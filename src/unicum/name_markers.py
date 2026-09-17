"""Rating badge and flags right of each player's name above their vehicle.

The client's vehicle markers set the player's name as plain text, so they
cannot carry our markup, and the engine's markers canvas only makes markers
from classes defined in the client's markers movie, battleVehicleMarkersApp.swf.
So:

- tools/build_as3.py installs a copy of that SWF with our code added
  (as3/src/unicum/markers). Its root, UnicumMarkersApp, loads
  unicum.markers.classes.swf right after the client's libraries, and only
  then registers with Python: UnicumVehicleMarker and UnicumComp7VehicleMarker
  subclass the client's marker symbol classes from those libraries, and add a
  view by the player's name.
- MarkersManager.createMarker is patched here to make ours in place of the
  client's symbol. Everything else about the marker stays the client's. If
  the movie does not know our classes -- the client's own SWF, another copy
  of it, or ours failed to load -- the client's marker is made instead, and
  the rest of that battle's markers too.

The view comes from unicum.markers.swf, loaded again whenever it changes on
disk, while the battle runs. The code added to the markers SWF needs a
client restart.

Markers are made when a battle starts: a reload of this module mid-battle
draws on the markers already made from our classes (their ids are kept on
the manager), and none on the others.
"""
import gc
import logging
import weakref

from gui.Scaleform.daapi.view.battle.shared.markers2d.manager import MarkersManager

from unicum import config

_logger = logging.getLogger('unicum.name_markers')

# The client's symbol -> ours, both in the markers movie.
SYMBOLS = {
    'VehicleMarker': 'unicum.markers::UnicumVehicleMarker',
    'Comp7VehicleMarkerUI': 'unicum.markers::UnicumComp7VehicleMarker',
}

VIEW_RES_PATH = 'gui/flash/unicum.markers.swf'

# What the markers movie calls with how loading our SWFs went.
READY_CALLBACK = 'unicum.markers.ready'

_SYNC_SECONDS = 0.1

# The text shown until the images are in, or instead of them.
_TEXT_COLOR = 0xFFFFFF

# Pixels after the badge, and after each flag: as in the players panel.
_BADGE_SPACE = 4
_FLAG_SPACE = 2

# Kept on the manager, so they survive a reload and end with the battle:
# the ids of the markers made from our classes, what each was last sent,
# and whether the movie refused our classes.
_IDS = '_unicumNameMarkerIds'
_SENT = '_unicumNameMarkerSent'
_REFUSED = '_unicumNameMarkerRefused'


class NameMarkers(object):

    def __init__(self, session, battle_flags):
        self._session = session
        self._flags = battle_flags
        self._view_stamp = _view_mtime()
        self._managers = weakref.WeakSet()

    def install(self):
        self._session.patch(MarkersManager, 'createExternalComponent', self._wrap_component)
        self._session.patch(MarkersManager, 'createMarker', self._wrap_create)
        self._session.patch(MarkersManager, 'destroyMarker', self._wrap_destroy)
        self._session.repeat(_SYNC_SECONDS, self._sync)
        if self._flags.alt is not None:
            self._flags.alt.on_change(self._sync)
        try:
            for manager in _running_managers():
                self._managers.add(manager)
        except Exception:
            _logger.exception('could not find the running battle markers')
        _logger.info('installed')

    def _wrap_component(self, original):

        def createExternalComponent(manager, *args, **kwargs):
            result = original(manager, *args, **kwargs)
            try:
                manager.addExternalCallback(READY_CALLBACK, _ready_handler())
            except Exception:
                _logger.exception('could not follow the markers movie')
            return result

        return createExternalComponent

    def _wrap_create(self, original):

        def createMarker(manager, symbol, *args, **kwargs):
            ours = SYMBOLS.get(symbol)
            if ours is not None and not getattr(manager, _REFUSED, False):
                try:
                    marker_id = original(manager, ours, *args, **kwargs)
                except SystemError:
                    setattr(manager, _REFUSED, True)
                    _logger.warning('the markers movie does not know %s: the client\'s own markers this battle '
                                    '(install the patched battleVehicleMarkersApp.swf with '
                                    'tools/build_as3.py, then restart the client)', ours)
                else:
                    try:
                        _ids(manager).add(marker_id)
                        self._managers.add(manager)
                    except Exception:
                        _logger.exception('could not keep track of a marker')
                    return marker_id
            return original(manager, symbol, *args, **kwargs)

        return createMarker

    def _wrap_destroy(self, original):

        def destroyMarker(manager, marker_id, *args, **kwargs):
            # The client's marker goes whatever happens to our bookkeeping.
            try:
                _ids(manager).discard(marker_id)
                _sent(manager).pop(marker_id, None)
            except Exception:
                _logger.exception('could not forget a marker')
            return original(manager, marker_id, *args, **kwargs)

        return destroyMarker

    def _sync(self):
        try:
            for manager in list(self._managers):
                if manager.canvas is not None:
                    self._draw(manager)
        except Exception:
            _logger.exception('could not draw by the names above vehicles')

    def _draw(self, manager):
        ours = _ids(manager)
        plugin = manager.getPlugin('vehicles')
        if not ours or plugin is None:
            return
        self._reload_view_if_changed(manager, ours)
        from unicum.battle import _arena
        arena = _arena()
        sent = _sent(manager)
        from unicum import modes
        shows = modes.team_filter(self._flags._settings)
        alt = self._flags.alt
        waits_for_nothing = not self._flags._settings.alt_only('markers') or (alt is not None and alt.down)
        for vehicle_id, marker in (getattr(plugin, '_markers', None) or {}).items():
            marker_id = marker.getMarkerID()
            if marker_id not in ours:
                continue
            vInfo = arena.getVehicleInfo(vehicle_id) if arena is not None else None
            shown = vInfo is not None and shows(vInfo.team) and waits_for_nothing
            entry = self._entry(vInfo.player.accountDBID if shown else None)
            data = (self._text(entry), _TEXT_COLOR, self._images(entry))
            if sent.get(marker_id) != data:
                manager.invokeMarker(marker_id, 'setUnicumData', *data)
                sent[marker_id] = data

    def _reload_view_if_changed(self, manager, ours):
        stamp = _view_mtime()
        if stamp == self._view_stamp:
            return
        self._view_stamp = stamp
        _logger.info('%s changed on disk, reloading the markers view', VIEW_RES_PATH)
        # Any of our markers reloads the view for all of them.
        manager.invokeMarker(next(iter(ours)), 'reloadUnicumView')

    def _entry(self, account_id):
        """The player's answer when the battle shows anything of theirs, else None."""
        from unicum.api.entry import PLAYERS
        if not account_id or not self._flags._settings.shows('battle'):
            return None
        return self._flags._lookup.get(PLAYERS, account_id)

    def _images(self, entry):
        """The badge then the flags, as "path|width|height|space after" joined by ";".

        The view draws them in place of the text once they are all loaded.
        A flag the client cannot resolve is left out; a rating without a
        badge keeps the text alone.
        """
        settings = self._flags._settings
        if entry is None:
            return ''
        images = []
        rating = settings.rating(entry, 'battle')
        if rating is not None:
            badge = self._flags._badges.image(settings.metric('battle'), rating)
            if badge is None:
                return ''
            images.append(badge + (_BADGE_SPACE,))
        if settings.shows_flags('battle'):
            for code in entry.flags[:settings['maxFlags']]:
                flag = self._flags._textures.image(code)
                if flag is not None:
                    images.append(flag + (_FLAG_SPACE,))
        return ';'.join('%s|%d|%d|%d' % image for image in images)

    def _text(self, entry):
        """The rating then the flags' codes, as plain text, or ''."""
        settings = self._flags._settings
        if entry is None:
            return ''
        parts = []
        rating = settings.rating(entry, 'battle')
        if rating is not None:
            parts.append('%d' % round(rating))
        if settings.shows_flags('battle'):
            parts.extend(entry.flags[:settings['maxFlags']])
        return u'  '.join(parts)


def _ready_handler(logger=_logger):
    """What the markers movie calls to say how loading our SWFs went.

    Held by the movie, so it may outlive a reload of this module: it uses
    nothing but its arguments.
    """

    def on_ready(state, *args):
        logger.info('markers movie: %s', state)

    return on_ready


def _on_manager(manager, name, factory):
    value = getattr(manager, name, None)
    if value is None:
        value = factory()
        setattr(manager, name, value)
    return value


def _ids(manager):
    return _on_manager(manager, _IDS, set)


def _sent(manager):
    return _on_manager(manager, _SENT, dict)


def _running_managers():
    """When this module loads mid-battle: the managers with markers of ours."""
    from helpers import isPlayerAvatar
    if not isPlayerAvatar():
        return []
    managers = []
    for obj in gc.get_objects():
        # Weak proxies pass isinstance too, and cannot be referenced.
        if isinstance(obj, weakref.ProxyTypes) or not isinstance(obj, MarkersManager):
            continue
        if obj.canvas is not None and getattr(obj, _IDS, None):
            managers.append(obj)
    return managers


def _view_mtime():
    import os
    path = config.res_mods_file(VIEW_RES_PATH)
    try:
        return os.path.getmtime(path) if path else None
    except OSError:
        return None


def install(session, battle_flags):
    NameMarkers(session, battle_flags).install()

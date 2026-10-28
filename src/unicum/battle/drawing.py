"""Putting a rating and a flag on each name, on every battle surface.

The measuring is here as much as the drawing. Scaleform gives no way to ask
what a string will be once its inline images have loaded, so the width is
computed from the markup, and `markup_width` is the one place that knows how.
A width guessed wrong is a column that overlaps the next one.

A mixin, for the reason the battles package gives: the entries, the session
and the settings are read by both halves.
"""
from __future__ import absolute_import

import logging
import re

from unicum import modes, views
from unicum.api.entry import PLAYERS

_logger = logging.getLogger('unicum.battle.drawing')

# The battle view's surfaces that can wait for Alt, in the order of its
# panelHidden, tabHidden and loadingHidden properties.
_ALT_SURFACES = ('panel', 'tab', 'loading')

# Of those, the ones that show a team's average: the players panel does not.
# Read by _mark_teams, which puts nothing in a team name while all of them are
# waiting for Alt.
_AVERAGE_SURFACES = ('tab', 'loading')

# The client's own method for "resend the arena's description", which is where
# a team name lives. Private, so it carries the mangled name of its class,
# `BattleStatisticsDataController`.
_ARENA_DESCRIPTION = '_BattleStatisticsDataController__setArenaDescription'

_IMG_WIDTH = re.compile(r'<IMG[^>]*\bwidth="(\d+)"', re.IGNORECASE)
_IMG = re.compile(r'<IMG[^>]*>', re.IGNORECASE)

# A space in markup; a bare number's digits, when a badge cannot draw.
_SPACE_WIDTH = 4
_DIGIT_WIDTH = 7

# The statistics controller's methods whose data can carry each team's order:
# every exchange it adds sort ids to (stats_ctrl.py). Frags re-sort the teams
# too, in the Tab of a mode that orders by them.
_ORDERED = ('as_setVehiclesDataS', 'as_addVehiclesInfoS', 'as_updateVehiclesInfoS',
            'as_updateVehicleStatusS', 'as_setFragsS', 'as_updateVehiclesStatsS')

def markup_width(markup):
    """Pixels the markup takes: its images' widths, and text by the character."""
    images = sum(int(width) for width in _IMG_WIDTH.findall(markup))
    text = _IMG.sub('', markup)
    return images + text.count(' ') * _SPACE_WIDTH + sum(c.isdigit() for c in text) * _DIGIT_WIDTH

def icon_markers(flags, badge):
    """[badge html, its width, flags html, their width], drawn as two columns."""
    badge, flags = badge.strip(), flags.strip()
    return [badge, markup_width(badge), flags, markup_width(flags)]

def _arena():
    """The battle's arena data provider, or None outside a battle."""
    from helpers import dependency
    from skeletons.gui.battle_session import IBattleSessionProvider
    return dependency.instance(IBattleSessionProvider).getArenaDP()

def _default_order(arena):
    """Each team's vehicle ids as the client sorts them for its screens.

    What TeamsSortedIDsComposer sends: sorted by VehicleInfoSortKey, without
    observers. Stands in until the client sends its own, which a mode may
    sort its own way.
    """
    from gui.battle_control.arena_info import vos_collections

    def ids(collection):
        return [vehicle_id for vehicle_id in collection(sortKey=vos_collections.VehicleInfoSortKey).ids(arena)
                if not arena.getVehicleInfo(vehicle_id).vehicleType.isObserver]

    return {'leftItemsIDs': ids(vos_collections.AllyItemsCollection),
            'rightItemsIDs': ids(vos_collections.EnemyItemsCollection)}


class Drawing(object):
    """Putting ratings and flags on the battle surfaces."""

    def _publish(self):
        # The view may have started drawing with no vehicle announced since,
        # in which case `_mark` has had no chance to notice. This runs on a
        # timer, so the rows marked before it was ready are taken back even
        # when nothing else happens in the battle.
        if views.html_team_names():
            self._take_back()
        """Give the battle view the markers and the teams' order, when changed.

        Both are read from the arena each time rather than kept from the
        vehicles drawn, so a hot reload mid-battle draws them at once. The
        order the client last sent is kept, since a mode may sort its own
        way; until one arrives, the client's default order stands in.
        """
        view = views.battle_view()
        arena = _arena() if view is not None else None
        if arena is None:
            # Between battles: the next one sends its own order.
            self._order = {'leftItemsIDs': [], 'rightItemsIDs': []}
            self._received = set()
            self._published = None
            return
        self._markers = {}
        shows = modes.team_filter(self._settings)
        for vInfo in arena.getVehiclesInfoIterator():
            if vInfo.isObserver() or not shows(vInfo.team):
                continue
            flags, badge = self._marker(vInfo.player.accountDBID)
            if flags or badge:
                self._markers[vInfo.vehicleID] = icon_markers(flags, badge)
        if len(self._received) < len(self._order):
            for key, ids in _default_order(arena).items():
                if key not in self._received:
                    self._order[key] = ids
        # The client's Scaleform has no JSON to parse with.
        state = ('\n'.join('%s\t%s\t%d\t%s\t%d' % ((k,) + tuple(v))
                           for k, v in sorted(self._markers.items())),
                 ','.join(str(i) for i in self._order['leftItemsIDs']),
                 ','.join(str(i) for i in self._order['rightItemsIDs']))
        held = self.alt is not None and self.alt.down
        # The players panel, the Tab screen and the loading screen, each hidden
        # (averages included) while it waits for Alt and Alt is up.
        hidden = tuple(self._settings.alt_only(surface) and not held for surface in _ALT_SURFACES)
        state = state + hidden
        # By identity: a reloaded view's proxy can reuse the old one's address.
        if self._published is not None and self._published[0] is view and self._published[1] == state:
            return
        first = self._published is None
        # Also when the marker count changes, not only on the first publish:
        # the first one happens before the account ids come back, so it always
        # shows almost none and says nothing about what the screens are given
        # once the answers land.
        count = len(self._markers)
        if count != getattr(self, '_probed', None):
            self._probed = count
            first = True
        if first:
            # One line per battle, saying what actually left Python. Without it
            # a Tab screen that draws nothing is indistinguishable from a Tab
            # screen that was never sent anything, and both look like silence
            # in the log. Cheap: it runs once per view, not per frame.
            # `ready` is the one that matters: a view whose window never
            # reaches LOADED never runs configUI, so it never searches the
            # display tree and never draws anything -- no error, no drawing.
            _logger.info('battle view: %d marker(s), %d left, %d right, '
                         'hidden panel/tab/loading=%s, ready=%s, status=%s',
                         len(self._markers),
                         len(self._order['leftItemsIDs']),
                         len(self._order['rightItemsIDs']),
                         '/'.join('1' if h else '0' for h in hidden),
                         views.BATTLE.ready(),
                         [getattr(w, 'windowStatus', '?') for w in views.BATTLE.windows()])
        # What Alt was showing a moment ago, to notice it changed.
        before = self._published[1][3:] if not first else None
        self._published = (view, state)
        try:
            view.markersText, view.leftIds, view.rightIds = state[:3]
        except Exception:
            _logger.exception('could not give the battle view its markers')
            return
        try:
            view.panelHidden, view.tabHidden, view.loadingHidden = hidden
        except Exception:
            # A view whose class predates the properties, until the next battle.
            _logger.debug('the battle view has no hidden surfaces yet', exc_info=True)
        if first or hidden != before:
            # Names drawn before the view loaded carry the markers after them,
            # and a team average only exists in the name, so Alt changing what
            # a screen shows is what asks for one to be put there or dropped
            # (see _mark_teams).
            self._redraw()

    def _mark_teams(self, controller, data):
        # Says, once per battle, whether this ran at all and what it found.
        # A team name with no average and a team name this never reached look
        # the same on screen, and that is the whole question right now.
        if not getattr(self, '_probed_teams', False):
            self._probed_teams = True
            try:
                _logger.info('team names: shows_average=%s, keys=%r',
                             self._settings.shows_average('battle'),
                             sorted(data.keys()) if hasattr(data, 'keys') else type(data).__name__)
            except Exception:
                _logger.exception('team names: could not describe the data')
        if not self._settings.shows_average('battle'):
            return
        # Not injected at all while every screen that would show it is waiting
        # for Alt.
        #
        # An average rides in the client's own team name field, which draws
        # plain text until TeamNamesHtml re-sets it as HTML. So putting one
        # there for a screen that is hidden shows a raw `<IMG ...>` tag for a
        # frame or two and then drops it, which is all the player ever sees of
        # it. `_publish` asks for a redraw whenever Alt changes what a screen
        # shows, and that is what puts the average back.
        held = self.alt is not None and self.alt.down
        if not held and all(self._settings.alt_only(surface) for surface in _AVERAGE_SURFACES):
            return
        arena = controller._battleCtx.getArenaDP()
        teams = {'allyTeamName': [], 'enemyTeamName': []}
        # A team whose players show nothing gets no average either.
        shows = modes.team_filter(self._settings)
        for vInfo in arena.getVehiclesInfoIterator():
            if vInfo.isObserver() or not shows(vInfo.team):
                continue
            key = 'allyTeamName' if arena.isAllyTeam(vInfo.team) else 'enemyTeamName'
            teams[key].append(vInfo.player.accountDBID)
        for key, account_ids in teams.items():
            average = self._average(account_ids)
            name = data.get(key)
            if not getattr(self, '_probed_each', False):
                _logger.info('team names: %s -> %d player(s), average=%r, name=%r',
                             key, len(account_ids), average, name)
            if average is None or name is None:
                continue
            if isinstance(name, str):
                # A localised team name arrives as UTF-8 bytes.
                name = name.decode('utf-8', 'replace')
            self._probed_each = True
            # A literal average sign rather than an entity: the field shows
            # plain text until the battle view re-sets it as HTML.
            badge = self._badges.markup(self._settings.metric('battle'), average) if views.html_team_names() else None
            data[key] = u'%s  \u00d8 %s' % (name, badge or '%d' % round(average))

    def _average(self, account_ids):
        """Mean chosen rating of the players whose rating is known, or None."""
        values = []
        for account_id in account_ids:
            if not account_id:
                continue
            if self._lookup.needs_fetch(PLAYERS, account_id):
                self._request(account_id)
            entry = self._lookup.get(PLAYERS, account_id)
            value = self._settings.rating(entry, 'battle')
            if value is not None:
                values.append(value)
        return sum(values) / float(len(values)) if values else None

    def _mark(self, component, vInfoVO):
        data = component.get()
        player = getattr(vInfoVO, 'player', None)
        if not modes.team_filter(self._settings)(getattr(vInfoVO, 'team', None)):
            return
        flags, badge = self._marker(getattr(player, 'accountDBID', None))
        if not getattr(self, '_probed_mark', False):
            self._probed_mark = True
            _logger.info('vehicle data: drawing=%s, flags=%d chars, badge=%d chars, '
                         'data is dict=%s, region before=%r',
                         views.html_team_names(), len(flags or ''), len(badge or ''),
                         isinstance(data, dict),
                         (data.get('region') if isinstance(data, dict) else None))
        vehicle_id = getattr(vInfoVO, 'vehicleID', None)
        # Beside the vehicle icon instead, drawn by the battle view.
        if views.html_team_names():
            self._inline.discard(vehicle_id)
            self._take_back()
            return
        # Left untouched without a marker, so a None stays None.
        if (flags or badge) and isinstance(data, dict):
            data['region'] = (data.get('region') or '') + flags + badge
            if vehicle_id:
                self._inline.add(vehicle_id)

    def _marker(self, account_id):
        """(flags markup, rating badge markup), each '' when not shown."""
        if not account_id or not self._settings.shows('battle'):
            return '', ''
        # An old answer is still drawn while a fresh one is fetched.
        if self._lookup.needs_fetch(PLAYERS, account_id):
            self._request(account_id)
        entry = self._lookup.get(PLAYERS, account_id)
        flags = ''
        if self._settings.shows_flags('battle'):
            flags = self._textures.markup(entry, self._settings['maxFlags'])
        # Compact: this one dict feeds the players panel, whose column is the
        # narrowest place any of these numbers has to fit.
        return flags, (self._badges.rating(entry, self._settings, 'battle')
                       + self._badges.extras(entry, self._settings, 'battle', compact=True))

    def _redraw(self):
        """Resend the arena description, which is what carries a team average.

        **Deliberately NOT `invalidateArenaInfo`.** That one resends the arena
        description AND the whole vehicles collection, and the second half is
        destructive to other mods: `invalidateVehiclesInfo` / `-Stats` push a
        new data provider into the players panel's lists, which re-binds every
        item renderer. Mods that graft their own Flash fields onto those
        renderers -- a spotted indicator, a hit-point label -- lose them, and
        since they build those once and never listen for an invalidation, they
        never come back. Holding Alt once showed everything, letting go took
        their labels away for the rest of the battle.

        Nothing we draw needs the vehicles resent. The players' notes are
        hidden by the view itself through `panelHidden` and friends; only a
        team average has to be written into the client's own team name field,
        and `__setArenaDescription` is exactly the half that resends it. It
        calls `as_setArenaInfoS`, which this mod already wraps, so the average
        is put back by the same path as always.

        Falls back to the whole invalidation on a client that has renamed the
        method: a team average that costs another mod its labels is still
        better than one that never appears, and the fallback is visible in the
        log rather than silent.
        """
        for controller in list(self._controllers):
            try:
                describe = getattr(controller, _ARENA_DESCRIPTION, None)
                if describe is not None:
                    describe()
                else:
                    _logger.info('no %s on this client, falling back to the '
                                 'full invalidation', _ARENA_DESCRIPTION)
                    controller.invalidateArenaInfo()
            except Exception:
                _logger.exception('could not redraw the battle statistics')

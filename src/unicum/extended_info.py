"""Whether the player is holding the key for the vehicle markers' extended info.

That is Alt unless the player bound it elsewhere (CMD_VEHICLE_MARKERS_SHOW_INFO).
The avatar turns the key into GameEvent.SHOW_EXTENDED_INFO on the battle's
event bus, with isDown, which is what the client's own markers and minimap
follow; the battle surfaces whose ratings show only while it is held follow
the same event.

The avatar reads no key before it is ready, which is when the loading screen
goes away (Avatar.handleKey returns early until then), so the event cannot
tell the loading screen anything. The key itself is also followed through
gui.InputHandler, which the client feeds every key before the avatar, the GUI
or the chat see it, loading or not, and checked against the same command, so
a rebound key counts the same. Either one held is held.

Both of those speak for a battle only. In the garage the key is read straight
from the client instead (BigWorld.isKeyDown), and only while something asks
for it: the skirmish room, whose ratings can wait for the key the same way.
"""
import logging

_logger = logging.getLogger('unicum.extended_info')


def _command_fired(key):
    """Whether `key` is the one bound to the markers' extended info."""
    import CommandMapping
    return CommandMapping.g_instance.isFired(CommandMapping.CMD_VEHICLE_MARKERS_SHOW_INFO, key)


def _bound_key():
    """The key the extended info is bound to, or None."""
    import CommandMapping
    return CommandMapping.g_instance.get('CMD_VEHICLE_MARKERS_SHOW_INFO')


# How often the key is read in the garage. Short enough that holding it shows
# at once, and it is read only while a surface asks for it.
_GARAGE_POLL = 0.1


def waits(alt, settings, surface):
    """Whether this surface shows nothing until the extended info key is held."""
    return alt is not None and settings.alt_only(surface) and not alt.down


class ExtendedInfo(object):

    def __init__(self, session):
        self._session = session
        self._event_down = False
        self._key_down = False
        self._garage_down = False
        self._wanted = 0
        self._last = False
        self._listeners = []

    @property
    def down(self):
        return self._event_down or self._key_down or self._garage_down

    def watch_outside_battle(self):
        """Ask for the key to be read in the garage too, for as long as this runs.

        The event bus and the input handler both speak for a battle alone, so
        without this the key is never down outside one.
        """
        self._wanted += 1
        if self._wanted == 1:
            self._session.repeat(_GARAGE_POLL, self._read_garage_key)

    def on_change(self, callback):
        self._listeners.append(callback)

    def install(self):
        self._install_event()
        self._install_keys()
        # A key held when a battle ends is never released as far as either
        # source goes: the next battle starts with it up.
        self._session.repeat(1.0, self._outside_battle)

    def _install_event(self):
        try:
            from gui.shared import EVENT_BUS_SCOPE, g_eventBus
            from gui.shared.events import GameEvent
        except ImportError:
            _logger.info('no event bus in this client, ratings follow the key alone')
            return
        handler = self._on_event
        g_eventBus.addListener(GameEvent.SHOW_EXTENDED_INFO, handler, scope=EVENT_BUS_SCOPE.BATTLE)

        def remove():
            g_eventBus.removeListener(GameEvent.SHOW_EXTENDED_INFO, handler, scope=EVENT_BUS_SCOPE.BATTLE)

        self._session.on_close(remove)

    def _install_keys(self):
        try:
            from gui import InputHandler
        except ImportError:
            _logger.info('no input handler in this client, the loading screen follows no key')
            return
        handler = self._on_key
        InputHandler.g_instance.onKeyDown += handler
        InputHandler.g_instance.onKeyUp += handler

        def remove():
            InputHandler.g_instance.onKeyDown -= handler
            InputHandler.g_instance.onKeyUp -= handler

        self._session.on_close(remove)

    def _on_event(self, event):
        self._event_down = bool((getattr(event, 'ctx', None) or {}).get('isDown'))
        self._changed()

    def _on_key(self, event):
        # A plain Event: a handler that raised would stop the client's own
        # handlers after it from hearing the key.
        try:
            from helpers import isPlayerAvatar
            if not isPlayerAvatar() or not _command_fired(event.key):
                return
            self._key_down = bool(event.isKeyDown())
            self._changed()
        except Exception:
            _logger.debug('could not read a key', exc_info=True)

    def _read_garage_key(self):
        try:
            from helpers import isPlayerAvatar
            if isPlayerAvatar():
                # In a battle the event and the input handler say it better.
                down = False
            else:
                import BigWorld
                key = _bound_key()
                down = bool(key is not None and BigWorld.isKeyDown(key))
        except Exception:
            _logger.debug('could not read the extended info key', exc_info=True)
            return
        if down == self._garage_down:
            return
        self._garage_down = down
        self._changed()

    def _outside_battle(self):
        try:
            from helpers import isPlayerAvatar
            if not isPlayerAvatar():
                self._event_down = self._key_down = False
                self._changed()
        except ImportError:
            pass

    def _changed(self):
        down = self.down
        if down == self._last:
            return
        self._last = down
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                _logger.exception('an extended info listener failed')

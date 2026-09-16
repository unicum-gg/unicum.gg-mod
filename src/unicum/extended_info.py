"""Whether the player is holding the key for the vehicle markers' extended info.

That is Alt unless the player bound it elsewhere (CMD_VEHICLE_MARKERS_SHOW_INFO).
The avatar turns the key into GameEvent.SHOW_EXTENDED_INFO on the battle's
event bus, with isDown, which is what the client's own markers and minimap
follow; the battle surfaces whose ratings show only while it is held follow
the same event rather than the raw key.
"""
import logging

_logger = logging.getLogger('unicum.extended_info')


class ExtendedInfo(object):

    def __init__(self, session):
        self._session = session
        self.down = False
        self._listeners = []

    def on_change(self, callback):
        self._listeners.append(callback)

    def install(self):
        try:
            from gui.shared import EVENT_BUS_SCOPE, g_eventBus
            from gui.shared.events import GameEvent
        except ImportError:
            _logger.info('no event bus in this client, ratings follow no key')
            return
        handler = self._on_event
        g_eventBus.addListener(GameEvent.SHOW_EXTENDED_INFO, handler, scope=EVENT_BUS_SCOPE.BATTLE)

        def remove():
            g_eventBus.removeListener(GameEvent.SHOW_EXTENDED_INFO, handler, scope=EVENT_BUS_SCOPE.BATTLE)

        self._session.on_close(remove)
        # A key held when a battle ends is never released as far as the event
        # goes: the next battle starts with it up.
        self._session.repeat(1.0, self._outside_battle)

    def _on_event(self, event):
        down = bool((getattr(event, 'ctx', None) or {}).get('isDown'))
        self._set(down)

    def _outside_battle(self):
        try:
            from helpers import isPlayerAvatar
            if not isPlayerAvatar():
                self._set(False)
        except ImportError:
            pass

    def _set(self, down):
        if down == self.down:
            return
        self.down = down
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                _logger.exception('an extended info listener failed')

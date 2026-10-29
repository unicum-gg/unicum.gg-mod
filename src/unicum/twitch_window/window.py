"""The window itself: making it, filling it, and taking it away.

The Gameface view and its model, which are the only part of this package that
names a client class. Everything about when it should exist is in `where`,
and everything about where it sits is in `placing`.
"""
from __future__ import absolute_import

import json
import logging
import zlib

from unicum import resources
from unicum.layouts import layout_id
from unicum.twitch_window.client import (_main_window, _model_class,
                                         _window_class)
from unicum.twitch_window.placing import (Gestures, battle_place,
                                          window_place, window_state)
from unicum.twitch_window.where import Watching, _in_battle, _language

_logger = logging.getLogger('unicum.twitch_window.window')

FEATURE = 'UnicumTwitchWindow'
# Where client 2.4.1.0 publishes the same layout. See unicum/layouts.py.
LAYOUT = 'R.mods.unicum.TwitchWindow.views.UnicumTwitchWindow'

_TICK_SECONDS = 0.5

# Property indexes, in _initialize's order.
_REVISION = 0
_SCRIPT = 1
_STYLE = 2
_TWITCH = 3


class TwitchWindowHost(Watching, Gestures):


    def __init__(self, session, settings, chat, link):
        self._session = session
        self._settings = settings
        self._chat = chat
        self._link = link
        self._layout = None
        self._window = None
        self._model = None
        self._ready = False
        self._size = None
        self._placed = None
        self._published = None
        self._stamps = None
        self._code = (0, u'', u'')
        self._machine = None
        # Until when the window stays without a queue on screen: asked for
        # a queue, or left one and waiting for the garage panel.
        self._entering_until = 0
        self._leaving = None  # (until, garage panel reports when the queue was left)
        self._to_battle = False
        self._gesture = None  # a drag or a resize under way, while the button is down
        self._loading = False  # in a battle, its loading screen not over yet

    def install(self):
        try:
            import openwg_gameface  # the injector the window's model needs
        except ImportError:
            _logger.info('openwg_gameface not installed, no Twitch window')
            return
        self._layout = layout_id(LAYOUT, FEATURE)
        if self._layout is None:
            _logger.info('%s not in the resource map yet; there is a Twitch window after the next client start',
                         FEATURE)
            return
        from PlayerEvents import g_playerEvents
        self._session.subscribe(g_playerEvents.onEnqueued, self._on_enqueued)
        for event in (g_playerEvents.onDequeued, g_playerEvents.onEnqueueFailure, g_playerEvents.onKickedFromQueue):
            self._session.subscribe(event, self._on_dequeued)
        self._session.subscribe(g_playerEvents.onArenaCreated, self._on_battle)
        self._session.subscribe(g_playerEvents.onAvatarBecomePlayer, self._on_avatar)
        from gui.shared import EVENT_BUS_SCOPE, events, g_eventBus
        g_eventBus.addListener(events.GameEvent.BATTLE_LOADING, self._on_loading, scope=EVENT_BUS_SCOPE.BATTLE)
        self._session.on_close(lambda: g_eventBus.removeListener(
            events.GameEvent.BATTLE_LOADING, self._on_loading, scope=EVENT_BUS_SCOPE.BATTLE))
        from unicum import twitch_panel
        twitch_panel.set_report_hook(self._on_panel_report)
        self._session.repeat(_TICK_SECONDS, self._tick)
        self._session.on_close(self._close)
        _logger.info('installed')

    def _close(self):
        from unicum import twitch_panel
        twitch_panel.set_report_hook(None)
        self._follow(None)
        self._destroy()

    def _create(self):
        main = _main_window()
        if main is None:
            return
        from frameworks.wulf import ViewFlags, ViewSettings, WindowLayer
        from gui.impl.pub import ViewImpl
        battle = _in_battle()
        revision, script, style = self._code
        self._published = self._state_text()
        model = _model_class()((revision, script, style, self._published))
        model.onItemClick += self._on_item
        view = ViewImpl(ViewSettings(layoutID=self._layout, flags=ViewFlags.VIEW, model=model))
        self._model = model
        # Above the battle's interface; in the lobby, under its own menus.
        self._window = _window_class()(view, main, WindowLayer.OVERLAY if battle else WindowLayer.WINDOW)
        self._ready = False
        self._size = None
        self._placed = None
        self._window.load()
        _logger.info('Twitch window opened over the %s',
                     ('battle loading screen' if self._loading else 'battle') if battle
                     else 'battle queue')

    @staticmethod
    def _cover(covered):
        from unicum import twitch_panel
        twitch_panel.set_covered(covered)

    def _destroy(self):
        window, model = self._window, self._model
        self._window = self._model = None
        self._ready = False
        self._gesture = None
        self._cover(False)
        if model is not None:
            try:
                model.onItemClick -= self._on_item
            except Exception:
                _logger.debug('could not unbind the Twitch window', exc_info=True)
        if window is not None:
            try:
                window.destroy()
                _logger.info('Twitch window closed')
            except Exception:
                _logger.exception('could not close the Twitch window')

    def _publish(self):
        text = self._state_text()
        if text != self._published:
            self._model._setString(_TWITCH, text)
            self._published = text

    def _place(self):
        """The window where the garage panel was, once the page has its size."""
        main = _main_window()
        if main is None or self._window is None or self._size is None or self._gesture is not None:
            return
        from unicum.twitch_panel import panel_rect
        rect = panel_rect()
        width, height = self._window.size
        if width <= 0 or height <= 0:
            return
        if self._own_place():
            # On a loading screen the window is still standing in for the
            # garage panel, so it stays where that panel was. Once the
            # battle itself is up it moves to the place of its own, out of
            # the corner the minimap wants.
            place = battle_place(self._settings['twitch']['battlePosition'],
                                 main.size, (width, height), self._per_rem())
        else:
            place = window_place(rect, main.size, (width, height))
        if place == self._placed:
            return
        if self._placed is None:
            _logger.info('Twitch window at %s, size %s (page %s px), main window %s, garage panel %s',
                         place, (width, height), self._size, tuple(main.size), rect)
        self._window.move(*place)
        self._placed = place

    # --- moving and resizing -------------------------------------------------

    def _stale(self):
        """Whether the window is gone, or hangs on a main window the client has since replaced.

        Coming back from a battle, the client builds its main window again,
        and a window opened on the one before stays loaded but out of sight.
        """
        from frameworks.wulf import WindowStatus
        if self._window.windowStatus in (WindowStatus.DESTROYING, WindowStatus.DESTROYED):
            return True
        main = _main_window()
        parent = self._window.parent
        return main is not None and parent is not None and parent.uniqueID != main.uniqueID

    def _state_text(self):
        from unicum import twitch_panel
        from unicum.twitch.protocol import ICON_RES_PATH
        from unicum.twitch_badges import drawable
        icon = 'img://%s' % ICON_RES_PATH if drawable(ICON_RES_PATH) else None
        state = twitch_panel.state(self._settings, self._chat, self._link, icon)
        battle = self._own_place()
        return json.dumps(window_state(
            state, twitch_panel.panel_rect(), _language(), battle=battle,
            battle_position=self._settings['twitch']['battlePosition'] if battle else None))

    def _check_code(self):
        """The panel's code, again when its files change on disk."""
        from unicum import tank_button
        stamps = tuple((path, resources.stamp(path)) for path in tank_button.panel_sources())
        if stamps == self._stamps:
            return
        self._stamps = stamps
        script, style = tank_button.panel_code()
        revision = zlib.crc32((script + style).encode('utf-8')) & 0x3fffffff
        self._code = (revision, script, style)
        if self._model is not None and self._ready:
            self._model._setString(_SCRIPT, script)
            self._model._setString(_STYLE, style)
            self._model._setNumber(_REVISION, revision)

"""The garage's Twitch panel where the garage is gone: the battle queue and loading screens.

The panel lives in the hangar's Gameface view (twitch_panel.py), and queueing
for a battle replaces the hangar with the queue screen, a Scaleform view: the
panel went with it, and a streamer watching the queue for minutes lost their
chat. So while the queue screen is up, the panel is opened again in a window
of its own, the same code (web/hangar/twitch_panel.js and .css) with the same
state, at the same place and the same size, folded if it is.

The battle's loading screen is the same story, in the battle app: the window
opens as soon as the player is in the battle (onAvatarBecomePlayer), the
battle's main window loaded, and closes when the game moves from the
loading screen to the battle page (GameEvent.BATTLE_LOADING, whose isShown
says which), after which the battle chat carries the Twitch messages as
before. Opening before the screen shows matters: while the map loads, the
page takes seconds to be drawn, and a loading screen can last only four.
In battle the window sits on the OVERLAY layer, the one that stays above the
battle's interface.

The window is a Gameface view of our own, UnicumTwitchWindow
(res/gui/gameface/mods/unicum/TwitchWindow/, declared in
res/mods/configs/res_map/unicum.json, so openwg_gameface restarts the client
once to add it), in a Wulf window the panel's size: a window as large as the
screen would take every click from the queue screen under it. It sits on the
WINDOW layer, above the queue screen and under the game's own menus, and
opens without taking the keyboard.

Its model carries the panel's code (`script`, `style`, `revision`, reloaded
when the files change, as the tank button's) and state (`twitch`, the
garage's JSON), and its onItemClick brings back what the player does, handed
to the garage panel's own handler: the window sends, folds, connects and
closes the way the garage does. Where it goes is the garage panel's last
report (twitch_panel.panel_rect), in the hangar's pixels, turned into the
window system's units by the main window's size; how large, the panel's size
in rem from that report.

Moved, resized or reset, the window does what the panel does in the garage,
and saves the same settings (twitchMove, twitchResize in rem), so each finds
the other where the player left it. The page cannot follow a mouse that
leaves it, so a press on the header or the corner only starts the gesture
(twitchWindowDrag, twitchWindowResize), and Python follows the cursor every
frame until the button is up, the way the known-good Gameface overlays do:
the window moves with it, or the panel is given its new size, which the
page then gives the window. A press on the header that does not move folds
the panel, as a click does in the garage.

The chat must never seem to leave the screen, so the window opens early
and closes late, and for a moment covers the garage panel, which it draws
exactly like, pixel for pixel. It opens when the server puts the player in
a queue (onEnqueued), before the lobby even moves to the queue screen, and
stays while the lobby's visible route is a battle queue. Once the lobby
leaves it, the window stays on until the garage panel is on screen again,
which its first report of where it is says (twitch_panel.panel_reports),
up to a few seconds; the hangar's Gameface takes a second or two to come
back. A battle found (onArenaCreated) leaves it on the queue screen, which
stays a moment longer, then closes it as soon as the lobby leaves the queue,
without waiting: the battle's loading must not have a lobby window over it.
The lobby's window only in the lobby, the battle's only on its loading screen.

Two panels on top of each other would show darker than one, their veils
added. So the two hand over: once the window is drawn, the garage panel
hides under it (twitch_panel.set_covered); once out of the queue, the
garage panel shows again, and its first report closes the window at once
(twitch_panel.set_report_hook) rather than on the next tick.

A tick does the rest: the state, the code, the place, and the route again
should an event be missed.

The page tells its size once it is laid out (twitchWindowSize), which is
also the sign it is ready: until then only its first state, given at
creation, reaches it.
"""
import json
import logging
import time
import zlib

from unicum import resources

_logger = logging.getLogger('unicum.twitch_window')

FEATURE = 'UnicumTwitchWindow'

_TICK_SECONDS = 0.5

# How long the window may wait, once in a queue was asked for, for the lobby
# to show the queue screen; once the queue is left, for the garage panel to
# be back.
_ENTER_SECONDS = 3.0
_LEAVE_SECONDS = 5.0

# What the window's page may ask of the garage panel's handler.
_PANEL_ITEMS = ('twitchSend', 'twitchCollapse', 'twitchClose', 'twitchConnect', 'twitchMove', 'twitchResize')

# How far the mouse goes before a press on the header is a drag (the panel's own).
_DRAG_THRESHOLD = 4

# The panel's size bounds and own size, in rem (twitch_panel.js, settings.panel_size).
_MIN_SIZE = (220, 120)
_MAX_SIZE = (1600, 1200)
_OWN_SIZE = (322, 220)

# Property indexes, in _initialize's order.
_REVISION = 0
_SCRIPT = 1
_STYLE = 2
_TWITCH = 3

# The panel's gap to the screen's right edge (twitch_panel.css, 46rem on a
# 1920 wide hangar), for when the garage has never said where it is.
_RIGHT_GAP = 46 / 1920.0


# The lobby state every battle queue sits under (gui/Scaleform/daapi/view/
# lobby/battle_queue/states.py): the common queue, the strongholds' and the
# map training's.
_QUEUE_CONTAINER = 'battleQueue'


def _in_lobby():
    """Whether the player is in the lobby, not in a battle nor on the way to one."""
    import BigWorld
    from Account import PlayerAccount
    return isinstance(BigWorld.player(), PlayerAccount)


def _in_battle():
    """Whether the player is in a battle, its loading screen included."""
    import BigWorld
    from Avatar import PlayerAvatar
    return isinstance(BigWorld.player(), PlayerAvatar)


def is_queue_route(state_id):
    """Whether a lobby state, by its id ("subScope/subLayer/battleQueue/battleQueue"), is a battle queue."""
    return _QUEUE_CONTAINER in (state_id or '').split('/')[:-1]


def _state_machine():
    from gui.Scaleform.lobby_entry import getLobbyStateMachine
    return getLobbyStateMachine()


def queue_open():
    """Whether the lobby shows a battle queue."""
    machine = _state_machine()
    info = getattr(machine, 'visibleRouteInfo', None)
    state = getattr(info, 'state', None)
    return state is not None and is_queue_route(state.getStateID())


def _language():
    try:
        from helpers import getClientLanguage
        return getClientLanguage()
    except Exception:
        return 'en'


def window_state(state, rect, lang='en'):
    """The garage panel's state, for the window: in its corner, at the garage panel's size.

    With the client's language, which the page puts on its <html> as the
    game's pages have it, for the game's own fonts to apply, and whether the
    player has a place or a size of their own, for the reset arrow.
    """
    state = dict(state)
    state['moved'] = bool(state.get('position') or state.get('size'))
    state['position'] = None
    state['covered'] = False
    state['lang'] = lang
    if rect is not None:
        state['size'] = [rect.rem_width, rect.rem_height]
    return state


def window_place(rect, main_size, window_size):
    """The window's top left corner, in the window system's units.

    Where the garage panel was, its hangar pixels scaled to the main window;
    without it, the right of the screen, halfway down. Kept on screen.
    """
    main_width, main_height = main_size
    width, height = window_size
    if rect is not None:
        x = rect.left * main_width / float(rect.screen_width)
        y = rect.top * main_height / float(rect.screen_height)
    else:
        x = main_width * (1 - _RIGHT_GAP) - width
        y = (main_height - height) / 2.0
    x = min(max(0, x), max(0, main_width - width))
    y = min(max(0, y), max(0, main_height - height))
    return int(round(x)), int(round(y))


def resized(start, delta, room):
    """The panel's size in rem, dragged by `delta` rem from `start`, within its bounds and `room`."""
    return tuple(int(round(min(max(start[i] + delta[i], _MIN_SIZE[i]), max(_MIN_SIZE[i], min(_MAX_SIZE[i], room[i])))))
                 for i in (0, 1))


def parse_size(text):
    """(width, height) in pixels from the page's "width,height", or None."""
    try:
        width, height = [int(part) for part in text.split(',')]
    except (AttributeError, ValueError):
        return None
    return (width, height) if width > 0 and height > 0 else None


def _model_class():
    from frameworks.wulf import ViewModel

    class TwitchWindowModel(ViewModel):
        __slots__ = ('onItemClick', '_first')

        def __init__(self, first):
            # (revision, script, style, twitch): the page's first state,
            # given before it loads rather than sent after.
            self._first = first
            super(TwitchWindowModel, self).__init__(properties=4, commands=1)

        def _initialize(self):
            super(TwitchWindowModel, self)._initialize()
            revision, script, style, twitch = self._first
            self._addNumberProperty('revision', revision)
            self._addStringProperty('script', script)
            self._addStringProperty('style', style)
            self._addStringProperty('twitch', twitch)
            self.onItemClick = self._addCommand('onItemClick')

    return TwitchWindowModel


def _window_class():
    from frameworks.wulf import WindowFlags
    from gui.impl.pub import WindowImpl

    class TwitchWindow(WindowImpl):
        __slots__ = ()

        def __init__(self, content, parent, layer):
            super(TwitchWindow, self).__init__(WindowFlags.WINDOW, content=content, layer=layer,
                                               parent=parent, name='unicumTwitchWindow')

        def _onReady(self):
            # Shown without the keyboard: the player's keys stay the game's
            # until they click in the panel's field.
            self.show(False)

    return TwitchWindow


def _main_window():
    """The client's main window once loaded, or None."""
    from frameworks.wulf import WindowStatus
    from helpers import dependency
    from skeletons.gui.impl import IGuiLoader
    main = dependency.instance(IGuiLoader).windowsManager.getMainWindow()
    if main is None or main.proxy is None or main.windowStatus != WindowStatus.LOADED:
        return None
    return main


class TwitchWindowHost(object):

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
            from openwg_gameface import res_id_by_key
            from gui.impl.gen_utils import INVALID_RES_ID
        except ImportError:
            _logger.info('openwg_gameface not installed, no Twitch window')
            return
        self._layout = res_id_by_key(FEATURE)
        if self._layout == INVALID_RES_ID:
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

    def _on_panel_report(self):
        if self._leaving is not None:
            self._tick()

    def _on_enqueued(self, *args):
        self._entering_until = time.time() + _ENTER_SECONDS
        self._tick()

    def _on_dequeued(self, *args):
        self._entering_until = 0
        self._tick()

    def _on_battle(self, *args):
        # Kept on the queue screen, closed when the lobby leaves it.
        self._entering_until = 0
        self._to_battle = True

    def _on_avatar(self, *args):
        # The loading screen is next: the window is opened as soon as the
        # battle's main window allows, for its page to be drawn by the time
        # the screen shows, and not seconds into a loading that may be short.
        self._loading = True
        self._tick()

    def _on_loading(self, event):
        self._loading = bool(getattr(event, 'ctx', {}).get('isShown'))
        _logger.info('battle loading screen %s', 'shown' if self._loading else 'gone')
        self._tick()

    def _close(self):
        from unicum import twitch_panel
        twitch_panel.set_report_hook(None)
        self._follow(None)
        self._destroy()

    def _follow(self, machine):
        """Listen to this lobby state machine's route changes, and no longer to the last one's.

        The lobby app, and its state machine with it, is built again after
        every battle.
        """
        if machine is self._machine:
            return
        if self._machine is not None:
            try:
                self._machine.onVisibleRouteChanged -= self._on_route
            except Exception:
                _logger.debug('could not stop following the lobby routes', exc_info=True)
        self._machine = machine
        if machine is not None:
            machine.onVisibleRouteChanged += self._on_route

    def _on_route(self, *args):
        self._tick()

    def _tick(self):
        try:
            self._follow(_state_machine())
            wanted = self._settings.shows_twitch_in_garage() and self._wanted()
        except Exception:
            _logger.exception('could not tell whether a battle queue is up')
            wanted = False
        if not wanted:
            self._leaving = None
            self._destroy()
            return
        try:
            self._check_code()
            if self._window is not None and self._stale():
                _logger.info('the Twitch window outlived its main window, opening it again')
                self._destroy()
            if self._window is None:
                self._create()
            elif self._ready:
                self._publish()
                self._place()
        except Exception:
            _logger.exception('could not keep the Twitch window up to date')

    def _wanted(self):
        """Whether the window should be up: in a queue, about to be, or just out of one."""
        from unicum.twitch_panel import panel_reports
        now = time.time()
        if not _in_lobby():
            self._entering_until = 0
            self._leaving = None
            self._to_battle = False
            return self._loading and _in_battle()
        self._loading = False
        if queue_open():
            self._entering_until = 0
            self._leaving = None
            return True
        if self._to_battle:
            # Out of the queue for a battle: no garage panel to wait for.
            self._to_battle = False
            return False
        if now < self._entering_until:
            return True
        if self._window is None:
            return False
        if self._leaving is None:
            self._leaving = (now + _LEAVE_SECONDS, panel_reports())
            # The garage panel back, to say when it is on screen.
            self._cover(False)
        until, reports = self._leaving
        return now < until and panel_reports() == reports

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
        from unicum.twitch import ICON_RES_PATH
        from unicum.twitch_badges import drawable
        icon = 'img://%s' % ICON_RES_PATH if drawable(ICON_RES_PATH) else None
        state = twitch_panel.state(self._settings, self._chat, self._link, icon)
        return json.dumps(window_state(state, twitch_panel.panel_rect(), _language()))

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
        _logger.info('Twitch window opened over the %s', 'battle loading screen' if battle else 'battle queue')

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
        place = window_place(rect, main.size, (width, height))
        if place == self._placed:
            return
        if self._placed is None:
            _logger.info('Twitch window at %s, size %s (page %s px), main window %s, garage panel %s',
                         place, (width, height), self._size, tuple(main.size), rect)
        self._window.move(*place)
        self._placed = place

    # --- moving and resizing -------------------------------------------------

    @staticmethod
    def _cursor():
        """The cursor in screen pixels, or None when it is not the player's to move."""
        import BigWorld
        import GUI
        import Keys
        cursor = GUI.mcursor()
        if not cursor.visible or not cursor.inWindow or not cursor.inFocus or \
                not BigWorld.isKeyDown(Keys.KEY_LEFTMOUSE):
            return None
        x, y = cursor.position
        width, height = GUI.screenResolution()
        return (x + 1.0) * 0.5 * width, (1.0 - y) * 0.5 * height

    def _units(self):
        """(window units per screen pixel, hangar pixels per screen pixel, hangar pixels per rem)."""
        import GUI
        from unicum.twitch_panel import panel_rect
        main = _main_window()
        rect = panel_rect()
        screen_width = float(GUI.screenResolution()[0])
        units = main.size[0] / screen_width if main is not None else 1.0
        hangar = rect.screen_width / screen_width if rect is not None else 1.0
        per_rem = rect.width / float(rect.rem_width) if rect is not None else 1.0
        return units, hangar, per_rem

    def _start_gesture(self, kind):
        from unicum.twitch_panel import panel_rect
        cursor = self._cursor()
        if self._window is None or cursor is None:
            return
        rect = panel_rect()
        self._gesture = {
            'kind': kind, 'cursor': cursor, 'position': tuple(self._window.position), 'moved': False,
            'size': (rect.rem_width, rect.rem_height) if rect is not None else _OWN_SIZE,
        }
        self._session.callback(0.0, self._gesture_step)

    def _gesture_step(self):
        gesture = self._gesture
        if gesture is None or self._window is None:
            return
        cursor = self._cursor()
        if cursor is None:
            self._end_gesture()
            return
        dx, dy = cursor[0] - gesture['cursor'][0], cursor[1] - gesture['cursor'][1]
        if not gesture['moved'] and abs(dx) < _DRAG_THRESHOLD and abs(dy) < _DRAG_THRESHOLD:
            self._session.callback(0.0, self._gesture_step)
            return
        gesture['moved'] = True
        units, hangar, per_rem = self._units()
        if gesture['kind'] == 'move':
            place = (int(round(gesture['position'][0] + dx * units)), int(round(gesture['position'][1] + dy * units)))
            if place != self._placed:
                self._window.move(*place)
                self._placed = place
        else:
            import GUI
            from unicum import twitch_panel
            screen = GUI.screenResolution()
            left, top = self._window.position
            room = ((screen[0] - left / units) * hangar / per_rem, (screen[1] - top / units) * hangar / per_rem)
            size = resized(gesture['size'], (dx * hangar / per_rem, dy * hangar / per_rem), room)
            if size != gesture.get('wanted'):
                gesture['wanted'] = size
                twitch_panel.update_rect(rem_width=size[0], rem_height=size[1],
                                         width=int(round(size[0] * per_rem)), height=int(round(size[1] * per_rem)))
                self._publish()
        self._session.callback(0.0, self._gesture_step)

    def _end_gesture(self):
        from unicum import twitch_panel
        gesture, self._gesture = self._gesture, None
        if gesture is None or self._window is None:
            return
        units, hangar, per_rem = self._units()
        if gesture['kind'] == 'move' and not gesture['moved']:
            # A click on the header: fold or unfold, as in the garage.
            collapsed = self._settings['twitch']['garageCollapsed']
            twitch_panel.on_item({'item': 'twitchCollapse', 'text': '0' if collapsed else '1'})
        elif gesture['kind'] == 'move':
            left, top = self._window.position
            left, top = left / units * hangar, top / units * hangar
            twitch_panel.update_rect(left=int(round(left)), top=int(round(top)))
            twitch_panel.on_item({'item': 'twitchMove',
                                  'text': '%d,%d' % (round(left / per_rem), round(top / per_rem))})
        elif 'wanted' in gesture:
            twitch_panel.on_item({'item': 'twitchResize', 'text': '%d,%d' % gesture['wanted']})
        self._publish()

    def _reset(self):
        """Back where and as the garage panel goes without the player's place and size."""
        from unicum import twitch_panel
        rect = twitch_panel.panel_rect()
        if rect is None:
            return
        per_rem = rect.width / float(rect.rem_width)
        twitch_panel.update_rect(left=rect.own_left, top=rect.own_top, rem_width=_OWN_SIZE[0],
                                 rem_height=_OWN_SIZE[1], width=int(round(_OWN_SIZE[0] * per_rem)),
                                 height=int(round(_OWN_SIZE[1] * per_rem)))
        self._placed = None
        self._publish()
        self._place()

    def _on_item(self, args=None):
        # From the page, through the window's command: never let an error out.
        try:
            item = args.get('item') if isinstance(args, dict) else None
            text = args.get('text') if isinstance(args, dict) else None
            if item == 'log':
                _logger.info('window: %s', text)
            elif item == 'twitchWindowSize':
                self._size = parse_size(text)
                self._ready = self._size is not None
                self._placed = None
                self._publish()
                self._place()
                if self._ready and self._leaving is None:
                    self._cover(True)
            elif item in ('twitchWindowDrag', 'twitchWindowResize'):
                self._start_gesture('move' if item == 'twitchWindowDrag' else 'resize')
            elif item in _PANEL_ITEMS:
                from unicum import twitch_panel
                twitch_panel.on_item({'item': item, 'text': text})
                if item in ('twitchMove', 'twitchResize') and not text:
                    self._reset()
                # Answer the page now rather than on the next tick.
                if self._model is not None:
                    self._publish()
        except Exception:
            _logger.exception('could not handle %r from the Twitch window', args)


def install(session, settings, chat, link):
    TwitchWindowHost(session, settings, chat, link).install()

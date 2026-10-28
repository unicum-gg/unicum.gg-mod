"""Where the window sits, and moving it with the mouse.

Gameface gives no window manager, so dragging and resizing are built out of
item events and a threshold: a press that moves less than `_DRAG_THRESHOLD`
is a click on the chat, and anything further is a gesture. The size and the
corner survive a restart, which is what `window_state` and `parse_size` are
for.

A mixin, for the reason given in `where`.
"""
from __future__ import absolute_import

import logging

from unicum.twitch_window.client import _main_window

_logger = logging.getLogger('unicum.twitch_window.placing')

# What the window's page may ask of the garage panel's handler.
_PANEL_ITEMS = ('twitchSend', 'twitchCollapse', 'twitchClose', 'twitchConnect', 'twitchMove', 'twitchResize')

# How far the mouse goes before a press on the header is a drag (the panel's own).
_DRAG_THRESHOLD = 4

# The panel's size bounds and own size, in rem (twitch_panel.js, settings.panel_size).
_MIN_SIZE = (220, 120)
_MAX_SIZE = (1600, 1200)
_OWN_SIZE = (322, 220)

# The panel's gap to the screen's right edge (twitch_panel.css, 46rem on a
# 1920 wide hangar), for when the garage has never said where it is.
_RIGHT_GAP = 46 / 1920.0

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


class Gestures(object):
    """Dragging and resizing it with the mouse."""

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

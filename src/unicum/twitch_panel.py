"""The player's Twitch chat in the garage: a panel beside the hangar.

It is drawn by src/unicum/web/hangar/twitch_panel.js, which runs in the
hangar's Gameface view through the loader tank_button.py already injects, so
it needs no layout of its own and no client restart. This module gives that
script the chat as it stands, as JSON in the loader model's `twitch` string:

    {"shown": true, "collapsed": false, "channel": "license__", "joined": true,
     "linked": true, "icon": "img://gui/maps/icons/unicum/twitch.png",
     "messages": [{"name": ..., "color": ..., "text": ..., "own": false,
                   "badges": ["img://gui/maps/icons/unicum/twitch/badges/..."]}]}

and acts on what the panel sends back through the model's onItemClick
command: twitchSend (a message typed in the panel, sent like the battle
chat's TO TWITCH), twitchConnect (links the game, see game_link.py),
twitchCollapse, twitchMove (dragged, or back to its place), twitchResize
(dragged by its corner, or back to its size) and twitchClose (turns the panel
off, as the settings window's checkbox does).
"""
import collections
import json
import logging
import weakref

_logger = logging.getLogger('unicum.twitch_panel')

_PUBLISH_SECONDS = 0.5

# The panel of this generation of the package, for on_item, which the hangar
# reaches through a string eval at click time (see tank_button.py).
_panel = None


def state(settings, chat, link, icon=None):
    """The panel's JSON-ready state."""
    channel = chat.channel
    messages = []
    for message in chat.history:
        messages.append({
            'name': message.name,
            'color': message.color,
            'text': message.text,
            'own': bool(channel) and message.login == channel,
            'badges': ['img://%s' % path for path in chat.badge_sources(message.badges)],
        })
    return {
        'shown': settings.shows_twitch_in_garage(),
        # The Twitch window lies over the panel, drawn the same: the panel
        # steps aside rather than darken it with a second veil.
        'covered': _covered,
        'collapsed': settings['twitch']['garageCollapsed'],
        'position': settings['twitch']['garagePosition'],
        'size': settings['twitch']['garageSize'],
        'channel': channel,
        # Told apart in the panel's empty chat: joining, or joined and quiet.
        'joined': chat.joined,
        'linked': bool(link.secret),
        # The account card above the panel (account_card.js) reads this too.
        'account': {'linked': bool(link.secret), 'name': getattr(link, 'name', None),
                    'hidden': bool(getattr(link, 'card_hidden', False))},
        'icon': icon,
        'messages': messages,
    }


def on_item(args):
    if _panel is not None:
        _panel.on_item(args)


class TwitchPanel(object):

    def __init__(self, session, settings, chat, link, sender):
        self._session = session
        self._settings = settings
        self._chat = chat
        self._link = link
        self._sender = sender
        self._published = weakref.WeakKeyDictionary()  # model -> JSON it last got

    def install(self):
        global _panel
        if self._chat is None:
            return
        _panel = self
        self._session.repeat(_PUBLISH_SECONDS, self._publish)
        _logger.info('installed')

    def _publish(self):
        from unicum import tank_button
        models = tank_button.live_models()
        if not models:
            return
        from unicum.twitch import ICON_RES_PATH
        from unicum.twitch_badges import drawable
        icon = 'img://%s' % ICON_RES_PATH if drawable(ICON_RES_PATH) else None
        text = json.dumps(state(self._settings, self._chat, self._link, icon))
        for model in models:
            if self._published.get(model) == text:
                continue
            if tank_button.set_twitch(model, text):
                self._published[model] = text

    def on_item(self, args):
        self._act(args)
        # Answer the panel now rather than on the next tick.
        self._publish()

    def publish_now(self):
        try:
            self._publish()
        except Exception:
            _logger.exception('could not update the Twitch panel')

    def _act(self, args):
        item = args.get('item')
        if item == 'twitchSend':
            text = args.get('text')
            if isinstance(text, basestring) and text.strip() and self._sender is not None:
                self._sender.send(text.strip()[:500])
        elif item == 'accountSettings':
            from unicum import mods_list
            mods_list.open_settings()
        elif item == 'accountHide':
            self._link.hide_card()
            _card_hidden_notice()
        elif item == 'accountConnect':
            from unicum.settings_window import _linked_notice
            self._link.connect(_linked_notice, twitch=False)
        elif item == 'twitchConnect':
            from unicum.settings_window import _linked_notice
            self._link.connect(_linked_notice)
        elif item == 'twitchCollapse':
            self._settings.update({'twitch': {'garageCollapsed': args.get('text') == '1'}})
        elif item == 'twitchClose':
            self._settings.update({'twitch': {'garage': False}})
            _closed_notice()
        elif item == 'twitchMove':
            self._settings.update({'twitch': {'garagePosition': parse_position(args.get('text'))}})
        elif item == 'twitchResize':
            self._settings.update({'twitch': {'garageSize': parse_size(args.get('text'))}})
        elif item == 'twitchRect':
            global _rect, _reports
            _rect = parse_rect(args.get('text')) or _rect
            _reports += 1
            if _report_hook is not None:
                _report_hook()


def _notice(text):
    from gui import SystemMessages
    from gui.shared.notifications import NotificationPriorityLevel
    SystemMessages.pushMessage(text, type=SystemMessages.SM_TYPE.Information,
                               priority=NotificationPriorityLevel.MEDIUM)


def _closed_notice():
    from unicum.settings_window import GARAGE_CHAT_LABEL
    _notice(u'unicum.gg: the Twitch chat panel is off. Turn it back on with "%s" in the unicum.gg '
            u'settings.' % GARAGE_CHAT_LABEL)


def _card_hidden_notice():
    """Where the card went, as the Twitch panel says where it went: closing
    something with no word on how to get it back reads as losing it."""
    from unicum.settings_window import CARD_LABEL
    _notice(u'unicum.gg: the account card is hidden. Bring it back with "%s" in the unicum.gg '
            u'settings.' % CARD_LABEL)


def parse_position(text):
    """[left, top] from the panel's "left,top" in rem; None (its own place) for anything else."""
    try:
        left, top = [int(round(float(part))) for part in text.split(',')]
    except (AttributeError, ValueError):
        return None
    return [max(0, left), max(0, top)]


# Where the garage panel last was: a PanelRect, or None until it has said.
# The battle queue screen, which replaces the hangar, opens the Twitch window
# at the same place and size (twitch_window.py).
_rect = None

# How many reports the garage panel has sent: a new one is the sign a garage
# panel is on screen, which the first report of a new hangar's panel is.
_reports = 0

# Called on every report, for the Twitch window to hand the screen back at once.
_report_hook = None

# Whether the Twitch window covers the panel (twitch_window.py).
_covered = False

PanelRect = collections.namedtuple('PanelRect', 'left top width height screen_width screen_height folded '
                                                'rem_width rem_height own_left own_top')


def panel_rect():
    """The garage panel's last place on screen, or None."""
    return _rect


def panel_reports():
    """How many times the garage panel has said where it is."""
    return _reports


def set_report_hook(hook):
    """Have `hook()` called whenever the garage panel says where it is, or no longer with None."""
    global _report_hook
    _report_hook = hook


def set_covered(covered):
    """Hide the garage panel under the Twitch window, or show it again, now."""
    global _covered
    if covered == _covered:
        return
    _covered = covered
    if _panel is not None:
        _panel.publish_now()


def parse_rect(text):
    """A PanelRect from the panel's report, or None.

    "left,top,width,height,screen width,screen height,folded,width,height,
    own left,own top": the panel's box and the page's size in the hangar's
    pixels, whether it is folded, its size in rem, the height it has
    unfolded, then where it goes without the player's place, in pixels.
    """
    try:
        parts = [int(round(float(part))) for part in text.split(',')]
    except (AttributeError, ValueError):
        return None
    if len(parts) != 11 or min(parts[2:6] + parts[7:9]) <= 0:
        return None
    return PanelRect(*(parts[:6] + [bool(parts[6])] + parts[7:]))


def update_rect(**fields):
    """The garage panel's last place, changed where the Twitch window moved or sized it."""
    global _rect
    if _rect is not None:
        _rect = _rect._replace(**fields)


def parse_size(text):
    """[width, height] from the panel's "width,height" in rem; None (its own size) otherwise.

    The bounds are the settings' own (settings.panel_size), so a size typed
    into settings.json and one dragged in the garage answer to the same limits.
    """
    from unicum.settings import panel_size
    try:
        width, height = [int(round(float(part))) for part in text.split(',')]
    except (AttributeError, ValueError):
        return None
    return panel_size([width, height])


def install(session, settings, chat, link, sender):
    TwitchPanel(session, settings, chat, link, sender).install()

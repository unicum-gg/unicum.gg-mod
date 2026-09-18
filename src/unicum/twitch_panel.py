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
twitchCollapse, twitchMove (dragged, or back to its place) and twitchClose
(turns the panel off, as the settings window's checkbox does).
"""
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
        'collapsed': settings['twitch']['garageCollapsed'],
        'position': settings['twitch']['garagePosition'],
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


def _closed_notice():
    from gui import SystemMessages
    from gui.shared.notifications import NotificationPriorityLevel
    SystemMessages.pushMessage(u'unicum.gg: the Twitch chat panel is off. Turn it back on with '
                               u'"Twitch chat in the garage" in the unicum.gg settings.',
                               type=SystemMessages.SM_TYPE.Information,
                               priority=NotificationPriorityLevel.MEDIUM)


def parse_position(text):
    """[left, top] from the panel's "left,top" in rem; None (its own place) for anything else."""
    try:
        left, top = [int(round(float(part))) for part in text.split(',')]
    except (AttributeError, ValueError):
        return None
    return [max(0, left), max(0, top)]


def install(session, settings, chat, link, sender):
    TwitchPanel(session, settings, chat, link, sender).install()

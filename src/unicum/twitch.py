"""Messages from the player's Twitch chat, shown in the battle chat.

Read-only and anonymous: Twitch's chat is IRC over a WebSocket
(wss://irc-ws.chat.twitch.tv), where a `justinfanNNNN` nick joins a channel
without an account and receives what is said there. The connection goes
through the client's own WebSocket (the `websocket` package over the native
`_websocket`), whose callbacks come on the game's thread: nothing here blocks
or needs a thread of its own.

In battle, each message goes to the battle chat with
MessengerEntry.gui.addClientMessage, the way the client shows its own notices
there: only on this screen, never sent to anyone. Outside a battle messages
are kept, a few at a time, for a garage view to come.

A battle opens with the last of them rather than with an empty chat, so what
was said while the player sat in the garage or waited out the loading screen
is still there to read (`ChatQueue.open_battle`).

settings.json: {"twitch": {"channel": "", "battleChat": true}}. With no
channel typed there, the one the player linked to their account on unicum.gg
(`twitchLogin` of GET /api/{region}/players/{nickname}) is followed. No
channel either way, no connection.
"""
import collections
import json
import logging
import os
import random
import re
import time
import urllib

from unicum.twitch_badges import ChatBadges, drawable, parse_badges

_logger = logging.getLogger('unicum.twitch')

URL = 'wss://irc-ws.chat.twitch.tv:443'

# How often the connection is checked against the settings, and how long a
# lost one waits before trying again.
_CHECK_SECONDS = 2.0
_RETRY_SECONDS = 30.0

# Shown at most this many a tick, from a queue this long: a burst of chat
# neither floods the battle chat nor lags far behind it. The queue also holds
# what is said while a battle loads, when the battle chat does not exist yet
# and a message handed to it would be dropped; past _BACKLOG waiting, it
# catches up faster.
_FLUSH_SECONDS = 0.5
_PER_FLUSH = 2
_PER_FLUSH_BEHIND = 5
_BACKLOG = 10
_QUEUE = 40

# Kept for the garage, newest last.
_HISTORY = 50

# What a battle opens with, from that history: chat said while the player sat
# in the garage or waited out the loading screen, which used to be dropped.
# Ten lines because the battle chat shows few at a time and the game's own
# notices have to stay readable; ten minutes because after a long garage stop
# the last battle's chat is not context any more, it is noise.
_REPLAY = 10
_REPLAY_SECONDS = 600.0

# The battle's loading screen has a chat of its own, and `_battle_chat_shown`
# is already true while it is up: a message written there is thrown away with
# the screen, seconds before the player can read anything. So nothing is
# written until the screen is over (GameEvent.BATTLE_LOADING), and never
# longer than this, in case that event does not come in some mode -- losing
# the first seconds of a battle's chat is a bad day, losing all of it silently
# is a bug nobody would report.
_LOADING_HOLD = 60.0

_MAX_TEXT = 200

# The linked channel is asked for once a session; a failed answer again after
# this long. The player's page can take seconds to build when it is cold.
_LINKED_RETRY_SECONDS = 60.0
_LINKED_TIMEOUT = 30.0

_TWITCH_COLOR = '#9146FF'
_DEFAULT_NAME_COLOR = '#C8C8C8'
_TEXT_COLOR = '#FFFFFF'

# The Glitch before each message, built by tools/badges/icon.mjs. A resource
# file, so one installed into a folder the client did not know at startup
# draws from the next start; until then the word "Twitch" stands in.
ICON_RES_PATH = 'gui/maps/icons/unicum/twitch.png'
_ICON = '<IMG SRC="img://%s" width="14" height="14" vspace="-3"/>' % ICON_RES_PATH

_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')

# IRCv3 tag value escapes.
_TAG_ESCAPES = {'\\s': ' ', '\\:': ';', '\\\\': '\\', '\\r': '\r', '\\n': '\n'}

Message = collections.namedtuple('Message', 'name color text badges login')
Message.__new__.__defaults__ = ((), '')


def parse_line(line):
    """('ping', server), ('message', Message) or None, for one IRC line."""
    tags = {}
    if line.startswith('@'):
        raw, _, line = line.partition(' ')
        for pair in raw[1:].split(';'):
            key, _, value = pair.partition('=')
            tags[key] = re.sub(r'\\[s:\\rn]', lambda m: _TAG_ESCAPES[m.group(0)], value)
    if line.startswith('PING'):
        return 'ping', line.partition(' ')[2]
    prefix = ''
    if line.startswith(':'):
        prefix, _, line = line[1:].partition(' ')
    command, _, rest = line.partition(' ')
    if command != 'PRIVMSG':
        return None
    _, _, text = rest.partition(' :')
    if text.startswith('\x01ACTION ') and text.endswith('\x01'):
        text = text[len('\x01ACTION '):-1]
    name = tags.get('display-name') or prefix.partition('!')[0]
    color = tags.get('color') if _COLOR.match(tags.get('color') or '') else None
    login = prefix.partition('!')[0].lower()
    return 'message', Message(name, color, text, parse_badges(tags.get('badges')), login)


def format_message(message, icon=False, badges=''):
    """The battle chat's HTML for a Twitch message, behind the Glitch or the word.

    `badges` is the <IMG> markup of the viewer's badges, drawn before the name.
    """
    text = message.text if len(message.text) <= _MAX_TEXT else message.text[:_MAX_TEXT - 1] + u'\u2026'
    source = _ICON if icon else u"<font color='%s'>Twitch</font>" % _TWITCH_COLOR
    return u"%s %s<font color='%s'>%s</font>: <font color='%s'>%s</font>" % (
        source, badges, message.color or _DEFAULT_NAME_COLOR, _escape(message.name), _TEXT_COLOR, _escape(text))


def _escape(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# How long a message the player sent from the game waits for Twitch to send
# it back, to be left out then.
_ECHO_SECONDS = 30.0


class EchoGuard(object):
    """The player's own messages, shown as they send them rather than once Twitch echoes them.

    Sending goes through unicum.gg and Twitch before the read connection gets
    the message back, a second or two in which the battle chat showed nothing
    and the message seemed lost. So it is shown at once, and the copy Twitch
    sends back from the player's own login is left out.
    """

    def __init__(self):
        self._sent = []  # (text, time)

    def expect(self, text, now):
        self._sent.append((_same_words(text), now))

    def consume(self, login, channel, text, now):
        """Whether this message is the echo of one already shown."""
        self._sent = [(sent, at) for sent, at in self._sent if now - at < _ECHO_SECONDS]
        if not channel or login != channel:
            return False
        text = _same_words(text)
        for index, (sent, _) in enumerate(self._sent):
            if sent == text:
                del self._sent[index]
                return True
        return False


def _same_words(text):
    # Twitch collapses runs of spaces, so the echo is compared word for word.
    return u' '.join(text.split())


# How the player looks in their own chat, kept for the messages shown before
# Twitch echoes them: name, colour and badges only come with a message.
SELF_STORE = os.path.join('mods', 'configs', 'unicum', 'twitch_self.json')

# Before any of their own messages was seen: it is their channel.
_OWNER_BADGES = ('broadcaster/1',)
# The name on the player's own message while their channel is not known yet.
_OWN_NAME = 'You'



def own_message(appearance, channel, text):
    """The player's message as Twitch would show it, from their last seen appearance."""
    if appearance and appearance.get('login') == channel:
        return Message(appearance.get('name') or channel, appearance.get('color'), text,
                       tuple(appearance.get('badges') or ()), channel)
    return Message(channel or _OWN_NAME, None, text, _OWNER_BADGES, channel)


def appearance_of(message):
    return {'login': message.login, 'name': message.name, 'color': message.color,
            'badges': list(message.badges)}


class ChatQueue(object):
    """What waits to be shown, and what the garage will show."""

    def __init__(self):
        self.pending = collections.deque(maxlen=_QUEUE)
        # (when, message) pairs rather than bare messages, so a battle can
        # replay only what is still recent. One deque rather than a second one
        # of timestamps beside it: paired, they cannot drift apart.
        self.kept = collections.deque(maxlen=_HISTORY)
        # Moves whenever the history does, for the garage to follow.
        self.revision = 0

    @property
    def history(self):
        return [message for _, message in self.kept]

    def add(self, message, in_battle, keep=True):
        if keep:
            # Wall clock, not BigWorld.time(): the age that matters here spans
            # the garage and the loading screen, and the game's own clock can
            # start over when the client changes space.
            self.kept.append((time.time(), message))
            self.revision += 1
        if in_battle:
            self.pending.append(message)

    def open_battle(self):
        """Replace what waits with the chat a battle should open on.

        Taken from the history, not added in front of what `pending` already
        holds: a message that arrived during the loading screen is in both, so
        adding would show it twice. Replacing cannot, and leaves the order
        alone, because the history ends with exactly those same messages.
        """
        cutoff = time.time() - _REPLAY_SECONDS
        recent = [message for when, message in self.kept if when >= cutoff][-_REPLAY:]
        self.pending.clear()
        self.pending.extend(recent)
        return len(recent)

    def take(self):
        taken = []
        count = _PER_FLUSH_BEHIND if len(self.pending) > _BACKLOG else _PER_FLUSH
        while self.pending and len(taken) < count:
            taken.append(self.pending.popleft())
        return taken


def linked_url(api_base, region, nickname):
    return '%s/api/%s/players/%s' % (api_base.rstrip('/'), region, urllib.quote(nickname, safe=''))


def linked_channel(payload):
    """The Twitch login in a player's answer, or '' when they linked none."""
    from unicum.settings import twitch_channel
    return twitch_channel(payload.get('twitchLogin')) if isinstance(payload, dict) else ''


class LinkedChannel(object):
    """The Twitch channel the player linked on unicum.gg, asked for once."""

    def __init__(self, session):
        self._session = session
        self._nickname = None
        self._channel = ''
        self._in_flight = False
        self._retry_at = 0.0

    def get(self):
        """The channel known so far; asks for it when the player is new."""
        import BigWorld
        nickname = getattr(BigWorld.player(), 'name', None)
        if not nickname:
            return self._channel
        if nickname != self._nickname:
            self._nickname, self._channel, self._retry_at = nickname, '', 0.0
        if not self._in_flight and self._retry_at is not None and BigWorld.time() >= self._retry_at:
            self._fetch(nickname)
        return self._channel

    def _fetch(self, nickname):
        import BigWorld
        from unicum import config
        from unicum.api.http import parse
        self._in_flight = True

        def done(response):
            self._in_flight = False
            if nickname != self._nickname:
                return
            payload = parse(response, 'the linked Twitch channel')
            if payload is None:
                self._retry_at = BigWorld.time() + _LINKED_RETRY_SECONDS
                return
            self._retry_at = None
            self._channel = linked_channel(payload)
            _logger.info('linked Twitch channel: %s', self._channel or 'none')

        self._session.fetch(linked_url(config.API_BASE, config.REGION, nickname), done,
                            timeout=_LINKED_TIMEOUT)


class TwitchChat(object):

    def __init__(self, session, settings, link=None):
        self._session = session
        self._settings = settings
        # The unicum.gg account link, which knows the linked channel without
        # the player page, the slowest the site serves.
        self._link = link
        self._client = None
        self._channel = None
        self._opened = False
        self._retry_at = 0.0
        self._queue = ChatQueue()
        self._linked = LinkedChannel(session)
        self._badges = ChatBadges(session)
        self._echoes = EchoGuard()
        self._self = _load_self()
        # Whether this battle has already been given the chat it opened with.
        self._seeded = False
        # While the battle's loading screen is up, and no later than this.
        self._loading_until = 0.0

    @property
    def history(self):
        return self._queue.history

    @property
    def revision(self):
        return self._queue.revision

    @property
    def channel(self):
        return self._channel or ''

    @property
    def joined(self):
        """True once the connection is open and the channel joined."""
        return bool(self._opened)

    def badge_sources(self, badges):
        """The resource paths of a message's badges that can draw now."""
        return self._badges.sources(badges)

    def install(self):
        self._follow_loading()
        self._session.repeat(_CHECK_SECONDS, self._check)
        self._session.repeat(_FLUSH_SECONDS, self._flush)
        self._session.on_close(self._close)
        _logger.info('installed')

    def _follow_loading(self):
        """Know when the battle's loading screen is up, and when it is over.

        Guarded rather than let to fail: without these events the chat shows
        as it did before, a little of it into the loading screen, which is far
        better than a Twitch chat that does not install at all.
        """
        try:
            from PlayerEvents import g_playerEvents
            from gui.shared import EVENT_BUS_SCOPE, events, g_eventBus
            self._session.subscribe(g_playerEvents.onAvatarBecomePlayer, self._on_avatar)
            g_eventBus.addListener(events.GameEvent.BATTLE_LOADING, self._on_loading,
                                   scope=EVENT_BUS_SCOPE.BATTLE)
            self._session.on_close(lambda: g_eventBus.removeListener(
                events.GameEvent.BATTLE_LOADING, self._on_loading, scope=EVENT_BUS_SCOPE.BATTLE))
        except Exception:
            _logger.exception('no battle loading events; the chat may open a little early')

    def _on_avatar(self, *args):
        # The loading screen comes next, so the hold starts here rather than
        # when it shows: the battle chat already exists in between.
        self._loading_until = time.time() + _LOADING_HOLD

    def _on_loading(self, event):
        shown = bool(getattr(event, 'ctx', {}).get('isShown'))
        self._loading_until = time.time() + _LOADING_HOLD if shown else 0.0

    def _check(self):
        """Follow the channel the settings name: join it, change, or leave."""
        import BigWorld
        wanted = self._settings.twitch_channel()
        if not wanted and self._settings['enabled']:
            wanted = self._settings.twitch_channel(self._linked_channel())
        if wanted != self._channel:
            self._close()
            self._retry_at = 0.0
        if not wanted or self._client is not None or BigWorld.time() < self._retry_at:
            return
        self._open(wanted)

    def _linked_channel(self):
        from unicum import config
        if config.PREVIEW_SIGNED_OUT:
            return ''
        if self._link is not None and self._link.twitch_login:
            return self._link.twitch_login
        return self._linked.get()

    def _open(self, channel):
        import websocket
        self._channel = channel
        self._badges.follow(channel)
        self._opened = False
        client = websocket.Client()
        listener = client.listener
        listener.onOpened += self._on_opened
        listener.onFailed += self._on_failed
        listener.onClosed += self._on_closed
        listener.onMessage += self._on_message
        self._client = client
        if not client.open(URL):
            _logger.warning('could not open the Twitch chat connection')
            self._lost()
        else:
            _logger.info('connecting to the Twitch chat of %s', channel)

    def _on_opened(self, server):
        self._opened = True
        # Anonymous: any justinfan nick, no password, read-only.
        for line in ('CAP REQ :twitch.tv/tags twitch.tv/commands',
                     'NICK justinfan%d' % random.randint(10000, 99999),
                     'JOIN #%s' % self._channel):
            self._client.sendText(line)
        _logger.info('joined the Twitch chat of %s', self._channel)

    def _on_failed(self, server, code, reason):
        _logger.warning('the Twitch chat connection failed: %s %s', code, reason)
        self._lost()

    def _on_closed(self, server, code, reason):
        _logger.info('the Twitch chat connection closed: %s %s', code, reason)
        self._lost()

    def _lost(self):
        """Let go of a failed or closed connection, and try again later.

        Called from the connection's own callbacks: it is torn down on the
        next tick rather than from inside them.
        """
        import BigWorld
        self._retry_at = BigWorld.time() + _RETRY_SECONDS
        channel = self._channel
        self._session.callback(0.0, lambda: self._release(channel))

    def _release(self, channel):
        if self._channel == channel:
            self._close()
            # Kept, so the next check waits for the retry instead of seeing a change.
            self._channel = channel

    def _on_message(self, code, payload):
        try:
            if isinstance(payload, str):
                payload = payload.decode('utf-8', 'replace')
            for line in payload.split('\r\n'):
                if line:
                    self._handle(line)
        except Exception:
            _logger.exception('could not read a Twitch chat message')

    def _handle(self, line):
        parsed = parse_line(line)
        if parsed is None:
            return
        kind, value = parsed
        if kind == 'ping':
            self._client.sendText('PONG %s' % value)
        else:
            import BigWorld
            echo = self._echoes.consume(value.login, self._channel, value.text, BigWorld.time())
            if self._channel and value.login == self._channel:
                self._remember_self(value)
            # The player's own message is already in the history, from echo().
            self._queue.add(value, _in_battle() and not echo, keep=not echo)

    def echo(self, text):
        """Show a message the player just sent to their chat, before Twitch sends it back."""
        import BigWorld
        from helpers import isPlayerAvatar
        self._echoes.expect(text, BigWorld.time())
        message = own_message(self._self, self._channel or '', text)
        in_battle = isPlayerAvatar() and self._settings.shows_twitch_in_battle()
        # Shown at once only once the battle has had its opening chat. Before
        # that, and while the battle loads, it waits in the queue like the
        # others: it is in the history too, so the opening chat carries it, and
        # showing it now would show it twice.
        show_now = in_battle and _battle_chat_shown() and self._seeded
        self._queue.add(message, in_battle and not show_now)
        if show_now:
            self._show([message])

    def _remember_self(self, message):
        appearance = appearance_of(message)
        if appearance == self._self:
            return
        self._self = appearance
        try:
            with open(SELF_STORE, 'w') as handle:
                json.dump(appearance, handle)
        except (IOError, OSError):
            _logger.debug('could not save how the player looks in chat', exc_info=True)

    def _flush(self):
        # Out of battle, what waited is stale for the next one, which opens
        # from the history instead. Re-arming here rather than on a battle
        # event keeps the two halves of this in one place.
        if not self._settings.shows_twitch_in_battle() or not _in_battle():
            self._queue.pending.clear()
            self._seeded = False
            self._loading_until = 0.0
            return
        # The loading screen's chat counts as shown and is thrown away with
        # the screen: everything waits, and comes out together once the player
        # is looking at the battle.
        if not _battle_chat_shown() or time.time() < self._loading_until:
            return
        if not self._seeded:
            # Open on the chat the player missed getting in here, rather than
            # on an empty screen. Logged because a quiet channel and a broken
            # replay look exactly the same from the battle chat.
            self._seeded = True
            _logger.info('battle chat opens on %d of the %d message(s) in hand',
                         self._queue.open_battle(), len(self._queue.kept))
        taken = self._queue.take()
        if taken:
            self._show(taken)

    def _show(self, messages):
        try:
            from messenger import MessengerEntry
            icon = drawable(ICON_RES_PATH)
            for message in messages:
                html = format_message(message, icon, self._badges.markup(message.badges))
                MessengerEntry.g_instance.gui.addClientMessage(html)
        except Exception:
            _logger.exception('could not show a Twitch message in the battle chat')

    def _close(self):
        client, self._client = self._client, None
        self._channel = None
        self._opened = False
        if client is not None:
            try:
                client.listener.clear()
                client.terminate()
            except Exception:
                _logger.exception('could not close the Twitch chat connection')


def _battle_chat_shown():
    """Whether the battle chat is on screen: until then, BattleEntry drops client messages."""
    try:
        from messenger import MessengerEntry
        from messenger.m_constants import MESSENGER_SCOPE
        entry = MessengerEntry.g_instance.gui.getEntry(MESSENGER_SCOPE.BATTLE)
        view = getattr(entry, '_BattleEntry__view', None)
        return view is not None and view() is not None
    except Exception:
        return False


def _in_battle():
    try:
        from helpers import isPlayerAvatar
        return isPlayerAvatar()
    except Exception:
        return False


def install(session, settings, link=None):
    chat = TwitchChat(session, settings, link)
    chat.install()
    return chat


def _load_self():
    try:
        with open(SELF_STORE) as handle:
            appearance = json.load(handle)
        return appearance if isinstance(appearance, dict) else None
    except (IOError, OSError, ValueError):
        return None

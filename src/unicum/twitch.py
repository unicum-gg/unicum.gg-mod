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

settings.json: {"twitch": {"channel": "", "battleChat": true}}. With no
channel typed there, the one the player linked to their account on unicum.gg
(`twitchLogin` of GET /api/{region}/players/{nickname}) is followed. No
channel either way, no connection.
"""
import collections
import logging
import random
import re
import urllib

from unicum.twitch_badges import ChatBadges, drawable, parse_badges

_logger = logging.getLogger('unicum.twitch')

URL = 'wss://irc-ws.chat.twitch.tv:443'

# How often the connection is checked against the settings, and how long a
# lost one waits before trying again.
_CHECK_SECONDS = 2.0
_RETRY_SECONDS = 30.0

# Shown at most this many a tick, from a queue this long: a burst of chat
# neither floods the battle chat nor lags far behind it.
_FLUSH_SECONDS = 0.5
_PER_FLUSH = 2
_QUEUE = 10

# Kept for the garage, newest last.
_HISTORY = 50

_MAX_TEXT = 200

# The linked channel is asked for once a session; a failed answer again after
# this long. The player's page can take seconds to build when it is cold.
_LINKED_RETRY_SECONDS = 300.0
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

Message = collections.namedtuple('Message', 'name color text badges')
Message.__new__.__defaults__ = ((),)


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
    return 'message', Message(name, color, text, parse_badges(tags.get('badges')))


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


class ChatQueue(object):
    """What waits to be shown, and what the garage will show."""

    def __init__(self):
        self.pending = collections.deque(maxlen=_QUEUE)
        self.history = collections.deque(maxlen=_HISTORY)

    def add(self, message, in_battle):
        self.history.append(message)
        if in_battle:
            self.pending.append(message)

    def take(self):
        taken = []
        while self.pending and len(taken) < _PER_FLUSH:
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

    def __init__(self, session, settings):
        self._session = session
        self._settings = settings
        self._client = None
        self._channel = None
        self._opened = False
        self._retry_at = 0.0
        self._queue = ChatQueue()
        self._linked = LinkedChannel(session)
        self._badges = ChatBadges(session)

    @property
    def history(self):
        return list(self._queue.history)

    def install(self):
        self._session.repeat(_CHECK_SECONDS, self._check)
        self._session.repeat(_FLUSH_SECONDS, self._flush)
        self._session.on_close(self._close)
        _logger.info('installed')

    def _check(self):
        """Follow the channel the settings name: join it, change, or leave."""
        import BigWorld
        wanted = self._settings.twitch_channel()
        if not wanted and self._settings['enabled']:
            wanted = self._settings.twitch_channel(self._linked.get())
        if wanted != self._channel:
            self._close()
            self._retry_at = 0.0
        if not wanted or self._client is not None or BigWorld.time() < self._retry_at:
            return
        self._open(wanted)

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
            self._queue.add(value, _in_battle())

    def _flush(self):
        if not self._settings.shows_twitch_in_battle():
            self._queue.pending.clear()
            return
        taken = self._queue.take()
        if not taken:
            return
        try:
            from messenger import MessengerEntry
            icon = drawable(ICON_RES_PATH)
            for message in taken:
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


def _in_battle():
    try:
        from helpers import isPlayerAvatar
        return isPlayerAvatar()
    except Exception:
        return False


def install(session, settings):
    TwitchChat(session, settings).install()

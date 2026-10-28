"""The connection itself, and when it is allowed to say anything.

Holds the socket, reconnects it, and decides when a message may reach the
player: never during a replay, never while a battle is loading, and never at
all if the player turned the battle chat off. Everything about what a message
means is in `protocol`, and everything about which ones survive is in
`queueing`.
"""
from __future__ import absolute_import

import json
import logging
import random
import time

from unicum import config
from unicum.twitch_badges import ChatBadges, drawable
from unicum.twitch.protocol import (ICON_RES_PATH, Message, SELF_STORE,
                                    _load_self, appearance_of,
                                    format_message, own_message, parse_line)
from unicum.twitch.queueing import (_FLUSH_SECONDS, ChatQueue, EchoGuard,
                                    LinkedChannel)

_logger = logging.getLogger('unicum.twitch.chat')

URL = 'wss://irc-ws.chat.twitch.tv:443'

# How often the connection is checked against the settings, and how long a
# lost one waits before trying again.
_CHECK_SECONDS = 2.0
_RETRY_SECONDS = 30.0

# The battle's loading screen has a chat of its own, and `_battle_chat_shown`
# is already true while it is up: a message written there is thrown away with
# the screen, seconds before the player can read anything. So nothing is
# written until the screen is over (GameEvent.BATTLE_LOADING), and never
# longer than this, in case that event does not come in some mode -- losing
# the first seconds of a battle's chat is a bad day, losing all of it silently
# is a bug nobody would report.
_LOADING_HOLD = 60.0

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

"""What is held back, what is dropped, and which channel is ours.

Three small pieces of judgement that have nothing to do with the socket. The
echo guard drops the copy of our own message that Twitch sends back; the queue
holds a battle's worth of chat and gives up the oldest rather than growing
without a bound; and the linked channel is the one the player's unicum.gg
account names, asked for again on a timer because the link can be made while
the client is running.
"""
from __future__ import absolute_import

import collections
import logging
import time
import urllib

from unicum import config

_logger = logging.getLogger('unicum.twitch.queueing')

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

# The linked channel is asked for once a session; a failed answer again after
# this long. The player's page can take seconds to build when it is cold.
_LINKED_RETRY_SECONDS = 60.0
_LINKED_TIMEOUT = 30.0

def linked_url(api_base, region, nickname):
    return '%s/api/%s/players/%s' % (api_base.rstrip('/'), region, urllib.quote(nickname, safe=''))

def linked_channel(payload):
    """The Twitch login in a player's answer, or '' when they linked none."""
    from unicum.settings import twitch_channel
    return twitch_channel(payload.get('twitchLogin')) if isinstance(payload, dict) else ''

class LinkedChannel(object):
    """The Twitch channel the player linked on unicum.gg.

    Asked for until there is one. A player who has not linked Twitch gets a
    perfectly good answer saying so, and stopping there meant the question
    was never asked again: linking during the session changed nothing until
    the next start, and the hangar card kept offering Connect for a channel
    the site already knew about. Reported from Discord on 2026-09-24.
    """

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
            self._channel = linked_channel(payload)
            # Settled once there is a channel; until then the player may be
            # linking theirs right now, in a browser, with the game running.
            self._retry_at = None if self._channel else BigWorld.time() + _LINKED_RETRY_SECONDS
            _logger.info('linked Twitch channel: %s', self._channel or 'none')

        self._session.fetch(linked_url(config.API_BASE, config.REGION, nickname), done,
                            timeout=_LINKED_TIMEOUT)

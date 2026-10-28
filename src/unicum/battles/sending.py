"""The half of the reporter that puts battles on the wire.

A mixin rather than an object of its own, and the shared state is the reason:
the queue, the in-flight marks and the quiet-until stamp are read and written
by both halves, so threading them through a second object would be ceremony
without separation. What the split buys is a file that holds one subject, so
the pacing rules and the request that obeys them are read together.

The pacing is most of it. Every number here went in after a real failure, and
each says which one.
"""
from __future__ import absolute_import

import json
import logging
import time

from unicum import config
from unicum.battles.extract import _int
from unicum.battles.store import (_MAX_SETTLED, read_answer, save_queue,
                                  save_settled, settled)

_logger = logging.getLogger('unicum.battles.sending')

# The refusals the payload itself earned, which no retry will change.
#
# Only these two. Every other 4xx is about the request rather than the battles
# in it: a 401 while the session is being renewed, a 403 from something in
# front of the app, a 404 while a deploy moves the route. Treating those as
# the battles' fault would throw away good battles to recover from an outage,
# which is the opposite of the point.
#
#   400  the body was refused for what it says
#   413  the body was refused for how big it is, and one battle alone that is
#        still too big is one no batch size will ever carry
_PAYLOAD_FAULTS = (400, 413)

# Battles per request.
#
# Five rather than the twenty-five the endpoint accepts, and the measurement is
# why: a thirty-vehicle battle is 10.2 KB of JSON, so twenty-five of them would
# be a quarter of a megabyte in one call on a connection we know nothing about,
# and a failure would throw all of it away rather than a fifth of it. That is
# the same reasoning as the loadout upload's own batch, and the same numbers.
_BATCH = 5

# How often `flush` looks again while the garage is still building its space.
_WHILE_LOADING = 2.0

# How long it keeps looking before sending anyway.
#
# The results are what matter, which is this module's whole premise. Holding a
# battle report hostage to a graphics state would be a worse bug than the hitch
# the wait is there to avoid, so the wait gives up rather than wins.
_LOADING_DEADLINE = 30.0

# The least time between two flushes that actually sent something.
#
# Only a flush that reached the network counts, which is the fix for a real
# bug: the interval used to be stamped before the attempt, so the garage's
# flush at +12s consumed it and the battle's own at +25s was refused for the
# 13 seconds between them. The battle then waited for the next garage, which is
# after the next battle.
_MIN_INTERVAL = 60.0

# How long a flush may be in flight before another is allowed to start.
#
# `_busy` has callbacks for its only releases, and three paths never reach one.
# The worst is real rather than theoretical: the WGNI token requester is a
# process-wide singleton with ONE callback slot (TokenRequester.py), shared
# with the loadout upload and the client's own portal code, and whoever asks
# last overwrites the pending callback AND cancels the timeout that would have
# rescued it. Without a deadline here, one unlucky overlap stopped this client
# sending battles until the next reload, silently, while its queue filled up
# and started dropping the oldest.
_BUSY_DEADLINE = 90.0

# How long to stay quiet after the server says the quota is spent.
#
# Without this, every garage restarted the same burst against a server that
# had just said no, and the queue never drained. The server's own Retry-After
# is preferred when it sends one.
_QUOTA_BACKOFF = 900.0

def garage_ready():
    """Whether the garage has finished building its 3D space.

    The client's own account of it, read off `IHangarSpace.spaceInited`, which
    turns true in the callback the space's own `create` is handed. Asked rather
    than waited out, because the thing worth staying out of is a state, not a
    duration, and every duration long enough for the slowest machine is wrong
    on all the others.

    True when it cannot be read at all. A service that is not there is no reason
    to keep a battle for ever, and `flush`'s own `isPlayerAccount` has already
    established that we are somewhere a send belongs.
    """
    try:
        from helpers import dependency
        from skeletons.gui.shared.utils import IHangarSpace
        return bool(dependency.instance(IHangarSpace).spaceInited)
    except Exception:
        return True

def _said(body):
    """What the server put in the body of a refusal, short enough to log.

    The status code alone was not enough: a 400 repeated for a whole evening
    without once saying which field the server disliked, while the body was
    carrying the `{error: ...}` that names it the entire time.
    """
    try:
        text = body if isinstance(body, str) else str(body)
    except Exception:
        return 'no body'
    text = ' '.join(text.split())
    if not text:
        return 'empty body'
    return text[:300] + ('...' if len(text) > 300 else '')


def _seconds(headers):
    """The server's own Retry-After in seconds, or None."""
    if not isinstance(headers, dict):
        return None
    for key, value in headers.items():
        if str(key).lower() == 'retry-after':
            seconds = _int(value, 0)
            return seconds if 0 < seconds <= 86400 else None
    return None


class Sending(object):
    """The queue and the wire; see the module docstring."""

    def _free(self, now):
        """Whether no flush is in flight, or the one that is has run too long."""
        if self._busy_since is None:
            return True
        if now - self._busy_since < _BUSY_DEADLINE:
            return False
        _logger.warning('a flush has been in flight for %.0fs with no answer; '
                        'starting another', now - self._busy_since)
        return True

    def flush(self):
        """Send what is waiting, a batch at a time."""
        if not self._queue or not self._sends():
            return
        now = time.time()
        if not self._free(now):
            return
        if now < self._quiet_until:
            return
        if now - self._last_flush < _MIN_INTERVAL:
            return
        try:
            from helpers import isPlayerAccount
            if not isPlayerAccount():
                return
        except ImportError:
            return
        if not garage_ready():
            # Still building the 3D space, which is the one moment in the client
            # worth staying out of. Looked at again rather than waited out, and
            # given up on rather than waited for: see `_LOADING_DEADLINE`.
            if self._loading_since is None:
                self._loading_since = now
            if now - self._loading_since < _LOADING_DEADLINE:
                self._session.callback(_WHILE_LOADING, self.flush)
                return
            _logger.info('the garage has not finished loading in %.0fs; '
                         'sending anyway', now - self._loading_since)
        self._loading_since = None
        self._busy_since = now
        self._post()

    def _done(self):
        self._busy_since = None

    def _blame(self, batch, code, said):
        """A refusal the payload earned, which no later garage will change.

        The queue is the only copy of a battle not yet placed, so nothing here
        drops a battle without first pinning the refusal on it. With more than
        one battle in the request any of them could be the cause and the rest
        are hostages, so the batch narrows to one: that names the battle at
        fault in at most as many requests as the batch held. Alone and still
        refused, a battle will never be accepted by anyone, and keeping it
        would hold up every battle queued behind it for good. That is not a
        hypothetical: thirty-five battles waited a day behind one.
        """
        if len(batch) > 1:
            self._batch = 1
            _logger.warning('the server refused a batch of %d on HTTP %s: %s; '
                            'sending them one at a time to find out which',
                            len(batch), code, said)
            self._post()
            return

        name = batch[0].get('arenaUniqueId')
        _logger.error('battle %s was refused on its own on HTTP %s: %s; '
                      'dropping it, because it would otherwise hold up every '
                      'battle behind it', name, code, said)
        self._queue = settled(self._queue, [name])
        save_queue(self._queue)
        if name is not None:
            # Written down as settled so it is never declared again. A battle
            # with no id at all is only taken off the queue: there is nothing
            # to remember it by, and `None` in here would match the next one.
            self._settled = (self._settled + [name])[-_MAX_SETTLED:]
            save_settled(self._settled)
            if self._replays is not None:
                # Its replay will never be taken either: a file offered for a
                # battle that has no row comes back `unknown_battle`.
                try:
                    self._replays.disown([name])
                except Exception:
                    _logger.exception('could not tell the replay archive about '
                                      'the battle that was dropped')
        self._batch = _BATCH
        if self._queue:
            self._post()
        else:
            self._done()

    def _post(self):
        # Re-read every batch: unticking the box has to stop the flush that is
        # already running, not only the next one. A full queue is forty calls.
        if not self._sends():
            _logger.info('battle sharing turned off; %d battle(s) stay on disk',
                         len(self._queue))
            self._done()
            return
        batch = self._queue[:self._batch]
        if not batch:
            self._done()
            return
        body = json.dumps({'battles': batch})

        def answered(response):
            code = getattr(response, 'responseCode', None)
            if code == 429:
                # Back off rather than come straight back at the next garage,
                # which is what turned a spent quota into a permanent burst.
                wait = _seconds(getattr(response, 'responseHeaders', None)) or _QUOTA_BACKOFF
                self._quiet_until = time.time() + wait
                self._done()
                _logger.warning('the server is rate limiting us; quiet for %.0fs, '
                                '%d battle(s) still waiting', wait, len(self._queue))
                return
            if code in _PAYLOAD_FAULTS:
                self._blame(batch, code, _said(getattr(response, 'body', None)))
                return
            if code != 200:
                # Kept, not dropped: a battle a network refused is one the next
                # garage sends.
                self._done()
                _logger.warning('battle upload stopped on HTTP %s: %s; %d still waiting',
                                code, _said(getattr(response, 'body', None)),
                                len(self._queue))
                return
            answer = read_answer(getattr(response, 'body', None))
            if answer is None:
                # A 200 carrying something that is not our answer. Nothing is
                # named, so nothing is forgotten.
                self._done()
                _logger.warning('the server answered 200 with something that is not '
                                'an upload result; %d battle(s) kept',
                                len(self._queue))
                return
            stored, known, refused = answer
            # Exactly what was named, and nothing else.
            names = list(stored) + list(known) + [id_ for id_, _ in refused]
            if not names:
                self._done()
                _logger.warning('the server named no battle at all; %d kept',
                                len(self._queue))
                return
            # The server took a request, so whatever narrowed the batch is
            # behind us and the next one can carry a full load again.
            self._batch = _BATCH
            self._queue = settled(self._queue, names)
            self._settled = (self._settled + names)[-_MAX_SETTLED:]
            save_queue(self._queue)
            save_settled(self._settled)
            if self._replays is not None:
                # The server has spoken, so the replays of these battles can
                # finally be looked for: a file offered before its own battle
                # is refused with `unknown_battle`, and the archive used to
                # read that as a verdict and delete the player's only copy.
                #
                # `stored` and `known` only. A refused battle will never have a
                # row, so its replay is told to go rather than left to be
                # offered and refused until its own bound runs out.
                try:
                    self._replays.confirm(list(stored) + list(known))
                    if refused:
                        self._replays.disown([id_ for id_, _ in refused])
                except Exception:
                    _logger.exception('could not tell the replay archive which '
                                      'battles the server named')
            if refused:
                _logger.warning('%d battle(s) refused for good: %s', len(refused),
                                ', '.join('%s %s' % pair for pair in refused))
            _logger.info('%d stored, %d already known, %d waiting',
                         len(stored), len(known), len(self._queue))
            if self._queue:
                self._post()
            else:
                self._done()

        self._last_flush = time.time()
        self._request('%s/api/game/battles' % config.API_BASE.rstrip('/'), answered,
                      method='POST', post_data=body)

    def _request(self, url, answered, method='GET', post_data=''):
        """Signed with whatever proves this account, and nothing if neither does.

        The same two proofs as the loadout upload: the link's secret when the
        player has one, otherwise the client's own WGNI web token, which
        unicum.gg has Wargaming confirm. A battle is a statement about thirty
        accounts and the server checks that this one is among them, which it
        can only do if it knows which account is speaking.
        """
        secret = getattr(self._link, 'secret', None)
        if secret:
            self._fetch(url, answered, {'Authorization': 'Bearer %s' % secret},
                        method, post_data)
            return

        def with_token(response):
            if not (response and response.isValid()):
                _logger.info('no web token; battles wait for the next garage')
                self._done()
                return
            self._fetch(url, answered, {
                'X-Wargaming-Token': str(response.getToken()),
                'X-Wargaming-Region': config.REGION,
            }, method, post_data)

        try:
            from constants import TOKEN_TYPE
            from gui.shared.utils.requesters import getTokenRequester
            requester = getTokenRequester(TOKEN_TYPE.WGNI)
            if requester.isInProcess():
                # Somebody else holds the singleton's one callback slot. The
                # deadline in `_free` is what makes this recoverable rather
                # than final.
                self._done()
                return
            requester.request(timeout=10.0)(with_token)
        except Exception:
            _logger.exception('could not ask for a web token')
            self._done()

    def _fetch(self, url, answered, headers, method, post_data):
        headers = dict(headers)
        headers['Content-Type'] = 'application/json'
        self._session.fetch(url, answered, headers=headers,
                            timeout=config.API_TIMEOUT, method=method,
                            post_data=post_data)

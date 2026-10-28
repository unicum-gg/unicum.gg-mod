"""The half of the uploader that puts a replay on the wire.

A mixin rather than an object of its own, for the reason the battles package
gives: the queue, the failure counts and the quiet-until stamp are read and
written by both halves.

Two things decide the shape of every request here. The body goes out base64
inside JSON, because `fetchURL`'s binary safety is documented nowhere and a
replay is full of zero bytes; and one request carries at most 8000000 bytes of
body, measured against a listener on the loopback, so a longer replay is sent
in pieces the server parks until the last turns up.
"""
from __future__ import absolute_import

import base64
import hashlib
import json
import logging
import os
import time

from unicum import config
from unicum.replays.store import QUEUE, forget, read_answer, save_queue

_logger = logging.getLogger('unicum.replays.sending')

#: The least time between two uploads. One file is 1.7 MB encoded.
_MIN_INTERVAL = 20.0

# The most the game's own HTTP layer will put on the wire, in bytes of body.
#
# MEASURED, against a listener on the loopback so that nothing stood between
# the two: 8000000 arrives whole, 8000001 arrives as a request with its
# headers, no body and no declared length, and no error on the way out. The
# server then answers `invalid_body`, which is exactly right from where it
# sits -- it really was handed an empty request -- and reads from here like
# the body was rejected rather than never sent. A round decimal number, not a
# power of two, which is why guessing at 8 MiB would have been wrong.
_MAX_POST_BYTES = 8000000

# `{"replay":"<base64>","sha256":"<64 hex>"}` around the file, and base64
# costs four bytes for every three. What is left is how big the file itself
# may be, about 5.7 MiB.
_ENVELOPE = len('{"replay":"","sha256":"%s"}' % ('0' * 64))
_MAX_PART_BYTES = ((_MAX_POST_BYTES - _ENVELOPE) // 4) * 3

# A replay longer than one request is sent in pieces, which the server parks
# beside the replay until the last turns up and then puts back together. Four
# is what the server accepts, and it is twice the twelve megabytes a replay is
# allowed to be in the first place.
_MAX_PARTS = 4
_MAX_REPLAY_BYTES = _MAX_PART_BYTES * _MAX_PARTS

#: How long a flush may be unanswered before another is allowed to start.
_BUSY_DEADLINE = 120.0

#: And when it rate limits us without saying for how long.
_QUOTA_BACKOFF = 900.0


class Sending(object):
    """The wire; see the module docstring."""

    def _free(self, now):
        if self._busy_since is None:
            return True
        if now - self._busy_since < _BUSY_DEADLINE:
            return False
        _logger.warning('a replay upload has been in flight for %.0fs; starting another',
                        now - self._busy_since)
        return True

    def flush(self):
        if not self._queue or not self._sends():
            return
        now = time.time()
        if not self._free(now) or now < self._quiet_until:
            return
        if now - self._last_flush < _MIN_INTERVAL:
            return
        try:
            from helpers import isPlayerAccount
            if not isPlayerAccount():
                return
        except ImportError:
            return
        self._busy_since = now
        self._post()

    def _done(self):
        self._busy_since = None

    def _post(self):
        if not self._sends() or not self._queue:
            self._done()
            return
        entry = self._next()
        if entry is None:
            self._done()
            return
        try:
            with open(entry['file'], 'rb') as handle:
                data = handle.read()
        except (IOError, OSError):
            # Our own copy is gone. Nothing to send and nothing to keep.
            _logger.warning('the copy for battle %s is unreadable; dropping it',
                            entry.get('arenaUniqueId'))
            self._queue.pop(0)
            save_queue(self._queue)
            self._done()
            return

        if len(data) > _MAX_REPLAY_BYTES:
            # Past what even four requests can carry, so it is said once and
            # let go of rather than carried around the queue for ever.
            _logger.warning('the replay of battle %s is %d KB, past the %d KB that '
                            '%d requests can carry; letting it go',
                            entry.get('arenaUniqueId'), len(data) // 1024,
                            _MAX_REPLAY_BYTES // 1024, _MAX_PARTS)
            forget(entry)
            self._queue = [row for row in self._queue if row is not entry]
            save_queue(self._queue)
            self._done()
            return

        parts = (len(data) + _MAX_PART_BYTES - 1) // _MAX_PART_BYTES
        self._send_part(entry, data, 0, max(1, parts))

    def _send_part(self, entry, data, index, parts):
        """One piece of a replay, and the next once the server has this one.

        Sent one at a time rather than all at once: the game's HTTP layer
        carries 8000000 bytes of body and no more, and a piece that failed
        while its siblings were in flight would leave the server holding half
        a file with nobody to say so.

        The hash is the WHOLE file's on every piece. It is what the server
        checks once it has put the pieces back together, and sending it with
        each one means a piece carries its own proof of what it belongs to.
        """
        start = index * _MAX_PART_BYTES
        piece = data[start:start + _MAX_PART_BYTES]
        body = json.dumps({
            'replay': base64.b64encode(piece).decode('ascii'),
            'sha256': hashlib.sha256(data).hexdigest(),
        })

        def answered(response):
            code = getattr(response, 'responseCode', None)
            # A piece that is not the last is acknowledged and nothing else:
            # the server has parked it and is waiting for its siblings.
            if code == 200 and index < parts - 1:
                _logger.info('replay for battle %s: piece %d of %d is in',
                             entry.get('arenaUniqueId'), index + 1, parts)
                self._send_part(entry, data, index + 1, parts)
                return
            if code == 429:
                wait = _QUOTA_BACKOFF
                self._quiet_until = time.time() + wait
                self._done()
                _logger.warning('rate limited on replays; quiet for %.0fs', wait)
                return
            if code != 200:
                # Kept. A network that refused one upload is one the next
                # garage retries, and 422 (the body arrived damaged) is
                # precisely a case where the copy on disk is still good.
                self._done()
                # The code alone does not say which refusal it is: 400 is
                # both a missing `startedAt` and a body the server could not
                # read, and the two are fixed in different places.
                said = getattr(response, 'body', None)
                _logger.warning('replay upload stopped on HTTP %s for battle %s '
                                '(%d KB), %d still waiting; said %r',
                                code, entry.get('arenaUniqueId'), len(data) // 1024,
                                len(self._queue),
                                said[:200] if isinstance(said, basestring) else said)
                self._set_aside(entry, code)
                return
            answer = read_answer(getattr(response, 'body', None))
            if answer is None:
                self._done()
                _logger.warning('the server answered 200 with something that is not '
                                'a replay result; %d copy(ies) kept', len(self._queue))
                return
            kind, detail = answer
            if kind == 'refused' and detail in self.CLOSED:
                self._drop_all(detail)
                return
            if kind == 'refused' and detail in self.PENDING:
                self._retry(entry, detail)
                return
            if kind == 'refused' and detail in self.RETAKE:
                self._wrong_copy(entry)
                return
            if kind == 'stored' or detail in self.FINAL:
                forget(entry)
                self._queue = [row for row in self._queue
                               if row.get('arenaUniqueId') != entry.get('arenaUniqueId')]
                save_queue(self._queue)
                _logger.info('replay for battle %s %s, %d waiting',
                             entry.get('arenaUniqueId'),
                             'stored' if kind == 'stored' else detail,
                             len(self._queue))
                if self._queue:
                    self._post()
                else:
                    self._done()
                return
            # A refusal we have not met. Kept rather than guessed at.
            self._done()
            _logger.warning('replay for battle %s refused with an unknown reason (%s); kept',
                            entry.get('arenaUniqueId'), detail)

        self._last_flush = time.time()
        url = '%s/api/game/battles/%s/replay?startedAt=%d' % (
            config.API_BASE.rstrip('/'), entry['arenaUniqueId'],
            int(entry.get('startedAt') or 0))
        if parts > 1:
            # Left off entirely for a whole file, so a server that has never
            # heard of pieces answers the only question it knows.
            url += '&part=%d&parts=%d' % (index, parts)
        self._request(url, answered, body)

    def _request(self, url, answered, body):
        """Signed the same two ways the battle upload is signed."""
        secret = getattr(self._link, 'secret', None)
        if secret:
            self._fetch(url, answered, {'Authorization': 'Bearer %s' % secret}, body)
            return

        def with_token(response):
            if not (response and response.isValid()):
                _logger.info('no web token; replays wait for the next garage')
                self._done()
                return
            self._fetch(url, answered, {
                'X-Wargaming-Token': str(response.getToken()),
                'X-Wargaming-Region': config.REGION,
            }, body)

        try:
            from constants import TOKEN_TYPE
            from gui.shared.utils.requesters import getTokenRequester
            requester = getTokenRequester(TOKEN_TYPE.WGNI)
            if requester.isInProcess():
                self._done()
                return
            requester.request(timeout=10.0)(with_token)
        except Exception:
            _logger.exception('could not ask for a web token')
            self._done()

    def _fetch(self, url, answered, headers, body):
        headers = dict(headers)
        headers['Content-Type'] = 'application/json'
        # Longer than the API default: this body is 1.7 MB where every other
        # call the mod makes is a few KB, and a timeout here costs a replay
        # that no retry can recreate once the client has overwritten it.
        self._session.fetch(url, answered, headers=headers,
                            timeout=max(config.API_TIMEOUT, 60.0),
                            method='POST', post_data=body)

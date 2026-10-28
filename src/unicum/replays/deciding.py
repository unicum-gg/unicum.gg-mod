"""Which copy goes next, and which one is finally let go of.

Every rule here was put in after a real replay was lost or a queue stalled,
and each says which. The four answer sets the server can give are read by
name in `Uploader`, because what to do with a refusal is the only judgement
in this whole path that cannot be guessed from the words.
"""
from __future__ import absolute_import

import logging
import os
import time

from unicum.replays.files import battle_in, find
from unicum.replays.store import forget, save_queue, save_wanted

_logger = logging.getLogger('unicum.replays.deciding')

# How many times a copy may be refused before the rest of the queue is let
# past it. ONE, because trying the same copy again in the same minute asks
# the same server the same question: the point is not to give up on it, it is
# to stop one copy holding everything else hostage. It comes back round after
# the others have had their turn, which is retry enough.
_MAX_FAILURES = 1

#: How long to stay quiet when the server says it keeps no replays, or that its
#: archive is full. Both are "stop asking", not "try again shortly".
_CLOSED_BACKOFF = 86400.0

# How long a copy waits to be named by the server before it is let go of.
#
# A copy is made as soon as the file exists but only OFFERED once the battle has
# been named, so a battle the server never names leaves a copy nothing will ever
# send. A try counter cannot bound that: nothing counts an upload that never
# happens. The deadline is read off the copy's own `startedAt`, which it already
# carries, so it survives a restart for free.
#
# Twelve hours. The reporter's record of answered ids is capped at five hundred,
# so a confirmation really can be missed outright, and this is the backstop for
# exactly that.
_CONFIRM_DEADLINE = 12 * 3600.0

# How many times one copy is offered for a battle the server does not have.
#
# Six, against a collection that runs once per garage: a file survives a
# whole evening of the server being behind, and is still let go of if its
# battle genuinely never lands (results refused for good, a row removed).
_MAX_TRIES = 6


class Deciding(object):
    """Which copy goes next, and which is let go of."""

    def _next(self):
        """The first copy whose battle the server has said it holds.

        Not `self._queue[0]`. A copy is kept from the moment its file exists,
        but offered only once the battle has been named, so the queue holds
        copies in both states at once and its head is quite often the one that
        cannot go yet. Taking the head regardless would park every confirmed
        copy behind one unconfirmed battle until that battle's own deadline.

        Copies nobody ever names are let go of here, on their `startedAt`,
        because `_retry`'s counter only ever sees uploads that happened.
        """
        now = time.time()
        chosen = None
        stale = []
        for entry in self._queue:
            if str(entry.get('arenaUniqueId')) in self._known:
                if chosen is None:
                    chosen = entry
            elif now - int(entry.get('startedAt') or 0) > _CONFIRM_DEADLINE:
                stale.append(entry)
        for entry in stale:
            forget(entry)
            self._queue.remove(entry)
            _logger.info('battle %s was never named by the server in %.0fh; '
                         'dropping its copy', entry.get('arenaUniqueId'),
                         _CONFIRM_DEADLINE / 3600.0)
        if stale:
            save_queue(self._queue)
        return chosen

    def _wrong_copy(self, entry):
        """This copy holds another battle. Drop it and look for the right file.

        The copy is genuinely wrong, so it goes; but the BATTLE is still owed,
        and the file may well still be on disk under another name. Letting the
        want go here is what made this permanent: the client rewrites
        `replay_last_battle.wotreplay` between the moment `find` reads the id
        out of it and the moment `stash` copies it, so the copy can be of the
        next battle. `stash` checks for that now, and this is the net for a copy
        that was already taken before it did.

        The next pass either finds the right file or finds nothing, says so and
        forgets it, so this cannot loop.
        """
        arena_id = str(entry.get('arenaUniqueId'))
        forget(entry)
        self._queue = [row for row in self._queue
                       if str(row.get('arenaUniqueId')) != arena_id]
        started = int(entry.get('startedAt') or 0)
        if started:
            self._wanted[arena_id] = started
            save_wanted(self._wanted)
        save_queue(self._queue)
        _logger.info('the copy for battle %s was of another battle; dropped, '
                     'and the file is wanted again', arena_id)
        self._done()

    def _set_aside(self, entry, code):
        """Let the rest of the queue past a copy the server keeps refusing.

        Keeping a copy after a failure is right: a network that refused one
        upload is one the next garage retries. What was wrong is that
        `_next` picks the FIRST confirmed copy every time, so a copy that
        fails every time is picked every time, and everything behind it waits
        on a battle that is never going up. One replay the server would not
        take stopped twelve from being sent, and the only sign of it was the
        player noticing their profile had no recent battles.

        The copy goes to the back rather than being dropped: the refusal may
        be the server's to fix, and the file costs a megabyte on disk.
        """
        failures = int(entry.get('failures') or 0) + 1
        entry['failures'] = failures
        if failures < _MAX_FAILURES:
            save_queue(self._queue)
            return
        entry['failures'] = 0
        # By identity: two copies could compare equal as dicts.
        self._queue = [row for row in self._queue if row is not entry]
        self._queue.append(entry)
        _logger.warning('battle %s refused %d times (HTTP %s); the other %d go first',
                        entry.get('arenaUniqueId'), failures, code, len(self._queue) - 1)
        save_queue(self._queue)

    def _retry(self, entry, why):
        """Keep this copy: the server does not have its battle yet.

        Nothing is sent again in this pass. Asking twice in the same second
        puts the same question to the same server and earns the same answer,
        so the bound would be spent before the battle had any chance to
        arrive. The next attempt comes from the reporter naming the battle,
        which schedules a collection within seconds of the results landing,
        and failing that from the next garage.

        With collection now waiting for that same confirmation this should be
        a dead branch. It is the net under it: a copy queued by an older
        version of this module, a confirmation that turned out to be about a
        row since removed.
        """
        tries = int(entry.get('tries') or 0) + 1
        # The entry is the queue's own dict, so this is the stored count.
        entry['tries'] = tries
        if tries >= _MAX_TRIES:
            forget(entry)
            self._queue = [row for row in self._queue
                           if row.get('arenaUniqueId') != entry.get('arenaUniqueId')]
            _logger.warning('battle %s was still %s after %d tries; dropping '
                            'its copy, %d waiting', entry.get('arenaUniqueId'),
                            why, tries, len(self._queue))
        else:
            # To the back. The queue is always drained from the front, so one
            # battle the server may never have would otherwise hold up every
            # copy behind it until its sixth try.
            self._queue.remove(entry)
            self._queue.append(entry)
            _logger.info('battle %s is not on the server yet (%s, try %d of '
                         '%d); its copy is kept', entry.get('arenaUniqueId'),
                         why, tries, _MAX_TRIES)
        save_queue(self._queue)
        self._done()

    def _drop_all(self, why):
        """Forget every pending file, and stop asking for a day."""
        _logger.info('the server keeps no replays (%s); dropping %d copy(ies)',
                     why, len(self._queue))
        for entry in self._queue:
            forget(entry)
        self._queue = []
        self._wanted = {}
        save_wanted(self._wanted)
        self._quiet_until = time.time() + _CLOSED_BACKOFF
        save_queue(self._queue)
        self._done()

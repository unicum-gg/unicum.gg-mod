"""When a replay is collected, and what the battle report tells it.

Collection runs at the garage and reads the newest few files, because the file
wanted was written moments ago. Offers wait for the battle itself to be named
by the server: a replay offered before its own battle earns `unknown_battle`,
which is not a verdict on the replay but a statement about when we asked.
"""
from __future__ import absolute_import

import logging
import os
import time

from unicum.replays.deciding import Deciding
from unicum.replays.files import candidates, find
from unicum.replays.sending import Sending
from unicum.replays.store import (_MAX_QUEUED, forget, load_queue,
                                  load_wanted, save_queue, save_wanted, stash)

_logger = logging.getLogger('unicum.replays.uploader')

#: Seconds after reaching the garage before anything is collected or sent.
#:
#: Later than the results flush on purpose: the results are what matter, and
#: the garage is already the busiest moment in the client.
_START_DELAY = 40.0

# How long after the battle is confirmed before its file is looked for.
#
# Not `_START_DELAY`. That one is forty seconds because the garage is the
# busiest moment in the client and the results are what matter; a
# confirmation arrives twenty-five seconds after the results, which is itself
# well after the garage has finished drawing, so the reason for waiting has
# already passed. Borrowing it put seventy seconds between the end of a
# battle and its replay being readable, for no reason anybody could name.
#
# And the work is small: measured on a real 0.97 MB replay under the client's
# own Python, 1 ms to read, 5 ms to base64, 2 ms to hash. Eight milliseconds,
# half a frame. Three seconds is only to get off the answer handler's own
# stack, not to spare the client anything.
_AFTER_CONFIRMED = 3.0


class Uploader(Sending, Deciding):
    """Collects the file of each battle at the garage, and sends it."""

    #: Answers that mean this battle will never be wanted. The copy goes.
    FINAL = ('already_stored', 'not_a_player')
    #: Answers that mean no battle will be wanted for a while. Everything goes.
    CLOSED = ('not_collected', 'archive_full')
    #: Answers that only mean "not yet". The copy is kept and offered again.
    #
    # `unknown_battle` used to sit in FINAL, which is the bug this tuple
    # exists to fix. It is not a verdict on the battle, it is a statement
    # about WHEN we asked: the results are queued and sent on a timer that
    # starts when they land, the replay on one that starts at the garage, so
    # the replay normally asks first. Measured on one real session, the
    # replay arrived 17s, 2s and 2s before its own battle, and the one time
    # it won it won by 137ms. Deleting the player's only copy on the strength
    # of a tenth of a second lost three battles in one evening.
    PENDING = ('unknown_battle',)
    #: Answers that condemn the COPY but not the battle. Look again.
    #
    # `not_this_battle` means the bytes we sent hold another battle, which
    # is true and is our own doing: the client rewrites
    # `replay_last_battle.wotreplay` between the moment the id is read out
    # of it and the moment it is copied. The copy is wrong, the battle is
    # still owed, and the right file may still be on disk. It sat in FINAL,
    # so a copy taken a second too late lost the replay for good: battle
    # 90570953574329799 was refused at 01:19:07 and only stored at 01:38:42
    # because the battle happened to be reported a second time.
    RETAKE = ('not_this_battle',)

    def __init__(self, session, settings, link):
        self._session = session
        self._settings = settings
        self._link = link
        self._queue = load_queue()
        # Battles whose results have been reported but whose file has not been
        # looked for yet: {arenaUniqueId: startedAt}. Read back from disk, so a
        # client closed between the battle and the garage still collects it.
        self._wanted = load_wanted()
        # The battles the server has said it holds, told to us by the battle
        # reporter. Deliberately NOT persisted: the reporter reads its own
        # record of answered ids off disk at install and hands it straight
        # back, so a second copy here would be the same truth kept twice and
        # the two would disagree the first time one of them was not written.
        self._known = set()
        self._busy_since = None
        self._quiet_until = 0.0
        self._last_flush = 0.0

    def install(self):
        try:
            from PlayerEvents import g_playerEvents
            self._session.subscribe(g_playerEvents.onAccountShowGUI, self._on_garage)
        except ImportError:
            _logger.exception('no player events; replays are not collected')
            return
        # The garage may already be up: `onAccountShowGUI` fires when it
        # appears, so a module installed after that (every dev reload) would
        # hold what it is owed until the player next came back from a battle.
        self._session.callback(_START_DELAY, self._collect)
        _logger.info('installed, %d replay(s) waiting, %d wanted',
                     len(self._queue), len(self._wanted))

    def offer(self, arena_id, started_at):
        """Told by the battle reporter that this battle has been written down.

        Only remembered here. The file is not looked for until the garage: the
        client is still finishing the results screen, and reading a megabyte
        off disk on the thread that draws the game is not something to do while
        an animation is running.
        """
        if not arena_id or not started_at:
            return
        self._wanted[str(arena_id)] = int(started_at)
        save_wanted(self._wanted)

    def confirm(self, arena_ids):
        """Told which battles the server says it holds. Collection waits for this.

        A replay offered before its own battle earns `unknown_battle`, which is
        the server answering honestly about a row that does not exist yet. The
        file is good; only the question was early. So the file is not looked
        for at all until the reporter has heard the battle named, which turns a
        race decided by a tenth of a second into an order.

        Called with the whole record at install as well as with each answer,
        because the gap this closes is exactly the one a restart opens: a
        battle settled in a previous session is in no queue any more and will
        never be named again.
        """
        fresh = set(str(one) for one in arena_ids if one)
        if not fresh:
            return
        self._known |= fresh
        # `flush`, not `_collect`. The copy is made at the garage whatever the
        # server knows, because the client overwrites `replay_last_battle` with
        # the next battle and a copy that waited would be a copy of the wrong
        # battle or of nothing. Only the offer waits for this, so what a
        # confirmation unblocks is the sending.
        #
        # A battle confirmed before its copy exists needs no nudge: `_collect`
        # ends with its own `flush`, and by then this id is in `_known`.
        if any(str(row.get('arenaUniqueId')) in fresh for row in self._queue):
            try:
                self._session.callback(_AFTER_CONFIRMED, self.flush)
            except Exception:
                _logger.exception('could not schedule the replay upload')

    def disown(self, arena_ids):
        """Told which battles the server refused for good. Their files go.

        Kept apart from `confirm` on purpose. Both mean the server has spoken,
        but a refused battle will never have a row, so its replay would be
        offered six times and dropped on the sixth. Saying so now costs one
        line and saves six megabytes of upload.
        """
        gone = set(str(one) for one in arena_ids if one)
        if not gone:
            return
        for arena_id in [key for key in self._wanted if key in gone]:
            del self._wanted[arena_id]
            _logger.info('battle %s was refused for good; its replay is no '
                         'longer wanted', arena_id)
        for entry in [row for row in self._queue
                      if str(row.get('arenaUniqueId')) in gone]:
            forget(entry)
            self._queue.remove(entry)
        save_wanted(self._wanted)
        save_queue(self._queue)

    def _sends(self):
        try:
            return self._settings.sends_replays()
        except Exception:
            _logger.exception('could not read the replay setting')
            return False

    def _on_garage(self, *args):
        try:
            self._session.callback(_START_DELAY, self._collect)
        except Exception:
            _logger.exception('could not schedule the replay collection')

    def _collect(self):
        """Find and copy the files of the battles we were told about."""
        if not self._sends():
            self._wanted = {}
            save_wanted(self._wanted)
            return
        if time.time() < self._quiet_until:
            # KEPT, not forgotten. This branch is reached after a 429, which
            # means "ask again later" and nothing else: the files are still on
            # disk and the battles still want their replay. Emptying the list
            # here threw away every pending replay on the first rate limit,
            # and the quiet period is 15 minutes, so what was discarded was
            # whatever the player had just played.
            #
            # The case that DOES mean forget is a server that keeps no
            # replays at all, and `_drop_all` says so itself: it clears the
            # list and sets a day of quiet in the same breath.
            return
        # Listed once for the whole pass rather than once per battle: the
        # newest files on disk do not change while we read their headers.
        newest = candidates()
        for arena_id, started_at in list(self._wanted.items()):
            del self._wanted[arena_id]
            if any(row.get('arenaUniqueId') == arena_id for row in self._queue):
                continue
            source = find(arena_id, newest)
            if source is None:
                # No file. By far the commonest outcome and not a failure: the
                # player may have recording off entirely.
                _logger.info('no replay on disk for battle %s', arena_id)
                continue
            target = stash(arena_id, source)
            if target is None:
                continue
            while len(self._queue) >= _MAX_QUEUED:
                dropped = self._queue.pop(0)
                _logger.warning('replay queue full at %d; dropping %s',
                                _MAX_QUEUED, dropped.get('arenaUniqueId'))
                forget(dropped)
            self._queue.append({'arenaUniqueId': arena_id,
                                'startedAt': started_at,
                                'file': target})
            _logger.info('replay kept for battle %s, %d waiting',
                         arena_id, len(self._queue))
        save_wanted(self._wanted)
        save_queue(self._queue)
        self.flush()

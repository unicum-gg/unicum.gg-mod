"""The reporter itself: what it hooks, and what it makes of what it hears.

Holds the two halves together and keeps for itself the three things that are
neither sending nor claiming: the patch on the client's own results, turning
a set of results into a queued battle, and writing down each battle's id as
it starts.
"""
from __future__ import absolute_import

import logging
import time

from unicum.battles.claiming import Claiming
from unicum.battles.extract import _int, payload
from unicum.battles.naming import arena_names, full_version
from unicum.battles.sending import Sending
from unicum.battles.store import (_MAX_QUEUED, append_queued, load_played,
                                  load_queue, load_settled, queued,
                                  save_played, save_settled)

_logger = logging.getLogger('unicum.battles.reporter')

# How long after the garage appears the queue is flushed. The garage has a
# sign-in, a carousel and the rest of this mod to draw first, and a battle
# that has already waited for the player to leave the results screen is not
# urgent.
_START_DELAY = 12.0

# How long after a battle's results land before trying to send it.
#
# Three seconds, and only to get off the stack of the screen that delivered
# them. It was twenty-five, to let the client finish drawing, and that number
# was both too big and aimed at the wrong thing: the garage finishes building
# its space BEFORE the results arrive, measured on a real session at 15:17:31
# against 15:17:53, so by the time the twenty-five seconds began the heavy part
# was already over. A stopwatch long enough for the slowest machine is also one
# that holds every other machine back, and it held a replay back with it, since
# the file is not collected until its battle has been named.
#
# What the wait was for is asked instead of timed now, in `flush`.
_SEND_DELAY = 3.0


class Reporter(Sending, Claiming):
    """Follows the client's battles and sends them on."""

    def __init__(self, session, settings, link, motion=None, replays=None):
        self._session = session
        self._settings = settings
        self._link = link
        # Where everybody was, sampled by `motion` while the battle ran. Absent
        # when that module could not install, which costs the replay view and
        # nothing else.
        self._motion = motion
        # Told about each battle written down, so it can look for the client's
        # own `.wotreplay` at the next garage. Absent is the ordinary case for
        # anyone whose client keeps no replays, and costs nothing else.
        self._replays = replays
        self._queue = load_queue()
        self._settled = load_settled()
        # The battles we were in, until each is written down. See `PLAYED`.
        self._played = load_played()
        # The ones a request is already out for. Not persisted: a request
        # does not survive the client, and an id stuck in here across a
        # restart would be a battle never asked about again.
        self._asking = set()
        # When `flush` first found the garage still loading, so it can give
        # up after a while instead of looking for ever.
        self._loading_since = None
        self._busy_since = None
        self._last_flush = 0.0
        self._quiet_until = 0.0

    def install(self):
        """Read every mode's results, by patching the one place they all pass.

        See the module docstring: `onResultPosted` only carries readable
        results for the Gameface path, so a patch on `postResult` is what makes
        Ranked, Stronghold, CyberSport and everything else report at all.
        """
        try:
            from gui.battle_results.service import BattleResultsService
        except ImportError:
            _logger.exception('no battle results service; battles are not reported')
            return
        self._session.patch(BattleResultsService, 'postResult', self._wrap_post)
        try:
            from PlayerEvents import g_playerEvents
            # The garage, which is the one place the account is there to prove.
            self._session.subscribe(g_playerEvents.onAccountShowGUI, self._on_garage)
            # And the start of every battle, the same event `motion` watches.
            # This is what makes a battle recoverable: the client only posts
            # results it shows, so without a record of having BEEN there a
            # battle whose window never opened is one we cannot even know we
            # are missing.
            self._session.subscribe(g_playerEvents.onAvatarBecomePlayer, self._on_battle)
        except ImportError:
            _logger.exception('no player events; battles only flush after one lands')
        try:
            from messenger.proto.events import g_messengerEvents
            # Every finished battle is announced in the service channel, the
            # one the notification centre draws, and that announcement names
            # the battle. Asking then is seconds after the battle instead of
            # the next garage; see `_on_announced`.
            self._session.subscribe(
                g_messengerEvents.serviceChannel.onChatMessageReceived,
                self._on_announced)
        except ImportError:
            _logger.exception('no service channel; battles are only claimed at '
                              'the garage')
        # The garage may already be up: the event fires when it appears, and a
        # mod installed after that would otherwise hold its queue until the
        # player next came back from a battle. `flush` refuses anywhere else.
        self._session.callback(_START_DELAY, self.flush)
        # And the same catch-up for the asking, for the same reason: a battle
        # the client never showed us is owed from the moment the mod loads, and
        # waiting for the next garage event means waiting for a whole battle.
        self._session.callback(_START_DELAY, self._claim)
        if self._replays is not None:
            # Everything the server has already answered for, handed over
            # before the first flush. This is the one gap a restart opens: a
            # battle settled in an earlier session is in no queue any more, so
            # no future answer will ever name it, and a replay still waiting on
            # its confirmation would wait for a word that is never coming.
            # Guarded on its own, like every other call into the archive.
            try:
                self._replays.confirm(self._settled)
            except Exception:
                _logger.exception('could not hand the settled battles to the '
                                  'replay archive')
        _logger.info('installed, %d battle(s) waiting', len(self._queue))

    def _wrap_post(self, original):
        """`postResult` with a look at the raw results on the way through.

        The client's own return value decides whether `requestResults`
        considers the battle posted, so it is handed back untouched and our
        own work is guarded whole: an exception here would make the client
        believe the results failed to arrive.
        """
        reporter = self

        def postResult(service, result, needToShowUI=True):
            try:
                reporter._record(result)
            except Exception:
                _logger.exception('could not write down a battle')
            return original(service, result, needToShowUI)

        return postResult

    def _sends(self):
        try:
            return self._settings.sends_battles()
        except Exception:
            _logger.exception('could not read the battle setting')
            return False

    def _record(self, results):
        """One battle's results, straight off the server. Write it down."""
        if not self._sends():
            return
        arena_id = str((results or {}).get('arenaUniqueID') or '')
        if arena_id and arena_id in self._settled:
            # Reopened from the notification centre: the client replays the
            # whole path for a cached battle, and this is the same battle.
            return
        common = (results or {}).get('common') or {}
        battle = payload(results,
                         arena_names(_int(common.get('arenaTypeID'), -1)),
                         full_version())
        if battle is None:
            _logger.info('battle %s carried nothing we could describe', arena_id or '?')
            return
        if any(row.get('arenaUniqueId') == battle['arenaUniqueId']
               for row in self._queue):
            return
        if self._motion is not None:
            # Taken and dropped, deliberately, until the server has somewhere to
            # put them.
            #
            # They were attached here and it broke every upload. Measured on one
            # real battle: the samples are 285 KB of raw JSON against 6 KB for
            # the whole result, and up to 3.6 MB on a long one with thirty
            # vehicles. Five of those is twenty megabytes against a 1.5 MB limit,
            # so nothing went up at all. The figure this was sized on, 64 KB, was
            # the GZIPPED size; the wire carries raw JSON, which is fifteen times
            # bigger.
            #
            # And the server would have thrown them away regardless: its body
            # schema has no `motion` field, so zod stripped them on arrival.
            #
            # Still taken rather than left in memory, so a battle's samples never
            # outlive it and get attached to the next one. To turn this back on:
            # a column or a bucket key to hold them, a field in the schema, and
            # zlib on this side, which is what makes 285 KB into 19 KB.
            try:
                self._motion.take(battle['arenaUniqueId'])
            except Exception:
                _logger.exception("could not clear the samples for this battle")
        if len(self._queue) >= _MAX_QUEUED:
            dropped = self._queue[0]
            _logger.warning('the queue is full at %d; dropping battle %s unsent',
                            _MAX_QUEUED, dropped.get('arenaUniqueId'))
        self._queue = queued(self._queue, battle)
        # Written down, so it is no longer owed. Dropped here rather than at
        # the garage so a battle reported the ordinary way never costs a
        # request: `_claim` only ever asks about what is still missing.
        if self._played.pop(str(battle['arenaUniqueId']), None) is not None:
            save_played(self._played)
        if append_queued(battle):
            _logger.info('battle %s written down, %d waiting',
                         battle['arenaUniqueId'], len(self._queue))
        if self._replays is not None:
            # Only told, not acted on: the file is looked for at the garage,
            # because this runs on the thread that draws the results screen and
            # the file is 1.3 MB. Guarded on its own so a fault in the archive
            # can never cost the battle itself, which is the part that matters.
            try:
                self._replays.offer(battle['arenaUniqueId'], battle.get('startedAt'))
            except Exception:
                _logger.exception('could not offer the replay of battle %s',
                                  battle['arenaUniqueId'])
        self._session.callback(_SEND_DELAY, self.flush)

    def _on_battle(self, *args):
        """A battle has started: remember we were in it.

        Written to disk at once rather than held in memory. The whole point is
        to survive the client being closed between the battle and the garage,
        which is one of the ways the results window never opens.
        """
        try:
            import BigWorld
            arena_id = str(getattr(BigWorld.player(), 'arenaUniqueID', '') or '')
            if not arena_id or arena_id in self._settled:
                return
            if arena_id in self._played:
                return
            self._played[arena_id] = {'at': time.time(), 'asked': 0}
            save_played(self._played)
        except Exception:
            _logger.exception('could not write down being in a battle')

    def _on_garage(self, *args):
        try:
            self._session.callback(_START_DELAY, self.flush)
            self._session.callback(_START_DELAY, self._claim)
        except Exception:
            # onAccountShowGUI is a SafeEvent (events_container._createEvent),
            # so the client would swallow this anyway and keep calling the
            # listeners after us. Guarded all the same, to say in the log that
            # the flush was never scheduled rather than leave it a silence.
            _logger.exception('could not schedule a flush at the garage')

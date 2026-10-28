"""Getting the results of a battle the client never showed us.

The client only posts a battle's results when it SHOWS them, so a player who
queues straight back up leaves a battle nothing here would otherwise hear of.
Two of nine went that way in one afternoon.

Two ways in, and they are not alternatives. The service channel announces
every finished battle and names it, which is the fast path; the garage claim
is the net for a battle announced while the mod was not listening, because
the client was closed or had crashed.

A mixin, for the reason given in `sending`.
"""
from __future__ import absolute_import

import logging
import time

from unicum.battles.store import (_MAX_CLAIMS, claimable, load_played,
                                  save_played, spent)

_logger = logging.getLogger('unicum.battles.claiming')

# How many battles to ask the server about per garage visit.
#
# One. Each ask is a real request for a real battle's results, and a player who
# has just installed the mod with twenty unreported battles behind them should
# not open the garage into twenty of them. The next garage takes the next one.
_CLAIMS_PER_GARAGE = 1

# How long after a battle is announced before its results are asked for.
#
# The reason is not load, it is collision. `BattleResultsCache` serves one
# request at a time and answers a second one `RES_COOLDOWN`, which is -5, and
# the client treats any negative code as a failure; the results screen the
# player opens runs through that same single call, and a failure there ends in
# `hideBattleResults()`. So a request of ours landing on top of theirs closes
# their results screen. The announcement arrives about when the client opens
# that screen by itself, so there is no worse moment to ask than at once.
#
# Five seconds, and what it costs is nothing: the client's own fetch comes to
# us through the `postResult` patch anyway, so waiting means the common case
# needs no request at all. What is left is the battle nobody opened, where
# five seconds against the garage visit this replaces is not a delay worth
# the name.
#
# It does not make a collision impossible -- the player can open results at
# any moment -- and nothing short of the client offering a lock could. It
# moves our request off the one moment the client is known to be busy, and
# `_client_has` covers the rest.
_ANNOUNCED_DELAY = 5.0

# `AccountCommands.RES_COOLDOWN`, which the results cache answers when a
# request is already in flight. Written out rather than imported because this
# module is read by the self-tests outside the client, and because the value
# is part of the account command protocol rather than of any one build.
_RES_COOLDOWN = -5

def _client_has(arena_id):
    """Whether the client already holds this battle's results.

    `areResultsPosted` is the service's own question, answered out of the
    `__statsCtrls` it fills in `postResult`. True means the results came
    through our patch on that same call, so there is nothing to fetch, and it
    also means the player's screen is served from memory and cannot be
    disturbed by anything we do.

    False when it cannot be asked, which only costs a request we would have
    made anyway.
    """
    try:
        from helpers import dependency
        from skeletons.gui.battle_results import IBattleResultsService
        service = dependency.instance(IBattleResultsService)
        return bool(service.areResultsPosted(int(arena_id)))
    except Exception:
        _logger.debug('could not ask whether battle %s is already in the '
                      'client', arena_id, exc_info=True)
        return False

def _is_battle_results(message):
    """Whether this service channel message announces a finished battle.

    Read from the client's own map on EVERY message, and never compared
    against `SYS_MESSAGE_TYPE.battleResults`. That constant is 2, and 2 is
    the random battle's type alone: every other mode registers a type of its
    own past the end of the base enumeration while the client starts
    (`registerBattleResultSysMsgType`, constants_utils.py), so Onslaught came
    out as 157 and event modes as 160 and 161. A filter on the constant hears
    random battles and goes quiet on everything else, with nothing in the log
    to say so.

    Per message rather than once at install for the same reason: the modes
    are still registering while the client starts, so a set built early is a
    set missing most of them. `AwardController` reads the map the same way.

    False when it cannot be read, which costs one announcement and leaves the
    battle to `_claim`.
    """
    try:
        from battle_results import ARENA_BONUS_TYPE_TO_SM_TYPE_BATTLE_RESULT
    except ImportError:
        _logger.exception('no battle result message types; announcements are '
                          'not read')
        return False
    return getattr(message, 'type', None) in frozenset(
        ARENA_BONUS_TYPE_TO_SM_TYPE_BATTLE_RESULT.values())


class Claiming(object):
    """Asking for a battle nobody showed us; see the module docstring."""

    def _on_announced(self, *ctx):
        """The server has announced a finished battle: ask for it shortly.

        The service channel, which is the channel the notification centre
        draws, carries a message for every battle that ends, and that message
        names the battle. So the results can be had seconds after the battle
        rather than at the next garage, and a player who queues straight back
        up no longer has one battle recovered per garage visit.

        `onChatMessageReceived` rather than the name-mangled
        `__addServerMessage` the older retrievers wrapped: it is a published
        event, four of the client's own controllers are on it, and being on an
        event instead of a patch is what lets this sit beside another mod
        doing the same thing.

        Found and measured by @Rayman223 in #2: 409-582 ms to an answer across
        random, Onslaught and an event mode, with no screen opened. Prior art
        credited there.

        Not asked the instant the announcement lands, which is what #5 is
        about. `BattleResultsCache` serves one request at a time and answers
        a second with `RES_COOLDOWN`, and the client's own results screen goes
        through the very same call (`BattleResultsGetter._request`). Since
        `RES_COOLDOWN` is -5 and the client reads any negative code as a
        failure, a request of ours overlapping the player's ends in
        `hideBattleResults()`: their results screen closes. The announcement
        arrives about when the client opens that screen by itself, so asking
        at once aims straight at the collision.

        So it waits. `_ANNOUNCED_DELAY` gives the client the first go, and by
        then the usual case needs no request at all: whatever the client
        fetches comes through the `postResult` patch for free. What is left to
        ask about is the battle nobody looked at, which is the only thing this
        was ever for.
        """
        try:
            message = ctx[1] if len(ctx) > 1 else None
            if message is None or not _is_battle_results(message):
                return
            data = getattr(message, 'data', None) or {}
            arena_id = str(data.get('arenaUniqueID') or '')
            if arena_id:
                self._session.callback(_ANNOUNCED_DELAY,
                                       lambda: self._ask_cache(arena_id))
        except Exception:
            _logger.exception('could not read a battle announcement')

    def _ask_cache(self, arena_id):
        """Ask the account's results cache about one announced battle.

        Straight to `battleResultsCache`, not through `requestResults`: the
        announcement carries only the player's own line (`playerVehicles`,
        `xp`, a name), never the thirty vehicles and `personal.<vehicle>`
        that `payload` reads, so the full results still have to be fetched.

        The answer goes to `_record`, the same place `postResult` sends what
        the client shows us, so there is one extractor and it dedupes on
        `_settled`: opening the results screen afterwards counts nothing
        twice.

        This does not spend one of `_claim`'s tries. It is a cheaper path that
        fires once per battle, and if it comes back empty the garage should
        still owe the battle.

        Gives up outright when the client already holds these results. That
        is both a free answer and the one way to be sure of not closing the
        player's results screen; see `_on_announced` for why that is at stake.
        """
        if not self._sends():
            return
        if arena_id in self._settled or arena_id in self._asking:
            return
        if _client_has(arena_id):
            # Posted already, so the `postResult` patch has had it or is about
            # to. Asking again would spend a request to learn what we know.
            _logger.info('battle %s is already in the client; nothing asked',
                         arena_id)
            return
        from helpers import isPlayerAccount
        if not isPlayerAccount():
            # The announcement can land before the account is the player, and
            # the cache lives on the Account. Nothing is lost: `_claim` owes
            # this battle from the garage, which is the whole reason it stays.
            _logger.info('battle %s was announced before the garage; left to '
                         'the next claim', arena_id)
            return
        import BigWorld
        cache = getattr(BigWorld.player(), 'battleResultsCache', None)
        if cache is None:
            return
        self._asking.add(arena_id)

        def answered(code, results):
            try:
                if results:
                    self._record(results)
                elif code == _RES_COOLDOWN:
                    # Somebody else is already asking, and the only other
                    # caller is the client itself. So the results are on their
                    # way to `postResult` and to us with them: this is the one
                    # refusal that is good news. `_claim` still owes the
                    # battle if that turns out not to happen.
                    _logger.info('battle %s is being fetched by the client; '
                                 'leaving it to that', arena_id)
            except Exception:
                _logger.exception('could not write down announced battle %s',
                                  arena_id)
            finally:
                self._answered(arena_id, bool(results))

        try:
            cache.get(int(arena_id), answered)
            _logger.info('battle %s was announced; asking the cache for it',
                         arena_id)
        except Exception:
            self._asking.discard(arena_id)
            _logger.exception('could not ask the cache about battle %s', arena_id)

    def _claim(self):
        """Ask the client for the results of a battle it never showed us.

        `requestResults` fetches them and hands them to `postResult`, which is
        the method this module already patches, so there is no second extractor
        to keep in step with the first. Both show flags are off: nothing opens,
        and the player sees none of this.

        One battle per garage, oldest first. Each ask is a real request to the
        server for a real battle, and somebody installing the mod with a
        fortnight behind them should not open the garage into a hundred of them.
        """
        # In an arena rather than the garage, `requestResults` reaches
        # BigWorld.player().battleResultsCache, which a PlayerAvatar has not
        # got: the client's own processor raises AttributeError inside an adisp
        # call. `flush` has always been gated on this; this was not, and it is
        # scheduled twelve seconds after the garage event, which is inside the
        # loading screen for anybody who presses Battle straight away. Six such
        # garages and a battle is given up on, having never been asked for.
        try:
            from helpers import isPlayerAccount
            if not isPlayerAccount():
                return
        except ImportError:
            return
        now = time.time()
        queued_ids = set(str(row.get('arenaUniqueId')) for row in self._queue)
        for arena_id in spent(self._played, self._settled, queued_ids, now):
            state = self._played.pop(arena_id)
            if state['asked'] >= _MAX_CLAIMS:
                _logger.info('battle %s never answered after %d asks; letting it go',
                             arena_id, state['asked'])
        wanted = [one for one in claimable(self._played, self._settled,
                                          queued_ids, now)
                  if one not in self._asking]
        if not wanted:
            save_played(self._played)
            return
        try:
            from helpers import dependency
            from skeletons.gui.battle_results import IBattleResultsService
            from gui.battle_results.context import RequestResultsContext
            service = dependency.instance(IBattleResultsService)
        except Exception:
            _logger.exception('cannot ask for battle results; %d battle(s) unclaimed',
                              len(wanted))
            save_played(self._played)
            return
        for arena_id in wanted[:_CLAIMS_PER_GARAGE]:
            # Counted up front and rolled back when the dispatch raises, NOT
            # written afterwards: `requestResults` can answer synchronously, and
            # `_answered` drops the row it answered about, so writing the count
            # after the call reached into a dict the callback had already
            # emptied -- a KeyError on the arena id, seen in production within
            # the hour. An ask that never left the client is still not a try,
            # which is what the rollback is for.
            self._played[arena_id]['asked'] += 1
            asked = self._played[arena_id]['asked']
            # In flight, so the next pass leaves it alone. `install` and the
            # garage event each schedule a pass, forty seconds apart, and
            # without this the second asked again for a battle the first was
            # still fetching: seen in the log as a third ask 378ms after the
            # battle it was asking about had been written down.
            self._asking.add(arena_id)
            try:
                # `showImmediately` AND `showIfPosted` off: the results go
                # through `postResult` and nowhere near a window.
                # `requestResults(ctx)(callback)`, in two calls, which is not a
                # style choice. `adisp_async` returns a closure that takes the
                # callback and only THEN runs the function (adisp.py:82), so
                # `requestResults(ctx, callback)` runs nothing at all: the
                # callback lands in `*args`, the closure is dropped, and the
                # request is never made. The log said "asking for it" and the
                # client was never asked.
                service.requestResults(
                    RequestResultsContext(int(arena_id), showImmediately=False,
                                          showIfPosted=False))(
                    lambda ok, which=arena_id: self._answered(which, ok))
                _logger.info('battle %s was never shown to us; asking for it '
                             '(try %d of %d)', arena_id, asked, _MAX_CLAIMS)
            except Exception:
                self._asking.discard(arena_id)
                # The row may be gone already, hence `get`.
                row = self._played.get(arena_id)
                if row is not None and row.get('asked'):
                    row['asked'] -= 1
                _logger.exception('could not ask for the results of battle %s',
                                  arena_id)
        save_played(self._played)

    def _answered(self, arena_id, ok):
        """The client has finished with a request, whatever it found.

        Only clears the in-flight mark. A successful answer has already gone
        through `_record` by the time this runs, which is what takes the
        battle off the owed list -- through `postResult` when the request came
        from `_claim`, and from the callback itself when it came from
        `_ask_cache`. An unsuccessful one leaves the battle owed, to be asked
        again at the next garage until its count runs out.
        """
        self._asking.discard(arena_id)
        _logger.info('the client answered for battle %s: %s', arena_id,
                     'results in hand' if ok else 'no results yet')

"""The results of a battle, asked for rather than waited on.

Why this exists
---------------
A 2.4 client does not hold a battle's numbers until something asks the server
for them. `battle_reports.py` sits on every arrival this client offers and
still captures nothing until the player opens the results screen; five ways in
were tried and timed, and that module says so. This is the ask it was missing.

Two things make it possible, and both were read out of the client's own sources
rather than guessed at:

  - the server announces a finished battle in the service channel, the message
    the notification centre shows, and that announcement carries the
    `arenaUniqueID`. It arrives whether anyone looks or not, which is what the
    capture never had: an arena id before the player asks for anything.
  - `BigWorld.player().battleResultsCache.get(arenaUniqueID, callback)` asks
    the server for that battle, and answers the results in the shape the
    capture already reads, keys and all. It is the same call the client makes
    while building the results screen, so nothing is asked for here that a
    player cannot ask for by opening it.

What this deliberately does not do
----------------------------------
It does not read the `.dat` files the cache writes beside its answers. The
cache empties that folder when it is built, so such a file is a copy of
something already delivered rather than a place a battle can be recovered
from. Mods that read the folder are reading the client's scratch paper.

The one thing to watch in game
------------------------------
A successful answer makes the client acknowledge the battle to the server. The
client does that whenever it shows results, so the acknowledgement itself is
the normal course of events -- but it has never been sent *before* the player
looked. If it turns out to cost them their own results notification, the way
out is to stop going through the cache and ask the server directly, which is
the one thing this module would have to be rewritten for.
"""
import logging
import time

from unicum import service_hooks
from unicum.report_sender import at_garage

_logger = logging.getLogger('unicum.results_request')

# `SYS_MESSAGE_TYPE.battleResults` on a 2.4 client, and the random battle's own
# type rather than the only one -- see `arrival_types`. Kept here so a client
# that moved or renamed that module keeps following something.
BATTLE_RESULTS = 2

# AccountCommands' refusals, for a client that does not hand them over. Only
# the three that mean "later" rather than "never" matter here.
_NON_PLAYER = -3
_COOLDOWN = -5
_DISCONNECTED = -7

# The cache serves one request at a time and answers the second with a
# cooldown, so these are asked for in single file. A tick takes the next one
# and retries whatever was refused for a reason that passes.
_TICK_SECONDS = 20.0
# An answer that never comes would otherwise hold the queue shut for the whole
# session. Long enough that a slow server is not mistaken for a lost callback.
_STALE_SECONDS = 60.0
# Asked for at most this many times before a battle is given up on, so a
# refusal that is somehow permanent cannot turn into a request every tick for
# as long as the client runs.
_MAX_ATTEMPTS = 5
# Battles waiting to be asked about. A player who queues straight into battle
# all evening builds this up; the number is generous because each entry is an
# integer, and the oldest goes first when it overflows.
LIMIT = 50


def _client(name):
    """Import a top-level client module, never a sibling of this one.

    Python 2 resolves a bare `import battle_results` inside this package to
    `unicum.battle_results` first, which exists and is a different thing
    entirely. The import then fails, the failure is caught, and the mod
    quietly follows the wrong set of message types -- which is precisely how
    this was found, by a check rather than by another evening in the garage.
    """
    import importlib
    return importlib.import_module(name)


def arrival_types():
    """Every message type that carries a finished battle, as this client numbers them.

    Not one number, which is the mistake that made the first live test hear
    nothing. `SYS_MESSAGE_TYPE.battleResults` is **the random battle's** type,
    2, and each game mode registers its own on top -- `registerBattleResultSysMsgType`
    injects it past the end of the base enumeration, which ends at 155. A real
    2.4 client announced a finished battle on **161** while this module was
    listening for 2 alone, and said nothing because nothing matched.

    The client keeps the whole set in `ARENA_BONUS_TYPE_TO_SM_TYPE_BATTLE_RESULT`,
    one entry per mode, so that is what is read -- and read at every message
    rather than once, because the modes register while the client starts and
    this mod is installed somewhere in the middle of that.
    """
    found = set()
    try:
        mapping = _client('battle_results').ARENA_BONUS_TYPE_TO_SM_TYPE_BATTLE_RESULT
        found.update(mapping.values())
    except Exception:
        _logger.debug('this client does not map its modes to message types', exc_info=True)
    try:
        found.add(_client('chat_shared').SYS_MESSAGE_TYPE.battleResults.index())
    except Exception:
        _logger.debug('this client does not name its message types', exc_info=True)
    if not found:
        found.add(BATTLE_RESULTS)
    return found


def type_name(kind):
    """What this client calls a message type, or None if it cannot say.

    The enumeration can be read by index, so a number in the log costs nothing
    to turn into a name. Worth the three lines: the first live run raised
    exactly this question about four numbers, and a name answers it where a
    number sends someone to read the client's sources.
    """
    try:
        item = _client('chat_shared').SYS_MESSAGE_TYPE[kind]
        return item.name() if item is not None else None
    except Exception:
        return None


def service_channel():
    """The messenger events every server message passes through, or None."""
    try:
        from messenger.proto.events import g_messengerEvents
        return g_messengerEvents.serviceChannel
    except Exception:
        _logger.debug('could not reach the messenger events', exc_info=True)
        return None


def results_cache():
    """The account's battle results cache, or None when there is no account."""
    try:
        import BigWorld
        return getattr(BigWorld.player(), 'battleResultsCache', None)
    except Exception:
        _logger.debug('could not reach the battle results cache', exc_info=True)
        return None


def arena_id_of(message, wanted=None):
    """The arena a service channel message is about, when it is a battle's.

    Everything the server says reaches the same event -- rewards, reboots,
    clan news, the repair bill a second after the battle -- so this is the
    filter. A message of the right type with no arena in it is not an error
    worth a line: the server sends battle-adjacent messages that carry no
    battle.
    """
    wanted = arrival_types() if wanted is None else wanted
    if isinstance(wanted, int):
        wanted = (wanted,)
    if getattr(message, 'type', None) not in wanted:
        return None
    data = getattr(message, 'data', None)
    if not isinstance(data, dict):
        return None
    arena_id = data.get('arenaUniqueID')
    if not arena_id:
        return None
    try:
        return int(arena_id)
    except (TypeError, ValueError):
        return None


def announced_mode(message):
    """The kind of battle an announcement is about, or None when it cannot say.

    Read so the mod can decline to ask about a battle nothing is waiting for.
    A player whose only destination scores ranked plays mostly random, and
    asking the server about every one of those would be a request per battle
    for numbers this mod throws away the moment they arrive.

    None rather than a guess when the announcement does not carry the type:
    asking about a battle that turns out to be unwanted costs one request, and
    not asking about a wanted one costs the battle.
    """
    data = getattr(message, 'data', None)
    if not isinstance(data, dict):
        return None
    bonus_type = data.get('bonusType')
    if bonus_type is None:
        return None
    try:
        from unicum.modes import mode_of
        return mode_of(bonus_type)
    except Exception:
        _logger.debug('could not name the mode of an announced battle', exc_info=True)
        return None


def retryable(code):
    """Whether a refusal is worth asking again for.

    Three of them mean "later": the account is not in the garage yet, another
    request is in flight, or the centre is down. Everything else is taken as
    final, because asking forever for a battle the server will not serve is
    indistinguishable from asking for nothing.
    """
    try:
        import AccountCommands
        later = (AccountCommands.RES_NON_PLAYER,
                 AccountCommands.RES_COOLDOWN,
                 AccountCommands.RES_CENTER_DISCONNECTED)
    except Exception:
        later = (_NON_PLAYER, _COOLDOWN, _DISCONNECTED)
    return code in later


class Requests(object):
    """Battles the server announced, asked about one at a time."""

    def __init__(self, session, deliver, taking=None, garage=at_garage, cache=results_cache,
                 limit=LIMIT, now=time.time):
        self._session = session
        self._deliver = deliver
        # Whether anything at all is taking battle reports right now. Asked
        # once per battle rather than per mode: the mode an announcement
        # carries and the mode a report turns out to have are read from
        # different places, and a gate that can disagree with the capture is a
        # gate that drops battles the capture would have kept.
        self._taking = taking if taking is not None else (lambda: True)
        self._garage = garage
        self._cache = cache
        self._limit = limit
        self._now = now
        self._pending = []
        self._attempts = {}
        self._asking = None
        self._asked_at = 0.0
        self._seen_types = set()
        self._said = set()

    def install(self):
        """Follow the server's announcements, and say whether anything was."""
        channel = service_channel()
        if channel is None:
            _logger.warning('no messenger events in this client, so a battle is only captured '
                            'when its results screen is opened')
            return False
        event = getattr(channel, 'onChatMessageReceived', None)
        if event is None or not hasattr(event, '__iadd__'):
            _logger.warning('the service channel announces nothing this mod can attach to, so a '
                            'battle is only captured when its results screen is opened')
            return False
        # The public event rather than the private method every other mod
        # patches: one is handed to subscribers by name, the other is a
        # name-mangled attribute that two mods cannot both wrap safely.
        self._session.subscribe(event, self._announced)
        # The moment the cache stops refusing: it is its own handler on this
        # event that stops ignoring requests. The reference implementation
        # this follows drains here rather than on a timer, and a battle the
        # player is waiting on should not sit for a tick's length first.
        self._follow_the_garage()
        # Kept as well as the event, not instead of it. Whether the cache's own
        # handler for the same event runs before this one is not ours to
        # decide, and a tick is what makes that ordering stop mattering.
        self._session.repeat(_TICK_SECONDS, self.drain)
        _logger.info('asking the client for the results of every battle the server announces')
        return True

    def _follow_the_garage(self):
        """Drain when the account becomes the player, if that can be followed."""
        account = service_hooks.account_events()
        event = getattr(account, 'onAccountBecomePlayer', None) if account is not None else None
        if event is None or not hasattr(event, '__iadd__'):
            _logger.info('this client does not announce the account becoming the player; '
                         'battles are asked about on the %.0fs tick instead', _TICK_SECONDS)
            return
        self._session.subscribe(event, self._became_player)

    def _became_player(self, *args):
        self.drain()

    def _announced(self, client_id=None, message=None, *args):
        """A server message arrived. Keep it if it is a battle worth asking about."""
        self._note_type(message)
        arena_id = arena_id_of(message)
        if arena_id is None:
            return
        if not self._taking():
            self._say_once('nothing taking',
                           'a battle finished, but nothing is taking battle reports right now, '
                           'so the server is not asked about it. Turn the setting on, or link a '
                           'site that wants it')
            return
        if self.remember(arena_id):
            _logger.info('the server announced a %s battle, %s',
                         announced_mode(message) or 'battle of an unnamed mode', arena_id)
        self.drain()

    def _note_type(self, message):
        """Say once what kinds of message reach this event, and which carry a battle.

        The one line that tells a silent mod apart from a mod that is never
        spoken to. Without it, a filter dropping every message and an event
        that never fires read exactly the same in game.log -- and both have
        already been suspected for an evening each.
        """
        kind = getattr(message, 'type', None)
        if kind in self._seen_types:
            return
        self._seen_types.add(kind)
        named = type_name(kind)
        said = '%s, %s' % (kind, named) if named else str(kind)
        wanted = arrival_types()
        _logger.info('the service channel said something of type %s%s', said,
                     ' -- which is one battles arrive on' if kind in wanted else
                     ' -- not one battles arrive on (those are %s)'
                     % ', '.join(str(one) for one in sorted(wanted)))

    def _say_once(self, key, message, *args):
        """Say something that would otherwise be said every tick, or every battle."""
        if key in self._said:
            return
        self._said.add(key)
        _logger.info(message, *args)

    def remember(self, arena_id):
        """Queue a battle to ask about, and say whether it was new."""
        if arena_id == self._asking or arena_id in self._pending:
            return False
        self._pending.append(arena_id)
        while len(self._pending) > self._limit:
            dropped = self._pending.pop(0)
            self._attempts.pop(dropped, None)
            _logger.warning('too many battles waiting to be asked about; gave up on %s', dropped)
        return True

    def waiting(self):
        """The battles still to be asked about, oldest first."""
        return list(self._pending)

    def drain(self):
        """Ask about the next battle, if this is a moment that can."""
        self._clear_stale()
        if self._asking is not None or not self._pending:
            return
        # Outside the garage the cache refuses every request, and a refusal
        # spends one of the attempts a battle gets. The sender waits for the
        # same moment, for the same kind of reason.
        if not self._garage():
            self._say_once('not the player',
                           'battles are waiting, but the account is not the player yet; '
                           'they are asked about on the way back to the garage')
            return
        cache = self._cache()
        if cache is None:
            self._say_once('no cache',
                           'battles are waiting, but this client has no battle results cache '
                           'to ask; they are captured only if their results screen is opened')
            return
        arena_id = self._pending.pop(0)
        _logger.info('asking the server about battle %s', arena_id)
        self._attempts[arena_id] = self._attempts.get(arena_id, 0) + 1
        self._asking = arena_id
        self._asked_at = self._now()
        try:
            cache.get(arena_id, self._answer(arena_id))
        except Exception:
            _logger.exception('could not ask for the results of battle %s', arena_id)
            self._asking = None
            self._give_up_or_retry(arena_id, retry=False)

    def _clear_stale(self):
        """Stop waiting on an answer that is never going to come.

        Without this, one callback the client never runs holds every later
        battle shut for the rest of the session -- the failure that is worst
        here, because it is silent and grows.
        """
        if self._asking is None:
            return
        if self._now() - self._asked_at <= _STALE_SECONDS:
            return
        arena_id = self._asking
        self._asking = None
        _logger.warning('no answer about battle %s after %.0fs; moving on', arena_id,
                        _STALE_SECONDS)
        # To the back, not the front: whatever is wrong with this one, the
        # battles behind it have waited long enough to go first.
        self._give_up_or_retry(arena_id, front=False)

    def _answer(self, arena_id):

        def answered(code=None, results=None):
            # Not `arena_id is self._asking`: a stale ask was let go of, and
            # its answer arriving late is still an answer worth keeping.
            if self._asking == arena_id:
                self._asking = None
            if results is not None:
                self._attempts.pop(arena_id, None)
                if arena_id in self._pending:
                    # Let go of as stale, then answered after all. Without
                    # this it is asked about a second time for an answer
                    # already in hand.
                    self._pending.remove(arena_id)
                try:
                    self._deliver(results, 'the client answering about battle %s' % arena_id)
                except Exception:
                    _logger.exception('could not capture the answer about battle %s', arena_id)
                self.drain()
                return
            _logger.info('the client refused to answer about battle %s with code %s',
                         arena_id, code)
            again = retryable(code)
            self._give_up_or_retry(arena_id, retry=again)
            # Only when this battle is settled. A refusal worth retrying says
            # the moment is wrong, not the battle, so asking again on the same
            # frame would spend every attempt it has in one burst and give up
            # on a battle that a tick later would have been served.
            if not again:
                self.drain()

        return answered

    def _give_up_or_retry(self, arena_id, retry=True, front=True):
        attempts = self._attempts.get(arena_id, 0)
        if not retry or attempts >= _MAX_ATTEMPTS:
            self._attempts.pop(arena_id, None)
            _logger.warning('giving up on the results of battle %s after %d attempt(s); it is '
                            'captured only if its results screen is opened', arena_id, attempts)
            return
        # At the front by default: the oldest battle is the one the player is
        # likeliest to have already walked away from.
        self._pending.insert(0 if front else len(self._pending), arena_id)


def install(session, deliver, taking=None, garage=at_garage, cache=results_cache):
    requests = Requests(session, deliver, taking=taking, garage=garage, cache=cache)
    requests.install()
    return requests

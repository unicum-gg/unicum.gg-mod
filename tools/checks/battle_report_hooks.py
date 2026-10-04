"""Checks for how the capture attaches to the client's battle results.

Separate from the checks for what a report is read from, because this is the
other half of the same failure and it failed on its own. A real client reported
`onResultPosted` as installed and then never fired it: nothing was captured and
nothing was said, because the install took the first way in that existed and
returned, leaving the `postResult` patch that reaches the same moment unapplied.
"""
import os
import sys
import tempfile

from checks.battle_fixtures import Bonus, Link, Settings, results
from checks.common import check


class _Event(object):
    """A WG Event, reduced to attaching and firing."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, *args):
        for handler in list(self.handlers):
            handler(*args)


class _Both(object):
    """A service offering both ways in."""

    def __init__(self):
        self.onResultPosted = _Event()

    def postResult(self, result, *args):
        return 'the client answer'


class _EventOnly(object):
    def __init__(self):
        self.onResultPosted = _Event()


class _Neither(object):
    pass


def _constants():
    """Give the fake client the bonus types it does not carry.

    The hooks reach `capture` the way the client does, without the bonus types
    passed in, so `modes.mode_of` imports them from the client itself. Every
    other check hands them over explicitly, which is why nothing had needed
    this until a check went through the real hook path.
    """
    class _Constants(object):
        ARENA_BONUS_TYPE = Bonus

    sys.modules.setdefault('constants', _Constants())


def _hooked(service, queue=None, on=True):
    """Install a capture over this service, and return the session owning it.

    Returned so a check can close it, which two things here depend on: the
    patches land on a class, so one check's would wrap the next check's, and
    the watcher reschedules itself, so one left pending runs long after the
    package is purged -- against module globals that are gone by then.
    """
    from unicum.battle_reports import BattleReports
    from unicum.runtime.session import Session

    class _Reports(BattleReports):
        def _service(self):
            return service

    session = Session(0)
    _Reports(session, Settings(on), queue=queue, link=Link()).install()
    return session


def _queue():
    from unicum.report_queue import Queue

    return Queue(store=os.path.join(tempfile.mkdtemp(), 'q.json'))


def _account_announcing(arrival):
    """Put an account in the client's place, announcing results on `arrival`."""
    class _Account(object):
        onBattleResultsReceived = arrival

    class _PlayerEvents(object):
        g_playerEvents = _Account()

    sys.modules['PlayerEvents'] = _PlayerEvents
    return _PlayerEvents.g_playerEvents


def _account_calling(seen):
    """An account where the name is a method the client calls, not an event.

    The other shape this name has. A surface probe reads a name and cannot say
    which of the two it is, and assuming the event shape left the capture
    waiting on an announcement that never reached it.
    """
    class _Account(object):
        def onBattleResultsReceived(self, is_player, results):
            seen.append((is_player, results))
            return 'the client answer'

    class _PlayerEvents(object):
        g_playerEvents = _Account()

    sys.modules['PlayerEvents'] = _PlayerEvents
    return _PlayerEvents.g_playerEvents


def check_battle_report_arrival():
    """The capture sits on the arrival, not on the player opening a screen.

    A live test played a battle without opening the results screen and captured
    nothing, then captured it the moment the screen opened: both of the results
    service's hooks fire as that screen is built. A battle nobody looks at
    still has to count, or a score computed from nine battles out of ten looks
    like a score rather than a fault.
    """
    _constants()
    arrival = _Event()
    _account_announcing(arrival)
    session = None
    try:
        # A service offering nothing at all, so only the account can be what
        # captures here.
        queue = _queue()
        session = _hooked(_Neither(), queue)
        check('the account announcement is attached', len(arrival.handlers) == 1)

        arrival.fire(True, results())
        check('a battle the player never looked at is captured', len(queue.all()) == 1)

        # Read out of the arguments, not off a position: the flag comes first
        # on some clients and a guessed signature would capture a boolean.
        arrival.fire(results(arenaUniqueID=7), False)
        check('the results are found whichever argument carries them',
              len(queue.all()) == 2)

        arrival.fire(True, False)
        check('arguments holding no results capture nothing', len(queue.all()) == 2)
    finally:
        if session is not None:
            session.close()
        del sys.modules['PlayerEvents']


def check_battle_report_arrival_as_method():
    """The same name, in its other shape: a method the client calls."""
    _constants()
    seen = []
    account = _account_calling(seen)
    session = None
    try:
        queue = _queue()
        session = _hooked(_Neither(), queue)

        answer = account.onBattleResultsReceived(True, results())
        check('a battle announced by a method is captured too', len(queue.all()) == 1)
        # The client's own call runs first and its answer is handed back: the
        # capture must never be why the client's own handling changes.
        check('the client still gets its arguments', seen == [(True, results())])
        check("and its answer is returned", answer == 'the client answer')
    finally:
        if session is not None:
            session.close()
        del sys.modules['PlayerEvents']


def check_battle_report_no_arrival():
    """A client announcing nothing is said out loud, not passed over.

    A capture following nothing would score a player on the battles whose
    results they happened to open, which looks like a score and is not one.
    """
    _constants()
    sys.modules.pop('PlayerEvents', None)
    queue = _queue()
    _hooked(_Neither(), queue).close()
    check('a client with no arrival to follow captures nothing by itself', not queue.all())


def check_battle_report_hooks():
    _constants()
    # Without an account in the client's place, only the service's hooks are
    # left -- which is what the rest of this checks.
    sys.modules.pop('PlayerEvents', None)

    both = _Both()
    queue = _queue()
    session = _hooked(both, queue)
    try:
        check('the event is attached when the service has one',
              len(both.onResultPosted.handlers) == 1)

        both.onResultPosted.fire(results())
        check('a battle arriving by the event is captured', len(queue.all()) == 1)

        answer = both.postResult(results(arenaUniqueID=12457893456789012346))
        check('a battle arriving by the patch is captured as well', len(queue.all()) == 2)
        # The client's own call runs first and its answer is handed back
        # untouched: a capture must never be the reason a player does not see
        # their results.
        check("and the client's own answer is returned", answer == 'the client answer')

        both.onResultPosted.fire(results())
        check('a battle reaching the capture twice is queued once', len(queue.all()) == 2)
    finally:
        session.close()

    alone = _EventOnly()
    _hooked(alone).close()
    check('an event with no postResult beside it is still attached',
          len(alone.onResultPosted.handlers) == 1)

    empty = _queue()
    _hooked(_Neither(), empty).close()
    check('a service offering no way in captures nothing and does not raise',
          not empty.all())

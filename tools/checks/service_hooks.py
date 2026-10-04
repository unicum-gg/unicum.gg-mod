"""Checks for reading what a results service offers to sit on.

The point of this surface is that it is read rather than guessed, so what is
checked is that it tells an event from everything else that merely answers to
`+=`, that it never calls what it finds, and that a client property which
raises does not take the description down with it.
"""
import logging

from checks.common import check


class _Event(object):
    """A WG Event: attached to with `+=`, and called to fire."""

    def __iadd__(self, handler):
        return self

    def __isub__(self, handler):
        return self

    def __call__(self, *args):
        pass


class _OneWayEvent(object):
    """An event that accepts a handler and will not give it back.

    What a real client offers. Requiring `-=` as well made the probe report a
    service as having no events while the capture was attached to one.
    """

    def __iadd__(self, handler):
        return self

    def __call__(self, *args):
        pass


class _NotAnEvent(object):
    """Answers to `+=` and cannot be fired, so it is not one."""

    def __iadd__(self, handler):
        return self


class _Capture(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())

    def said(self, fragment):
        return any(fragment in line for line in self.lines)


def check_service_signatures():
    from unicum.service_hooks import signatures

    class _Service(object):
        def requestResults(self, arenaUniqueID, needsRefresh=False):
            raise AssertionError('reading a signature must not call anything')

        def areResultsPosted(self, arenaUniqueID):
            raise AssertionError('reading a signature must not call anything')

        notAMethod = 3

    read = signatures(_Service(), ('requestResults', 'areResultsPosted',
                                   'notAMethod', 'absent'))
    # What a client wants to be asked with, which is the whole point of
    # reading these: an arrival cannot be listened to when there is none.
    check('the arguments a method takes are read',
          'requestResults(arenaUniqueID, needsRefresh)' in read)
    check('a plain value is not a method to ask with', not any('notAMethod' in row for row in read))
    check('a name the service does not have is left out',
          not any('absent' in row for row in read))
    check('and both methods it does have are there', len(read) == 2)


def check_service_hooks_filter():
    from unicum.service_hooks import about_battles

    names = ['onBattleResultsReceived', 'onAccountShowGUI', 'postResult',
             'onArenaCreated', 'onClientUpdated']
    # The account's surface holds hundreds of names; only the ones naming a
    # battle or a result can be where an arrival is announced.
    check('a name about battles is kept', 'onBattleResultsReceived' in about_battles(names))
    check('a name about results is kept too', 'postResult' in about_battles(names))
    check('and everything else is left out',
          'onAccountShowGUI' not in about_battles(names)
          and 'onClientUpdated' not in about_battles(names))
    check('a client with no account events is not a failure',
          about_battles([]) == [])


def check_service_hooks():
    from unicum.service_hooks import describe, is_event, surface

    called = []

    class _Service(object):
        onResultPosted = _Event()

        def __init__(self):
            self.counters = [1, 2]
            self.label = 'results'
            self.total = 3

        def postResult(self, result):
            called.append(result)

        @property
        def angry(self):
            raise RuntimeError('a client property that raises')

    # A list answers to `+=` and would be subscribed to happily, then never
    # fire anything. Both halves of the protocol are required.
    check('an event is something to attach to and to fire', is_event(_Event()))
    # Seen on a real client, and the reason this no longer asks for `-=`.
    check('an event that refuses -= is still an event', is_event(_OneWayEvent()))
    check('something that takes a handler and cannot fire is not',
          not is_event(_NotAnEvent()))
    check('a list is not an event', not is_event([1, 2]))
    check('a string is not an event', not is_event('results'))
    check('a number is not an event', not is_event(3))

    events, methods = surface(_Service())
    check('the events are found', events == ['onResultPosted'])
    check('the methods are found', 'postResult' in methods)
    check('a plain value is neither', 'label' not in methods and 'label' not in events)
    # Reading a surface must not set anything off: the mod would be running
    # client code it knows nothing about, at the end of every battle.
    check('nothing found was called', not called)

    captured = _Capture()
    logger = logging.getLogger('unicum.service_hooks')
    logger.addHandler(captured)
    try:
        describe(_Service())
    finally:
        logger.removeHandler(captured)

    check('the description names the service', captured.said('_Service'))
    check('and what it offers', captured.said('onResultPosted') and captured.said('postResult'))
    check('a property that raises does not take the description down',
          not captured.said('angry'))

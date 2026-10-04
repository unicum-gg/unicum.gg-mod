"""Checks for finding the server's results dict on whatever the client hands us.

This is the one part of the capture that cannot be checked against a real
client, so what is checked here is the next best thing: that a known path is
followed, that an unknown one is still found and *reported*, that a view
pointing back at itself does not hang the walk, and that a miss describes
itself well enough to be fixed from one session's log.

The last two matter because both have happened. A real client handed the mod a
`_ReusableInfo` whose dict sat at none of the listed paths, and the miss said
only which attribute names mentioned "personal" -- not which of them held a
dict, which is what decides the fix.
"""
import logging

from checks.common import check


def _results():
    """The server's results dict, reduced to what identifies it."""
    return {'common': {'arenaUniqueID': 12457893456789012345, 'winnerTeam': 1},
            'personal': {'8721': {'team': 1}, 'avatar': {'team': 1}}}


class _Capture(logging.Handler):
    """What the module said while a check ran."""

    def __init__(self):
        logging.Handler.__init__(self)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())

    def said(self, fragment):
        return any(fragment in line for line in self.lines)


def _listening(call):
    """Run `call`, and return (its result, what the module logged)."""
    captured = _Capture()
    logger = logging.getLogger('unicum.results_dict')
    logger.addHandler(captured)
    try:
        return call(), captured
    finally:
        logger.removeHandler(captured)


def check_results_dict_paths():
    from unicum.results_dict import raw_results

    payload = _results()

    class _Personal(object):
        def __init__(self):
            self._PersonalInfo__personal = payload

    class _Reusable(object):
        def __init__(self):
            self.personal = _Personal()

    check('a results dict is taken at face value', raw_results(payload) is payload)
    check('the dict is found at a known path', raw_results(_Reusable()) is payload)


def check_results_dict_search():
    from unicum.results_dict import raw_results

    payload = _results()

    class _Buried(object):
        """A view holding the dict where no listed path reaches it."""

        def __init__(self):
            self.somethingElse = {'wrapped': payload}

    found, said = _listening(lambda: raw_results(_Buried()))
    check('a dict at an unlisted path is still found', found is payload)
    # Without the path in the log, the next client release costs a round trip
    # through somebody's evening instead of one line in _RAW_PATHS.
    check('and the path it was found at is reported', said.said('somethingElse'))


def check_results_dict_cycle():
    from unicum.results_dict import raw_results

    class _Loop(object):
        pass

    loop = _Loop()
    loop.itself = loop
    loop.sibling = _Loop()
    loop.sibling.back = loop

    # The walk runs on the main thread as a battle ends: a view that refers to
    # itself must come back, not spin.
    missed = []
    check('a view pointing back at itself does not hang the walk',
          raw_results(loop, on_miss=missed.append) is None)
    check('and it is reported as a miss', len(missed) == 1)


def check_results_dict_said_once():
    from unicum.results_dict import describe

    class _Repeat(object):
        def __init__(self):
            self.notTheOne = {'team': 1}

    _, first = _listening(lambda: describe(_Repeat()))
    check('a shape is described the first time it is seen', first.said('_Repeat'))
    # A client can hand the capture a view by one route and the dict by
    # another, so this miss happens every battle. Repeating it would bury the
    # lines that say a battle was captured and sent.
    _, again = _listening(lambda: describe(_Repeat()))
    check('and not described again', not again.said('_Repeat'))


def check_results_dict_miss():
    from unicum.results_dict import describe, raw_results

    missed = []
    check('an unknown shape yields nothing', raw_results(object(), on_miss=missed.append) is None)
    check('and it reports what it was handed', len(missed) == 1)

    class _Opaque(object):
        def __init__(self):
            self.notTheOne = {'team': 1, 'xp': 5}
            self.aView = object()

        @property
        def angry(self):
            raise RuntimeError('a client property that raises')

        def getSomething(self):
            return None

    _, said = _listening(lambda: describe(_Opaque()))
    check('a miss names the class it was handed', said.said('_Opaque'))
    # The names alone were not enough the first time this fired in a client.
    check('and which attributes hold a dict, with their keys', said.said('notTheOne: dict(team, xp)'))
    check('and what the others are', said.said('aView: object'))
    check('a property that raises does not take the description down',
          not said.said('angry'))
    check('methods are left out, the dict is held and never computed',
          not said.said('getSomething'))

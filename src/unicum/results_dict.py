"""Where the client keeps the server's own results dict.

The battle results service passes round a reusable *view* of the results, not
the dict the server sent. That view's shape is the client's business and moves
with it; the dict underneath does not, because it is the server's payload. So
the dict is what every reader wants, and this module is the only place that has
to know where it hides.

Three steps, in order of certainty:

  - a dict is taken at face value, which is what the checks hand it;
  - then the paths already seen on a real client, tried in order;
  - then a bounded walk of the object, which logs the path it found.

The walk is the part worth explaining. This is the one piece of the capture
that cannot be verified outside a running client, and a client that moves the
dict used to mean the mod stopped capturing until someone read a log, guessed a
path and shipped a release. The walk finds it anyway and says where, so the
next release spends one line here instead of somebody's evening.
"""
import logging

_logger = logging.getLogger('unicum.results_dict')

# The key every server results dict carries, and the cheapest proof that what
# we hold is that dict rather than a view of it.
_MARK = 'common'

# How far the walk goes and how much it may touch. Both bounded: it runs on the
# main thread as a battle ends, and a view holding a reference back to itself
# would otherwise be walked forever.
_MAX_DEPTH = 3
_MAX_VISITS = 400

# How many attributes a miss describes before the line stops being readable.
_MAX_DESCRIBED = 40

# The shapes already described, so a miss that happens every battle is said
# once. Reset with the package on every reload, which is what we want: a shape
# worth describing again after an edit is a shape read by new code.
_described = set()

# Where the dict has actually been found, in the order to try. A client that
# moves it gets a line here, read off the path the walk logs.
_RAW_PATHS = (
    ('_ReusableInfo__personal', '_PersonalInfo__personal'),
    ('personal', '_PersonalInfo__personal'),
    ('personal', '_personal'),
    ('_personal', ),
    ('personal', ),
)


def is_results(value):
    """Whether this is the server's results dict and not a view of it."""
    return isinstance(value, dict) and _MARK in value


def _follow(posted, path):
    """What a path of attribute names leads to, or None if it leads nowhere."""
    value = posted
    for step in path:
        value = getattr(value, step, None)
        if value is None:
            return None
    return value


def _children(value):
    """What is worth looking inside, each under a name that can be logged.

    Callables are skipped on purpose: the dict is held, not computed, and
    calling a client's methods to find out would be this mod deciding to run
    code it knows nothing about at the end of every battle. A property that
    raises is the client's business too, so it is stepped over rather than
    taking the capture down.
    """
    if isinstance(value, dict):
        for key in value:
            yield '[%r]' % (key, ), value[key]
        return
    for name in dir(value):
        if name.startswith('__'):
            continue
        try:
            attr = getattr(value, name)
        except Exception:
            continue
        if attr is None or callable(attr):
            continue
        if isinstance(attr, (basestring, bool, int, long, float)):
            continue
        yield name, attr


def _step(path, name):
    return name if not path else '%s.%s' % (path, name)


def _walk(posted):
    """(the results dict, the path it sits at), breadth first, or (None, None).

    Breadth first rather than depth first because the dict is held near the top
    of whatever we were handed, and the deep corners of a client's view are
    where the cycles and the expensive properties live.
    """
    seen = set([id(posted)])
    frontier = [('', posted)]
    visits = 0
    for _ in range(_MAX_DEPTH):
        following = []
        for path, value in frontier:
            for name, child in _children(value):
                visits += 1
                if visits > _MAX_VISITS:
                    return None, None
                if is_results(child):
                    return child, _step(path, name)
                if id(child) in seen:
                    continue
                seen.add(id(child))
                following.append((_step(path, name), child))
        frontier = following
    return None, None


def raw_results(posted, on_miss=None):
    """The client's own results dict, out of whatever the hook was handed.

    When nothing leads to one, `on_miss` is called with what we did get. That
    is not politeness: a miss has to describe itself in `game.log` well enough
    to be fixed from one session's log.
    """
    if isinstance(posted, dict):
        return posted
    for path in _RAW_PATHS:
        value = _follow(posted, path)
        if is_results(value):
            return value
    found, path = _walk(posted)
    if found is not None:
        # A warning, not an info: the capture works, but on a path no release
        # knows about, and this line is the whole of the fix for the next one.
        _logger.warning('the results dict was found by searching, at `%s`. Capture works, but add '
                        'that path to _RAW_PATHS in results_dict.py so it is not searched again.',
                        path)
        return found
    if on_miss is not None:
        on_miss(posted)
    return None


def describe(posted):
    """Say what we were handed, in enough detail to fix this from one log line.

    The names alone were not enough the first time this fired: what decides the
    fix is which of them hold a dict, and what keys those dicts carry.

    Said once per shape, not once per battle. A client can hand the capture a
    view by one route and the dict by another -- `onResultPosted` passes a
    `_ReusableInfo` holding nothing but more view objects, while `postResult`
    passes the dict itself -- so this miss is expected every battle and is
    reported for the first one. Repeating it would bury the lines that matter.
    """
    name = type(posted).__name__
    if name in _described:
        return
    _described.add(name)
    try:
        rows = []
        for name, child in _children(posted):
            if len(rows) >= _MAX_DESCRIBED:
                rows.append('...')
                break
            if isinstance(child, dict):
                keys = sorted(str(key) for key in child)[:12]
                rows.append('%s: dict(%s)' % (name, ', '.join(keys) or 'empty'))
            else:
                rows.append('%s: %s' % (name, type(child).__name__))
        _logger.warning('battle results arrived as %s and nothing led to the results dict. '
                        'What it holds: %s', type(posted).__name__, '; '.join(rows) or 'nothing')
    except Exception:
        _logger.warning('battle results arrived in an unreadable shape')

"""What is owed, what was sent, and what the server answered.

Three files and the pure functions over them: the battles waiting to go, the
ids already answered for, and the battles that started and whose results
nobody showed us. Everything here takes values and returns values, which is
why the checks drive it with no client in sight.
"""
from __future__ import absolute_import

import json
import logging
import os

_logger = logging.getLogger('unicum.battles.store')

# Where battles wait until the server has taken them, one JSON object a line.
#
# A line a battle, because this file is appended to from the battle results
# handler, on the thread that draws the game. The whole-file rewrite only
# happens once a flush has been answered, which is at the garage.
QUEUE = os.path.join('mods', 'configs', 'unicum', 'battles.ndjson')

# The ids the server has already answered for, so a battle whose results the
# player reopens from the notification centre is not offered again.
#
# `postResult` runs again for a battle read out of the client's own cache, so
# without this every stroll through the notification centre reposted up to
# twenty battles. This is the same job `loadouts.py` gives its fingerprint
# store, and leaving it out was the half of that pattern this module missed.
SETTLED = os.path.join('mods', 'configs', 'unicum', 'battles-sent.json')

# How many settled ids to remember. A fortnight of heavy play, at 20 bytes an
# id, so the file stays a few kilobytes.
_MAX_SETTLED = 500

# The battles this client was in, until each one has been written down.
#
# **The client only posts a battle's results when it SHOWS them.** A player who
# returns to the garage and queues straight back up without the results window
# opening leaves a battle that, as far as this module goes, never happened: no
# `postResult`, so no `_record`, so no line in the queue and nothing in the log
# either. Two of nine battles went that way in one afternoon, and the only
# trace of them was `motion`'s own "sampling battle" line.
#
# So the arena id is written down when the battle STARTS, off the same event
# `motion` uses, and the results are asked for at the garage rather than waited
# for. The file is the record of what is still owed.
PLAYED = os.path.join('mods', 'configs', 'unicum', 'battles-played.json')

# How long a battle is still worth asking about.
#
# A day. Long enough to cover a client closed mid-session and reopened the next
# evening, short enough that a battle nobody will ever answer for stops costing
# a request at every garage. The server's own ingest refuses what is too old
# anyway, so asking past that buys nothing.
_CLAIM_DEADLINE = 24 * 3600.0

# How many times one battle is asked about before it is let go of.
#
# A battle still running answers unsuccessfully, which is the ordinary case for
# the first ask: the player left early and it has not finished. Six garages is
# generous for that, and bounded for the battle whose results the server simply
# does not have.
_MAX_CLAIMS = 6

# How many battles the queue keeps when the server cannot be reached.
#
# A queue that grew without a bound would be a file that grows without a
# bound. Two hundred battles is more than a week of heavy play, and past that
# the oldest go: a battle nobody could send for a week is one somebody else in
# it has almost certainly sent already. Dropping one is logged, because it is
# the only place this module loses data on purpose.
_MAX_QUEUED = 200

def read_answer(body):
    """(stored, known, [(id, reason)]) from the endpoint, or None if it was not it.

    **None is the whole point of this function.** An answer the mod cannot
    parse and an answer that stored nothing have to be different things,
    because the caller deletes what the server names and the queue is the only
    copy. Reading a login page or a CDN error served with a 200 as "nothing was
    stored, carry on" is how a whole queue disappears in one flush.

    So an answer counts only if it names at least one of the three lists, and
    all of them are read by name rather than by position.
    """
    try:
        answer = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(answer, dict):
        return None
    stored, known, refused = [], [], []
    named = False
    for key, into in (('stored', stored), ('known', known)):
        value = answer.get(key)
        if isinstance(value, list):
            named = True
            into.extend(str(item) for item in value if item)
    rejected = answer.get('rejected')
    if isinstance(rejected, list):
        named = True
        for row in rejected:
            if isinstance(row, dict) and row.get('arenaUniqueId'):
                refused.append((str(row['arenaUniqueId']), row.get('reason') or '?'))
    return (stored, known, refused) if named else None

def load_queue():
    """The battles a previous session wrote down and could not send."""
    out = []
    try:
        with open(QUEUE, 'rb') as handle:
            lines = handle.read().decode('utf-8').splitlines()
    except (IOError, OSError, UnicodeDecodeError):
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            battle = json.loads(line)
        except ValueError:
            # One torn line, from a crash mid-append, is not worth the rest of
            # the queue.
            continue
        if isinstance(battle, dict) and battle.get('arenaUniqueId'):
            out.append(battle)
    return out

def append_queued(battle):
    """Add one battle to the file, without reading or rewriting it.

    This runs inside the battle results handler, on the thread that draws the
    game. One line is 10 KB and a fraction of a millisecond; serialising the
    whole queue here was 31 ms of `json.dumps` plus 12 ms of write, measured on
    200 battles, landing on the results screen's own animation.
    """
    try:
        folder = os.path.dirname(QUEUE)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(QUEUE, 'ab') as handle:
            handle.write(json.dumps(battle).encode('utf-8') + b'\n')
        return True
    except (IOError, OSError):
        _logger.exception('could not append to %s', QUEUE)
        return False

def save_queue(battles):
    """Rewrite the file. Only ever called once a flush has been answered."""
    try:
        folder = os.path.dirname(QUEUE)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(QUEUE, 'wb') as handle:
            handle.write(b''.join(json.dumps(battle).encode('utf-8') + b'\n'
                                  for battle in battles))
    except (IOError, OSError):
        _logger.exception('could not write %s', QUEUE)

def load_played():
    """The battles we were in and have not written down, as {id: startedAt}.

    `{}` on anything unreadable, like every other store here: a file a crash
    tore in half is a file we are better off rebuilding than refusing to start
    over.
    """
    try:
        with open(PLAYED, 'rb') as handle:
            parsed = json.loads(handle.read().decode('utf-8'))
    except (IOError, OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    out = {}
    for key, value in parsed.items():
        if not isinstance(value, dict):
            continue
        try:
            out[str(key)] = {'at': float(value.get('at') or 0),
                             'asked': int(value.get('asked') or 0)}
        except (TypeError, ValueError):
            continue
    return out

def save_played(played):
    try:
        folder = os.path.dirname(PLAYED)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(PLAYED, 'wb') as handle:
            handle.write(json.dumps(played).encode('utf-8'))
    except (IOError, OSError):
        _logger.exception('could not write %s', PLAYED)

def claimable(played, settled, queued_ids, now):
    """The ids still worth asking the server about, oldest battle first.

    Already settled or already queued means written down, so there is nothing
    to ask. Past the deadline or past the attempt count means nobody is ever
    going to answer, and the entry is the caller's to drop.
    """
    out = []
    for arena_id, state in played.items():
        if arena_id in settled or arena_id in queued_ids:
            continue
        if now - state['at'] > _CLAIM_DEADLINE or state['asked'] >= _MAX_CLAIMS:
            continue
        out.append(arena_id)
    out.sort(key=lambda one: played[one]['at'])
    return out

def spent(played, settled, queued_ids, now):
    """The ids to forget: written down, too old, or asked about too often."""
    out = []
    for arena_id, state in played.items():
        if arena_id in settled or arena_id in queued_ids:
            out.append(arena_id)
        elif now - state['at'] > _CLAIM_DEADLINE or state['asked'] >= _MAX_CLAIMS:
            out.append(arena_id)
    return out

def load_settled():
    try:
        with open(SETTLED, 'rb') as handle:
            stored = json.loads(handle.read().decode('utf-8'))
    except (IOError, OSError, ValueError, UnicodeDecodeError):
        return []
    if not isinstance(stored, list):
        return []
    return [str(item) for item in stored if item][-_MAX_SETTLED:]

def save_settled(ids):
    try:
        folder = os.path.dirname(SETTLED)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(SETTLED, 'wb') as handle:
            handle.write(json.dumps(list(ids)[-_MAX_SETTLED:]).encode('utf-8'))
    except (IOError, OSError):
        _logger.exception('could not write %s', SETTLED)

def queued(battles, battle):
    """`battles` with `battle` added, deduplicated, oldest dropped past the cap."""
    out = [row for row in battles
           if row.get('arenaUniqueId') != battle['arenaUniqueId']]
    out.append(battle)
    return out[-_MAX_QUEUED:]

def settled(battles, done):
    """`battles` without the ids the server has answered for.

    Only the ids. A battle the answer did not mention stays in the queue, even
    when the call succeeded: a partial acceptance the client cannot see is
    exactly the case where dropping the batch loses data for good.
    """
    answered = set(done)
    return [row for row in battles if row.get('arenaUniqueId') not in answered]

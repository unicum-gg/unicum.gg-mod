"""Our own copies, and the record of what the server still owes us.

The client's own file is volatile: `enableAutoRecordingBattles` writes every
battle to `replay_last_battle.wotreplay` and overwrites the one before, so a
player who queues up again destroys the file being uploaded. Every replay is
therefore copied aside the moment it is found, and the upload reads the copy.

Three files: the copies, the queue of what to send, and the battles whose
file has not been looked for yet. That last one is on disk rather than in
memory because the two moments are minutes apart.
"""
from __future__ import absolute_import

import json
import logging
import os
import shutil
import time

from unicum.replays.files import battle_in, find

_logger = logging.getLogger('unicum.replays.store')

#: Our own copies, so the client may overwrite its originals freely.
STASH = os.path.join('mods', 'configs', 'unicum', 'replays')

#: What we still owe the server, as [{arenaUniqueId, startedAt, file}].
QUEUE = os.path.join('mods', 'configs', 'unicum', 'replays.json')

#: Battles reported but whose file has not been looked for yet, {id: startedAt}.
#:
#: On disk rather than in memory alone, because the two moments are minutes
#: apart: the results arrive when the battle ends, the file is collected at the
#: garage. A client closed in between, or a dev reload, would otherwise drop the
#: only record that a file was ever wanted, and the battle's replay is gone for
#: good once the next one overwrites it.
WANTED = os.path.join('mods', 'configs', 'unicum', 'replays-wanted.json')

#: How many copies may wait on disk at once.
#:
#: Twenty is 26 MB at the measured average of 1.3 MB, which is a rounding error
#: on a 70 GB game install and still a bound rather than a hope. Past it the
#: oldest is dropped: a replay is a nice-to-have, and filling somebody's disk
#: to keep one would be a poor trade.
_MAX_QUEUED = 20

def stash(arena_id, source):
    """Copy the file somewhere the client will not overwrite it."""
    try:
        if not os.path.isdir(STASH):
            os.makedirs(STASH)
        target = os.path.join(STASH, '%s.wotreplay' % arena_id)
        with open(source, 'rb') as reading:
            data = reading.read()
        if not data:
            return None
        with open(target, 'wb') as writing:
            writing.write(data)
        # Read back what we actually copied, because `find` read the id out of
        # this path and we re-read the path to copy it: by default the client
        # writes every battle to the same name and overwrites it, so a player
        # who queued up in between leaves us a copy of a DIFFERENT battle under
        # this battle's name. The server then answers `not_this_battle`, which
        # is how this was found: battle 90570953574329799 was refused at
        # 01:19:07 and the same battle stored at 01:38:42, once a later pass had
        # copied the right file.
        #
        # A few kilobytes off the front of our own copy, no decryption and no
        # inflation, against a megabyte uploaded for nothing.
        if battle_in(target) != str(arena_id):
            _logger.warning('the file for battle %s changed under us; '
                            'not keeping that copy', arena_id)
            try:
                os.remove(target)
            except (IOError, OSError):
                pass
            return None
        return target
    except (IOError, OSError):
        _logger.exception('could not copy the replay for battle %s', arena_id)
        return None

def forget(entry):
    """Drop our copy of one battle's file."""
    path = (entry or {}).get('file')
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except (IOError, OSError):
        _logger.exception('could not remove %s', path)

def load_queue():
    try:
        with open(QUEUE, 'rb') as handle:
            parsed = json.loads(handle.read().decode('utf-8'))
    except (IOError, OSError, ValueError, UnicodeDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [row for row in parsed
            if isinstance(row, dict) and row.get('arenaUniqueId')]

def save_queue(entries):
    try:
        folder = os.path.dirname(QUEUE)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(QUEUE, 'wb') as handle:
            handle.write(json.dumps(entries).encode('utf-8'))
    except (IOError, OSError):
        _logger.exception('could not write %s', QUEUE)

def load_wanted():
    try:
        with open(WANTED, 'rb') as handle:
            parsed = json.loads(handle.read().decode('utf-8'))
    except (IOError, OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    out = {}
    for key, value in parsed.items():
        try:
            out[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out

def save_wanted(wanted):
    try:
        folder = os.path.dirname(WANTED)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(WANTED, 'wb') as handle:
            handle.write(json.dumps(wanted).encode('utf-8'))
    except (IOError, OSError):
        _logger.exception('could not write %s', WANTED)

def read_answer(body):
    """('stored'|'refused', detail) from the endpoint, or None if it was not it.

    None kept apart from every other answer for the reason `battles.read_answer`
    keeps it apart: the caller deletes a file on the strength of this, and
    reading a login page served with a 200 as "stored, you may delete it" is
    how an archive quietly loses what it was built to keep.
    """
    try:
        answer = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(answer, dict):
        return None
    if answer.get('stored'):
        return ('stored', str(answer['stored']))
    if answer.get('refused'):
        return ('refused', str(answer['refused']))
    return None

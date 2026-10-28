"""Finding a battle's replay on disk, by what is inside it.

By content rather than by name, and that is the point of this module: the
default recording setting writes every battle to the same file name, the "all"
setting builds one out of the map and the tank, and neither is a promise. The
arena id in the file is.

Reads the JSON blocks at the front only. They sit in the clear ahead of the
encrypted stream, so this never touches Blowfish and never inflates anything.
"""
from __future__ import absolute_import

import json
import logging
import os
import struct

_logger = logging.getLogger('unicum.replays.files')

#: Where the client writes replays, from `BattleReplay.__replayDir`.
REPLAY_DIR = os.path.join('replays')

#: The recording in progress, which is never a finished battle.
_IN_PROGRESS = 'temp.wotreplay'

#: Only the newest few files are opened when looking for a battle.
#:
#: A player on "all" can have twelve thousand of them, and reading every header
#: to find one battle would be minutes of disk. The file we want was written
#: moments ago, so the newest handful always contains it.
_CANDIDATES = 6

#: How many of the newest names are asked about on disk, to rank them.
#:
#: Ranking used to mean `getmtime` on every file in the folder: measured at
#: 493 ms of the game thread on a folder of 12,933, to produce six names, and
#: growing with the folder for as long as the player keeps replays. The names
#: themselves carry the battle's start (`20261027_1800_...`) and so sort
#: chronologically as plain text, which picks the newest few out of twelve
#: thousand without asking the disk about any of them.
#:
#: Wider than _CANDIDATES because a name is the start of a battle and the
#: ranking wants the write: a long battle can be named before a short one and
#: finish after it. Eight times over is far more slack than that needs.
_SHORTLIST = _CANDIDATES * 8

#: Enough of the front of a file to hold both JSON blocks.
#:
#: The metadata and the results sit in the clear before the encrypted stream.
#: 256 KB is far more than either needs and avoids pulling a megabyte off disk
#: to read a number.
_HEADER_BYTES = 262144

#: Magic at the top of every replay.
_MAGIC = b'\x12\x32\x34\x11'

def _u32(data, at):
    return struct.unpack_from('<I', data, at)[0]

def battle_in(path):
    """The arena id this replay belongs to, or None if it says nothing.

    Reads the JSON blocks only. They are not encrypted, so this never touches
    Blowfish and never inflates anything; it is a few KB off the front of the
    file. The id lives in the SECOND block, the one written when the battle
    ends, so a replay of a battle still in progress answers None and is
    correctly left alone.
    """
    try:
        with open(path, 'rb') as handle:
            head = handle.read(_HEADER_BYTES)
    except (IOError, OSError):
        return None
    if len(head) < 12 or head[:4] != _MAGIC:
        return None
    try:
        count = _u32(head, 4)
        if count > 16:
            return None
        at = 8
        blocks = []
        for _ in range(count):
            if at + 4 > len(head):
                return None
            size = _u32(head, at)
            at += 4
            if at + size > len(head):
                # The block runs past what we read. Only possible for the
                # stream, which we do not want anyway.
                break
            blocks.append(head[at:at + size])
            at += size
    except Exception:
        return None
    for raw in blocks[1:]:
        try:
            parsed = json.loads(raw.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]
        if isinstance(parsed, dict) and parsed.get('arenaUniqueID'):
            return str(parsed['arenaUniqueID'])
    return None

def _stamped(name):
    """Whether a name carries its battle's start, as `20261027_1800_...`.

    The client's own format for a finished replay under the "all" setting,
    and the only one that says when it was written without asking the disk.
    A name that does not match stays in the shortlist wherever it sits,
    because the other settings reuse one name for every battle and that name
    says nothing at all about its age.
    """
    return (len(name) > 13 and name[:8].isdigit() and name[8] == '_'
            and name[9:13].isdigit() and name[13] == '_')

def candidates():
    """The newest finished replays on disk, newest first."""
    try:
        names = [n for n in os.listdir(REPLAY_DIR)
                 if n.lower().endswith('.wotreplay') and n != _IN_PROGRESS]
    except (IOError, OSError):
        return []
    # Which names are worth a syscall; see _SHORTLIST. Still ranked on the
    # real write time, so the answer is the one statting the whole folder
    # gave -- a name only decides who gets asked.
    stamped, plain = [], []
    for name in names:
        (stamped if _stamped(name) else plain).append(name)
    stamped.sort(reverse=True)
    paths = []
    for name in plain + stamped[:_SHORTLIST]:
        full = os.path.join(REPLAY_DIR, name)
        try:
            paths.append((os.path.getmtime(full), full))
        except (IOError, OSError):
            continue
    paths.sort(reverse=True)
    return [full for _, full in paths[:_CANDIDATES]]

def find(arena_id, paths=None):
    """The file for this battle, found by what is inside it, not by its name.

    By content on purpose: the default setting writes every battle to the same
    name, the "all" setting builds one out of the map and the tank, and neither
    is a promise. The id in the file is.

    `paths` is for a caller looking for several battles in the one pass: the
    newest files on disk are the same for all of them, and listing the folder
    once per battle is work that answers the same thing every time.
    """
    for path in (candidates() if paths is None else paths):
        if battle_in(path) == str(arena_id):
            return path
    return None

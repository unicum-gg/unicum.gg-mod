"""Finding a battle's replay on disk, by what is inside it.

By content rather than by name, and that is the point of this module: the
default recording setting writes every battle to the same file name, the "all"
setting builds one out of the map and the tank, and neither is a promise. The
arena id in the file is.

Reads the JSON blocks at the front only, each at its declared size. They sit
in the clear ahead of the encrypted stream, so this never touches Blowfish and
never inflates anything.
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

#: The most a single JSON block may claim before the file is taken as damaged.
#:
#: Each block is read at the size its own header declares, not through a fixed
#: window. The window was 256 KB and a Frontline battle overflows it: sixty
#: players, one record per tank each, so its results block runs past the
#: window and the battle was never recognised, which is why no Frontline
#: replay ever reached the site. A Random battle's is a fraction of that. The
#: ceiling only guards against a corrupt size field asking for gigabytes.
_MAX_BLOCK_BYTES = 16 * 1024 * 1024

#: Magic at the top of every replay.
_MAGIC = b'\x12\x32\x34\x11'

def _u32(data, at):
    return struct.unpack_from('<I', data, at)[0]

def header_blocks(path):
    """The JSON blocks at the front of a replay, raw, in order; [] if none.

    Each one is read at the size the file declares for it, so a large results
    block (a Frontline battle) is read whole rather than cut off. They are not
    encrypted, so this never touches Blowfish and never inflates anything, and
    it stops before the stream: `count` names the JSON blocks only.
    """
    try:
        with open(path, 'rb') as handle:
            head = handle.read(8)
            if len(head) < 8 or head[:4] != _MAGIC:
                return []
            count = _u32(head, 4)
            if count > 16:
                return []
            blocks = []
            for _ in range(count):
                raw = handle.read(4)
                if len(raw) < 4:
                    break
                size = _u32(raw, 0)
                if size > _MAX_BLOCK_BYTES:
                    break
                block = handle.read(size)
                if len(block) < size:
                    # The file ends inside the block: a recording still being
                    # written, or a truncated copy.
                    break
                blocks.append(block)
            return blocks
    except (IOError, OSError, struct.error):
        return []

def battle_in(path):
    """The arena id this replay belongs to, or None if it says nothing.

    The id lives in the SECOND block, the one written when the battle ends,
    so a replay of a battle still in progress answers None and is correctly
    left alone.
    """
    for raw in header_blocks(path)[1:]:
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

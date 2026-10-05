"""Sending the battle's own `.wotreplay` file, when the client kept one.

Why a file at all
-----------------
`motion.py` already samples every vehicle five times a second, and that is what
the site draws: 64 KB against this file's 1.3 MB. So the file is not how a
battle gets replayed. It is insurance for a 3D view nobody has built yet, which
would want shell trajectories, the geometry of each hit and the state of the
destructible terrain. None of that can be collected after the fact, and a
battle played today is the only chance to have it.

Why it has to be copied aside
-----------------------------
**The file is volatile.** `BattleReplay.enableAutoRecordingBattles` is 1 by
default, which calls `setResultingFileName(FIXED_REPLAY_FILENAME, True)`: every
battle is written to `replays/replay_last_battle.wotreplay` and **overwrites
the one before it**. A player who queues up again while an upload is in flight
destroys the thing being uploaded. So the file is copied into our own folder at
the garage, and the upload reads the copy.

Players who set recording to "all" get a descriptive name per battle instead,
and nothing is overwritten. Both are handled by looking the file up by the
battle id inside it rather than by trusting any name.

Why base64
----------
The body goes out through `BigWorld.fetchURL`, whose `postData` the game itself
never uses with anything but text, and whose binary safety is documented
nowhere. A replay is full of zero bytes. If that path is not binary-safe the
failure is a file truncated at the first one, which still has a valid header
and still names the right battle, and would be archived silently broken. 33% on
the wire, once per battle, buys certainty instead. The SHA-256 that rides along
catches the other half of the problem: a body cut short in transit.
"""
import base64
import hashlib
import json
import logging
import os
import struct
import time

from unicum import config

_logger = logging.getLogger('unicum.replays')


#: Where the client writes replays, from `BattleReplay.__replayDir`.
REPLAY_DIR = os.path.join('replays')

#: The recording in progress, which is never a finished battle.
_IN_PROGRESS = 'temp.wotreplay'

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

#: Only the newest few files are opened when looking for a battle.
#:
#: A player on "all" can have twelve thousand of them, and reading every header
#: to find one battle would be minutes of disk. The file we want was written
#: moments ago, so the newest handful always contains it.
_CANDIDATES = 6

#: Enough of the front of a file to hold both JSON blocks.
#:
#: The metadata and the results sit in the clear before the encrypted stream.
#: 256 KB is far more than either needs and avoids pulling a megabyte off disk
#: to read a number.
_HEADER_BYTES = 262144

#: Magic at the top of every replay.
_MAGIC = b'\x12\x32\x34\x11'

#: Seconds after reaching the garage before anything is collected or sent.
#:
#: Later than the results flush on purpose: the results are what matter, and
#: the garage is already the busiest moment in the client.
_START_DELAY = 40.0

#: The least time between two uploads. One file is 1.7 MB encoded.
_MIN_INTERVAL = 20.0

#: How long a flush may be unanswered before another is allowed to start.
_BUSY_DEADLINE = 120.0

#: How long to stay quiet when the server says it keeps no replays, or that its
#: archive is full. Both are "stop asking", not "try again shortly".
_CLOSED_BACKOFF = 86400.0

#: And when it rate limits us without saying for how long.
_QUOTA_BACKOFF = 900.0


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


def candidates():
    """The newest finished replays on disk, newest first."""
    try:
        names = [n for n in os.listdir(REPLAY_DIR)
                 if n.lower().endswith('.wotreplay') and n != _IN_PROGRESS]
    except (IOError, OSError):
        return []
    paths = []
    for name in names:
        full = os.path.join(REPLAY_DIR, name)
        try:
            paths.append((os.path.getmtime(full), full))
        except (IOError, OSError):
            continue
    paths.sort(reverse=True)
    return [full for _, full in paths[:_CANDIDATES]]


def find(arena_id):
    """The file for this battle, found by what is inside it, not by its name.

    By content on purpose: the default setting writes every battle to the same
    name, the "all" setting builds one out of the map and the tank, and neither
    is a promise. The id in the file is.
    """
    for path in candidates():
        if battle_in(path) == str(arena_id):
            return path
    return None


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


class Uploader(object):
    """Collects the file of each battle at the garage, and sends it."""

    #: Answers that mean this battle will never be wanted. The copy goes.
    FINAL = ('already_stored', 'not_a_player', 'not_this_battle',
             'unknown_battle')
    #: Answers that mean no battle will be wanted for a while. Everything goes.
    CLOSED = ('not_collected', 'archive_full')

    def __init__(self, session, settings, link):
        self._session = session
        self._settings = settings
        self._link = link
        self._queue = load_queue()
        # Battles whose results have been reported but whose file has not been
        # looked for yet: {arenaUniqueId: startedAt}. Read back from disk, so a
        # client closed between the battle and the garage still collects it.
        self._wanted = load_wanted()
        self._busy_since = None
        self._quiet_until = 0.0
        self._last_flush = 0.0

    def install(self):
        try:
            from PlayerEvents import g_playerEvents
            self._session.subscribe(g_playerEvents.onAccountShowGUI, self._on_garage)
        except ImportError:
            _logger.exception('no player events; replays are not collected')
            return
        # The garage may already be up: `onAccountShowGUI` fires when it
        # appears, so a module installed after that (every dev reload) would
        # hold what it is owed until the player next came back from a battle.
        self._session.callback(_START_DELAY, self._collect)
        _logger.info('installed, %d replay(s) waiting, %d wanted',
                     len(self._queue), len(self._wanted))

    def offer(self, arena_id, started_at):
        """Told by the battle reporter that this battle has been written down.

        Only remembered here. The file is not looked for until the garage: the
        client is still finishing the results screen, and reading a megabyte
        off disk on the thread that draws the game is not something to do while
        an animation is running.
        """
        if not arena_id or not started_at:
            return
        self._wanted[str(arena_id)] = int(started_at)
        save_wanted(self._wanted)

    def _sends(self):
        try:
            return self._settings.sends_replays()
        except Exception:
            _logger.exception('could not read the replay setting')
            return False

    def _on_garage(self, *args):
        try:
            self._session.callback(_START_DELAY, self._collect)
        except Exception:
            _logger.exception('could not schedule the replay collection')

    def _collect(self):
        """Find and copy the files of the battles we were told about."""
        if not self._sends():
            self._wanted = {}
            save_wanted(self._wanted)
            return
        if time.time() < self._quiet_until:
            self._wanted = {}
            save_wanted(self._wanted)
            return
        for arena_id, started_at in list(self._wanted.items()):
            del self._wanted[arena_id]
            if any(row.get('arenaUniqueId') == arena_id for row in self._queue):
                continue
            source = find(arena_id)
            if source is None:
                # No file. By far the commonest outcome and not a failure: the
                # player may have recording off entirely.
                _logger.info('no replay on disk for battle %s', arena_id)
                continue
            target = stash(arena_id, source)
            if target is None:
                continue
            while len(self._queue) >= _MAX_QUEUED:
                dropped = self._queue.pop(0)
                _logger.warning('replay queue full at %d; dropping %s',
                                _MAX_QUEUED, dropped.get('arenaUniqueId'))
                forget(dropped)
            self._queue.append({'arenaUniqueId': arena_id,
                                'startedAt': started_at,
                                'file': target})
            _logger.info('replay kept for battle %s, %d waiting',
                         arena_id, len(self._queue))
        save_wanted(self._wanted)
        save_queue(self._queue)
        self.flush()

    def _free(self, now):
        if self._busy_since is None:
            return True
        if now - self._busy_since < _BUSY_DEADLINE:
            return False
        _logger.warning('a replay upload has been in flight for %.0fs; starting another',
                        now - self._busy_since)
        return True

    def flush(self):
        if not self._queue or not self._sends():
            return
        now = time.time()
        if not self._free(now) or now < self._quiet_until:
            return
        if now - self._last_flush < _MIN_INTERVAL:
            return
        try:
            from helpers import isPlayerAccount
            if not isPlayerAccount():
                return
        except ImportError:
            return
        self._busy_since = now
        self._post()

    def _done(self):
        self._busy_since = None

    def _drop_all(self, why):
        """Forget every pending file, and stop asking for a day."""
        _logger.info('the server keeps no replays (%s); dropping %d copy(ies)',
                     why, len(self._queue))
        for entry in self._queue:
            forget(entry)
        self._queue = []
        self._wanted = {}
        save_wanted(self._wanted)
        self._quiet_until = time.time() + _CLOSED_BACKOFF
        save_queue(self._queue)
        self._done()

    def _post(self):
        if not self._sends() or not self._queue:
            self._done()
            return
        entry = self._queue[0]
        try:
            with open(entry['file'], 'rb') as handle:
                data = handle.read()
        except (IOError, OSError):
            # Our own copy is gone. Nothing to send and nothing to keep.
            _logger.warning('the copy for battle %s is unreadable; dropping it',
                            entry.get('arenaUniqueId'))
            self._queue.pop(0)
            save_queue(self._queue)
            self._done()
            return

        body = json.dumps({
            'replay': base64.b64encode(data).decode('ascii'),
            'sha256': hashlib.sha256(data).hexdigest(),
        })

        def answered(response):
            code = getattr(response, 'responseCode', None)
            if code == 429:
                wait = _QUOTA_BACKOFF
                self._quiet_until = time.time() + wait
                self._done()
                _logger.warning('rate limited on replays; quiet for %.0fs', wait)
                return
            if code != 200:
                # Kept. A network that refused one upload is one the next
                # garage retries, and 422 (the body arrived damaged) is
                # precisely a case where the copy on disk is still good.
                self._done()
                _logger.warning('replay upload stopped on HTTP %s, %d still waiting',
                                code, len(self._queue))
                return
            answer = read_answer(getattr(response, 'body', None))
            if answer is None:
                self._done()
                _logger.warning('the server answered 200 with something that is not '
                                'a replay result; %d copy(ies) kept', len(self._queue))
                return
            kind, detail = answer
            if kind == 'refused' and detail in self.CLOSED:
                self._drop_all(detail)
                return
            if kind == 'stored' or detail in self.FINAL:
                forget(entry)
                self._queue = [row for row in self._queue
                               if row.get('arenaUniqueId') != entry.get('arenaUniqueId')]
                save_queue(self._queue)
                _logger.info('replay for battle %s %s, %d waiting',
                             entry.get('arenaUniqueId'),
                             'stored' if kind == 'stored' else detail,
                             len(self._queue))
                if self._queue:
                    self._post()
                else:
                    self._done()
                return
            # A refusal we have not met. Kept rather than guessed at.
            self._done()
            _logger.warning('replay for battle %s refused with an unknown reason (%s); kept',
                            entry.get('arenaUniqueId'), detail)

        self._last_flush = time.time()
        url = '%s/api/game/battles/%s/replay?startedAt=%d' % (
            config.API_BASE.rstrip('/'), entry['arenaUniqueId'],
            int(entry.get('startedAt') or 0))
        self._request(url, answered, body)

    def _request(self, url, answered, body):
        """Signed the same two ways the battle upload is signed."""
        secret = getattr(self._link, 'secret', None)
        if secret:
            self._fetch(url, answered, {'Authorization': 'Bearer %s' % secret}, body)
            return

        def with_token(response):
            if not (response and response.isValid()):
                _logger.info('no web token; replays wait for the next garage')
                self._done()
                return
            self._fetch(url, answered, {
                'X-Wargaming-Token': str(response.getToken()),
                'X-Wargaming-Region': config.REGION,
            }, body)

        try:
            from constants import TOKEN_TYPE
            from gui.shared.utils.requesters import getTokenRequester
            requester = getTokenRequester(TOKEN_TYPE.WGNI)
            if requester.isInProcess():
                self._done()
                return
            requester.request(timeout=10.0)(with_token)
        except Exception:
            _logger.exception('could not ask for a web token')
            self._done()

    def _fetch(self, url, answered, headers, body):
        headers = dict(headers)
        headers['Content-Type'] = 'application/json'
        # Longer than the API default: this body is 1.7 MB where every other
        # call the mod makes is a few KB, and a timeout here costs a replay
        # that no retry can recreate once the client has overwritten it.
        self._session.fetch(url, answered, headers=headers,
                            timeout=max(config.API_TIMEOUT, 60.0),
                            method='POST', post_data=body)


def install(session, settings, link):
    uploader = Uploader(session, settings, link)
    uploader.install()
    return uploader

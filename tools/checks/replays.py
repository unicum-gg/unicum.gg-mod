# -*- coding: utf-8 -*-
"""Checks for the replay archive: what is copied, what is offered, and when.

The property worth protecting here is an ORDER, not a timing. A copy is made as
soon as the client's file exists, because the default setting writes every
battle to `replay_last_battle.wotreplay` and overwrites the one before it, but
the copy is not OFFERED until the battle's own results have reached the server:
a replay whose battle has no row yet is refused, and that refusal used to be
read as a verdict and delete the player's only copy. Three battles went that
way in one evening, on a race the replay won by two to seventeen seconds and
lost exactly once, by 137 milliseconds.
"""

import os
import shutil
import tempfile
import time

from checks.common import check


class _Session(object):
    """Enough of the session for the uploader, remembering what it was asked."""

    def __init__(self):
        self.subscribed = []
        self.scheduled = []
        self.fetched = []

    def subscribe(self, event, handler):
        self.subscribed.append(handler)
        return handler

    def callback(self, delay, func):
        self.scheduled.append((delay, func))

    def repeat(self, period, func):
        self.scheduled.append((period, func))

    def fetch(self, url, callback, **kwargs):
        self.fetched.append((url, callback, kwargs))


class _Settings(object):
    def __init__(self, sends=True):
        self.sends = sends

    def sends_replays(self):
        return self.sends


class _Link(object):
    secret = 'a-secret'


def _uploader(entries, wanted=None):
    """An uploader holding `entries`, with nothing of its own on disk."""
    from unicum.replays.uploader import Uploader
    up = Uploader(_Session(), _Settings(), _Link())
    up._queue = list(entries)
    up._wanted = dict(wanted or {})
    return up


def _copy(arena_id, started_at, tries=None):
    entry = {'arenaUniqueId': arena_id,
             'startedAt': started_at,
             'file': 'copy-%s' % arena_id}
    if tries is not None:
        entry['tries'] = tries
    return entry


def check_replay_answers():
    """Which answers end a copy's life, and which only mean "not yet"."""
    from unicum.replays.uploader import Uploader

    # The regression this file exists for. `unknown_battle` in FINAL is what
    # deleted three replays: it is the server saying it holds no row for this
    # battle, which is a statement about when we asked and not about the battle.
    check('unknown_battle is not final',
          'unknown_battle' not in Uploader.FINAL)
    check('unknown_battle only means not yet',
          'unknown_battle' in Uploader.PENDING)
    # The ones that really are verdicts stay verdicts.
    check('a replay already stored is done with',
          'already_stored' in Uploader.FINAL)
    check('an archive that keeps nothing closes the whole queue',
          'not_collected' in Uploader.CLOSED and 'archive_full' in Uploader.CLOSED)
    # `not_this_battle` condemns the COPY, not the battle: the client rewrites
    # `replay_last_battle.wotreplay` between the id being read out of it and the
    # file being copied, so the copy can hold the next battle. It sat in FINAL,
    # and a copy taken a second too late lost the replay for good.
    check('a copy of the wrong battle is not the end of the battle',
          'not_this_battle' not in Uploader.FINAL
          and 'not_this_battle' in Uploader.RETAKE)
    families = (Uploader.FINAL, Uploader.PENDING, Uploader.CLOSED, Uploader.RETAKE)
    every = [one for family in families for one in family]
    check('no answer is read two ways at once',
          len(every) == len(set(every)))


def check_replay_wrong_copy():
    """A copy of another battle goes, and the battle is looked for again."""
    workdir = tempfile.mkdtemp(prefix='unicum-replays-')
    original = os.getcwd()
    try:
        os.chdir(workdir)
        now = int(time.time())
        entry = _copy('7', now)
        up = _uploader([entry, _copy('8', now)])
        up._wrong_copy(entry)
        check('the wrong copy is dropped',
              [row['arenaUniqueId'] for row in up._queue] == ['8'])
        check('but the battle is wanted again, so the disk is searched afresh',
              up._wanted.get('7') == now)
        check('and the pass ends rather than sending the same bytes again',
              up._busy_since is None)

        # Without a start time there is nothing to re-register under, and
        # inventing one would put a deadline on a battle we cannot date.
        bare = {'arenaUniqueId': '9', 'file': 'copy-9'}
        up = _uploader([bare])
        up._wrong_copy(bare)
        check('a copy with no start time is dropped and not re-wanted',
              up._queue == [] and up._wanted == {})
    finally:
        os.chdir(original)
        shutil.rmtree(workdir, ignore_errors=True)


def check_replay_confirmation():
    """A copy is offered only once its battle has been named by the server."""
    from unicum.replays.uploader import _AFTER_CONFIRMED

    now = int(time.time())
    up = _uploader([_copy('1', now), _copy('2', now)])

    check('nothing is offered before any battle is named', up._next() is None)
    check('and every copy is still there', len(up._queue) == 2)

    up.confirm(['2'])
    chosen = up._next()
    check('a named battle is offered from behind the queue head as well',
          chosen is not None and chosen['arenaUniqueId'] == '2')
    check('one unnamed battle does not park the copies behind it',
          len(up._queue) == 2)

    # The ids arrive off a JSON answer, where a 19-digit arena id may well have
    # come back as a number rather than as text.
    up.confirm([1])
    check('an id is the same id whether it arrives as text or as a number',
          up._next()['arenaUniqueId'] == '1')

    up = _uploader([_copy('9', now)], wanted={'9': now})
    up.confirm(['9'])
    check('a confirmation schedules the sending, not another collection',
          any(delay == _AFTER_CONFIRMED for delay, _ in up._session.scheduled))

    up = _uploader([], wanted={'9': now})
    up.confirm(['9'])
    check('a battle named before its copy exists schedules nothing yet',
          up._session.scheduled == [])


def check_replay_deadlines():
    """A copy nobody ever names is let go of, and only that one."""
    from unicum.replays.deciding import _CONFIRM_DEADLINE

    workdir = tempfile.mkdtemp(prefix='unicum-replays-')
    original = os.getcwd()
    try:
        os.chdir(workdir)
        now = int(time.time())
        old = now - int(_CONFIRM_DEADLINE) - 60
        up = _uploader([_copy('old', old), _copy('new', now)])
        check('nothing is offered while nothing is named', up._next() is None)
        check('a copy past its deadline is dropped, and it alone',
              [row['arenaUniqueId'] for row in up._queue] == ['new'])

        # The try counter cannot do this job: it only ever sees uploads that
        # happened, and a copy that is never offered is never counted.
        up = _uploader([_copy('old', old)])
        up.confirm(['old'])
        check('a named battle is offered however old it is',
              up._next() is not None)
    finally:
        os.chdir(original)
        shutil.rmtree(workdir, ignore_errors=True)


def check_replay_retries():
    """A "not yet" keeps the copy, counts the try, and gives up in the end."""
    from unicum.replays.deciding import _MAX_TRIES

    workdir = tempfile.mkdtemp(prefix='unicum-replays-')
    original = os.getcwd()
    try:
        os.chdir(workdir)
        now = int(time.time())
        first, second = _copy('1', now), _copy('2', now)
        up = _uploader([first, second])
        up._retry(first, 'unknown_battle')
        check('a copy refused for now is kept', len(up._queue) == 2)
        check('the try is counted on the copy, so a restart remembers it',
              first.get('tries') == 1)
        check('and it goes to the back, so it cannot park the queue',
              [row['arenaUniqueId'] for row in up._queue] == ['2', '1'])
        check('the pass ends rather than asking again in the same second',
              up._busy_since is None)

        entry = _copy('3', now, tries=_MAX_TRIES - 1)
        up = _uploader([entry])
        up._retry(entry, 'unknown_battle')
        check('a copy nothing ever accepts is let go of on its last try',
              up._queue == [])
    finally:
        os.chdir(original)
        shutil.rmtree(workdir, ignore_errors=True)


def check_replay_disowning():
    """A battle refused for good takes its replay with it."""
    workdir = tempfile.mkdtemp(prefix='unicum-replays-')
    original = os.getcwd()
    try:
        os.chdir(workdir)
        now = int(time.time())
        up = _uploader([_copy('1', now), _copy('2', now)],
                       wanted={'1': now, '3': now})
        up.disown(['1', '3'])
        check('the copy of a refused battle goes',
              [row['arenaUniqueId'] for row in up._queue] == ['2'])
        check('and so does a file it had not got round to copying',
              up._wanted == {})

        up = _uploader([_copy('1', now)], wanted={'1': now})
        up.disown([])
        check('an answer that refused nothing disowns nothing',
              len(up._queue) == 1 and up._wanted == {'1': now})
    finally:
        os.chdir(original)
        shutil.rmtree(workdir, ignore_errors=True)

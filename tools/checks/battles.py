"""Checks for the battles the mod sends: what is extracted, what is never sent twice,
and what the client is allowed to forget."""

import json
import os
import shutil
import tempfile

from checks.common import check


# A real battle's results, trimmed to what the extractor reads, out of
# 20260926_2141_ussr-R97_Object_140_59_asia_great_wall.wotreplay. Real rather
# than invented because the two values this file most needs to be right about
# are counter-intuitive and both appear here: a survivor's `deathReason` is -1
# and NOT 0 (0 is a real reason, and the commonest one), and a casualty's
# `health` is NEGATIVE on the shot that overkills them.
#
# The map name, the gameplay and the client version are not in the results.
# They are in a replay's meta block, which is why `payload` takes them: this
# battle's were '59_asia_great_wall', 'ctf' and v.2.4.0.1.
RESULTS = {
    'arenaUniqueID': 19011738950705142,
    'common': {'arenaCreateTime': 1790451702,
               'arenaTypeID': 54,
               'bonusType': 1,
               'duration': 245,
               'finishReason': 1,
               'winnerTeam': 1},
    'personal': {'avatar': {'replayURL': 'recordings/eu_2.4.0_3-EU-202-20260926/'
                                         '1790451702.EU.202.19011738950705142.'
                                         '59_asia_great_wall.wotsrvreplay'}},
    'vehicles': {
        '13089208': [{'accountDBID': 531280131, 'team': 1, 'typeCompDescr': 6209,
                      'damageDealt': 4374, 'damageAssistedRadio': 0,
                      'damageAssistedTrack': 59, 'damageAssistedStun': 0,
                      'damageBlockedByArmor': 0, 'damageReceived': 0,
                      'shots': 18, 'directHits': 14, 'piercings': 11, 'spotted': 0,
                      'kills': 1, 'lifeTime': 244, 'deathReason': -1,
                      'capturePoints': 0, 'xp': 892, 'credits': 38307,
                      'health': 2200, 'maxHealth': 2200}],
        '13089212': [{'accountDBID': 595280968, 'team': 2, 'typeCompDescr': 8545,
                      'damageDealt': 872, 'damageAssistedRadio': 0,
                      'damageAssistedTrack': 0, 'damageAssistedStun': 0,
                      'damageBlockedByArmor': 0, 'damageReceived': 2500,
                      'shots': 4, 'directHits': 2, 'piercings': 2, 'spotted': 0,
                      'kills': 0, 'lifeTime': 110, 'deathReason': 0,
                      'capturePoints': 0, 'xp': 36, 'credits': 10487,
                      'health': -3, 'maxHealth': 2500}],
    },
}

ARENA = ('59_asia_great_wall', 'ctf')


def check_battles():
    from unicum.battles import SURVIVED, client_version, cluster, payload

    check('the cluster comes out of the results\' own replayURL',
          cluster(RESULTS['personal']['avatar']['replayURL']) == 'EU-202')
    check('a battle with no recording on the server has no cluster',
          cluster(None) is None and cluster('') is None and cluster('nonsense') is None)

    # The exe reports 2.4.0.0 for every 2.4.0.x, and the difference between
    # 2.4.0.1 and 2.4.0.2 is what decides whether a replay still plays.
    check('the client version is read to its last part, non-breaking spaces and all',
          client_version(u'World\xa0of\xa0Tanks v.2.4.0.1 #952') == '2.4.0.1')
    check('a byte string with a UTF-8 non-breaking space reads the same',
          client_version(u'World\xa0of\xa0Tanks v.2.4.0.1 #952'.encode('utf-8')) == '2.4.0.1')
    check('an unreadable version is left out',
          client_version(None) is None and client_version('World of Tanks') is None)

    battle = payload(RESULTS, ARENA, '2.4.0.1')
    check('the battle id crosses as text, every digit of it',
          battle['arenaUniqueId'] == '19011738950705142')
    check('the start is the battle\'s own, from the server',
          battle['startedAt'] == 1790451702)
    check('the map and the gameplay are the ones the client named',
          battle['mapName'] == '59_asia_great_wall' and battle['gameplayId'] == 'ctf')
    check('the mode, length, winner and ending come from the results',
          (battle['battleType'], battle['duration'], battle['winnerTeam'],
           battle['finishReason']) == (1, 245, 1, 1))
    check('the cluster and the client version ride along',
          battle['server'] == 'EU-202' and battle['clientVersion'] == '2.4.0.1')

    survivor, casualty = battle['vehicles']
    check('the vehicles come out in a stable order, by their battle id',
          [vehicle['id'] for vehicle in battle['vehicles']] == [13089208, 13089212])
    check('a vehicle keeps its account, team and tank',
          (survivor['account'], survivor['team'], survivor['tank']) == (531280131, 1, 6209))
    check('the game\'s own words are renamed to ours, not passed through',
          (survivor['damage'], survivor['track'], survivor['hits'],
           survivor['blocked']) == (4374, 59, 14, 0))
    # The two the schema was wrong about until real battles were read.
    check('a survivor is -1, not 0',
          survivor['deathReason'] == SURVIVED and survivor['health'] == 2200)
    check('a casualty\'s reason can be 0, and their health can be negative',
          casualty['deathReason'] == 0 and casualty['health'] == -3)

    check('results that describe no battle are not sent',
          payload(None, ARENA, 'v') is None
          and payload({}, ARENA, 'v') is None
          and payload(RESULTS, None, 'v') is None)
    # The arena cache answers nothing for an arena this client does not know,
    # and a battle whose map we cannot name is one nobody could read back.
    check('a battle whose arena the client cannot name is not sent',
          payload(RESULTS, (None, None), 'v') is None)


def check_battle_lives():
    """A vehicle that respawned did all of it, and died once."""
    from unicum.battles import payload

    results = dict(RESULTS)
    first = RESULTS['vehicles']['13089212'][0]
    second = dict(first)
    second.update({'damageDealt': 500, 'lifeTime': 80, 'deathReason': 2,
                   'health': 0, 'maxHealth': 1800, 'xp': 40})
    results['vehicles'] = {'13089212': [dict(first), second]}

    vehicle = payload(results, ARENA, 'v')['vehicles'][0]
    check('the deeds of every life are added up',
          vehicle['damage'] == 1372 and vehicle['lifeTime'] == 190 and vehicle['xp'] == 76)
    check('how the battle left them comes from the last life',
          vehicle['deathReason'] == 2 and vehicle['health'] == 0)
    check('the biggest tank they fielded is the one reported',
          vehicle['maxHealth'] == 2500)
    check('a bot has no account to name',
          'account' not in payload(
              {'arenaUniqueID': 1, 'common': {'arenaCreateTime': 1, 'bonusType': 1},
               'vehicles': {'7': [{'team': 1, 'typeCompDescr': 1, 'maxHealth': 1}]}},
              ARENA, 'v')['vehicles'][0])


def check_battle_answer():
    """What the server said, and what the client is therefore allowed to forget.

    This is where the worst defect of the first version lived: the client read
    counts, so an HTML error page served with a 200 parsed as "nothing was
    stored" and the whole queue -- the only copy of those battles -- was
    deleted in one flush.
    """
    from unicum.battles import read_answer, settled

    check('an answer naming what it did is read',
          read_answer('{"stored": ["1", "2"], "known": ["3"], "rejected":'
                      ' [{"arenaUniqueId": "9", "reason": "not_a_player"}]}')
          == (['1', '2'], ['3'], [('9', 'not_a_player')]))
    check('an answer that stored nothing is still an answer',
          read_answer('{"stored": [], "known": [], "rejected": []}') == ([], [], []))

    # Each of these used to read as "the server stored nothing", which the
    # caller acted on by emptying the queue.
    check('an HTML page served with a 200 is not an answer',
          read_answer('<html><body>Sign in</body></html>') is None)
    check('an empty body is not an answer', read_answer('') is None)
    check('nothing at all is not an answer', read_answer(None) is None)
    check('a JSON body that names none of the three lists is not an answer',
          read_answer('{"ok": true}') is None and read_answer('[]') is None)
    check('counts alone are not an answer, which is what they used to be',
          read_answer('{"stored": 2, "known": 1}') is None)

    one, two, three = ({'arenaUniqueId': '1'}, {'arenaUniqueId': '2'},
                       {'arenaUniqueId': '3'})
    check('only what the server named leaves the queue',
          settled([one, two, three], ['1']) == [two, three])
    # A battle the server has told us it will not take is one we would
    # otherwise offer for ever, so it is settled like an accepted one.
    check('a refused battle is settled too, not retried for ever',
          settled([one, two], ['1', '2']) == [])
    check('a battle the answer did not mention is kept',
          settled([one, two], []) == [one, two])


def check_battle_queue():
    """The file on disk: appended a line at a time, never rewritten on the event."""
    from unicum.battles import (QUEUE, _MAX_QUEUED, append_queued, load_queue,
                                queued, save_queue)

    workdir = tempfile.mkdtemp(prefix='unicum-battles-')
    original = os.getcwd()
    try:
        os.chdir(workdir)
        check('an empty store reads as an empty queue', load_queue() == [])
        append_queued({'arenaUniqueId': '1', 'mapName': 'a'})
        append_queued({'arenaUniqueId': '2', 'mapName': 'b'})
        check('appended battles read back in order',
              [row['arenaUniqueId'] for row in load_queue()] == ['1', '2'])
        # Appending is what keeps this off the thread that draws the game: it
        # must not read or rewrite what is already there.
        check('appending leaves the earlier lines alone',
              open(QUEUE, 'rb').read().count(b'\n') == 2)
        with open(QUEUE, 'ab') as handle:
            handle.write(b'{"arenaUniqueId": "3", "mapN')
        check('a line torn by a crash costs only itself',
              [row['arenaUniqueId'] for row in load_queue()] == ['1', '2'])
        save_queue([{'arenaUniqueId': '2'}])
        check('a rewrite keeps exactly what it was given',
              [row['arenaUniqueId'] for row in load_queue()] == ['2'])
    finally:
        os.chdir(original)
        shutil.rmtree(workdir, ignore_errors=True)

    one = {'arenaUniqueId': '1'}
    two = {'arenaUniqueId': '2'}
    check('a battle joins the queue', queued([], one) == [one])
    check('the same battle twice is still one battle', queued([one], dict(one)) == [one])
    check('the queue keeps its order', queued([one], two) == [one, two])

    full = [{'arenaUniqueId': str(n)} for n in range(_MAX_QUEUED)]
    fresh = {'arenaUniqueId': 'new'}
    check('a full queue stays at its cap and drops its oldest, never the newest',
          len(queued(full, fresh)) == _MAX_QUEUED
          and queued(full, fresh)[0] == {'arenaUniqueId': '1'}
          and queued(full, fresh)[-1] == fresh)
    check('a battle already queued costs nobody their place',
          queued(full, dict(full[0]))[0] == {'arenaUniqueId': '1'}
          and len(queued(full, dict(full[0]))) == _MAX_QUEUED)


class _FakeSession(object):
    """Enough of the session for the reporter, remembering what it was asked."""

    def __init__(self):
        self.patched = []
        self.subscribed = []
        self.scheduled = []
        self.fetched = []

    def patch(self, holder, name, build):
        original = getattr(holder, name)
        replacement = build(original)
        setattr(holder, name, replacement)
        self.patched.append((holder, name, original))
        return replacement

    def subscribe(self, event, handler):
        self.subscribed.append(handler)
        return handler

    def callback(self, delay, func):
        self.scheduled.append((delay, func))

    def fetch(self, url, callback, **kwargs):
        self.fetched.append((url, callback, kwargs))


class _Settings(object):
    def __init__(self, sends=True):
        self.sends = sends

    def sends_battles(self):
        return self.sends


class _Arena(object):
    """What ArenaType.g_cache hands back, as far as this module reads it."""

    geometryName = '59_asia_great_wall'
    gameplayName = 'ctf'


def _with_arena_cache():
    """Stub ArenaType so the extractor can name the sample battle's map.

    The map's name is not in the results, it is in the client's arena cache,
    which the fake client has no reason to carry. Without it `payload` is
    right to refuse the battle, and the reporter check would be testing that
    refusal rather than the patch.
    """
    import sys
    import types
    module = sys.modules.get('ArenaType')
    if module is None:
        module = types.ModuleType('ArenaType')
        sys.modules['ArenaType'] = module
    module.g_cache = {RESULTS['common']['arenaTypeID']: _Arena()}
    return module


def check_battle_reporter():
    """The patch on the client's own results, and the in-flight guard."""
    from unicum.battles import _BUSY_DEADLINE, Reporter, _seconds

    workdir = tempfile.mkdtemp(prefix='unicum-reporter-')
    original = os.getcwd()
    try:
        os.chdir(workdir)
        _with_arena_cache()
        session = _FakeSession()
        reporter = Reporter(session, _Settings(), link=None)

        # The client's own postResult, which every mode passes through and
        # whose return value requestResults reads as "were the results
        # posted". A wrapper that swallowed it, or that let our own work
        # raise, would make the client believe the battle never arrived.
        class FakeService(object):
            def postResult(self, result, needToShowUI=True):
                return 'the client answer'

        wrapped = reporter._wrap_post(FakeService.postResult.__func__
                                      if hasattr(FakeService.postResult, '__func__')
                                      else FakeService.postResult)
        service = FakeService()
        check('the client\'s own answer is handed back untouched',
              wrapped(service, RESULTS, True) == 'the client answer')
        check('one battle reached the queue through the patch',
              [row['arenaUniqueId'] for row in reporter._queue] == ['19011738950705142'])
        check('the same results again do not queue it twice',
              wrapped(service, RESULTS, True) == 'the client answer'
              and len(reporter._queue) == 1)

        # Results the extractor cannot read must not stop the client.
        check('unreadable results still let the client post',
              wrapped(service, None, True) == 'the client answer'
              and len(reporter._queue) == 1)

        # A battle the server has already answered for: the client reposts
        # when the player opens it from the notification centre.
        reporter._queue = []
        reporter._settled = ['19011738950705142']
        wrapped(service, RESULTS, True)
        check('a battle the server already took is not queued again',
              reporter._queue == [])

        # The in-flight guard. Every release of it lives in a callback, and
        # the WGNI token requester is a one-slot singleton shared with the
        # loadout upload, so one overlap used to stop this client for good.
        reporter._busy_since = None
        check('nothing in flight means free', reporter._free(1000.0) is True)
        reporter._busy_since = 1000.0
        check('a flush in flight blocks another', reporter._free(1001.0) is False)
        check('one that has run past the deadline does not block for ever',
              reporter._free(1000.0 + _BUSY_DEADLINE + 1) is True)
    finally:
        os.chdir(original)
        shutil.rmtree(workdir, ignore_errors=True)

    check('the server\'s own Retry-After is preferred',
          _seconds({'Retry-After': '42'}) == 42
          and _seconds({'retry-after': 42}) == 42)
    check('a nonsense Retry-After falls back to our own wait',
          _seconds({'Retry-After': 'soon'}) is None
          and _seconds({'Retry-After': '0'}) is None
          and _seconds({'Retry-After': '999999'}) is None
          and _seconds(None) is None)


def check_battle_setting():
    """The box that turns this on, and what it is wired to."""
    from unicum.settings import DEFAULTS, validate
    from unicum.settings_window import from_window, to_window

    # On by default, like the loadouts: a box nobody ticks collects nothing,
    # and a battle names all thirty players, so each client that speaks covers
    # thirty.
    check('sharing battles is on by default', DEFAULTS['sendBattles'] is True)
    check('a settings.json that has never heard of it gets the default',
          validate({})['sendBattles'] is True)
    # The half that matters most now that it is on by default: a player who
    # turns it off must stay off, including across the update that flipped it.
    check('a player who turned it off stays off',
          validate({'sendBattles': False})['sendBattles'] is False)
    check('what the player chose is kept', validate({'sendBattles': True})['sendBattles'] is True)
    check('nonsense in the file falls back to the default',
          validate({'sendBattles': 'yes'})['sendBattles'] is True)

    values = validate({'sendBattles': True})
    check('the window is told the state of the box', to_window(values)['sendBattles'] is True)
    check('the box comes back from the window',
          from_window({'sendBattles': False}) == {'sendBattles': False})
    check('the mod being off takes the uploads with it',
          _sends(validate({'sendBattles': True, 'enabled': False})) is False
          and _sends(validate({'sendBattles': True})) is True)


def _sends(values):
    """`sends_battles` read off a validated dictionary, without a session."""
    from unicum.settings import Settings
    settings = Settings.__new__(Settings)
    settings._values = values
    return settings.sends_battles()

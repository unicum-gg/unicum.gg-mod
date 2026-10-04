"""Checks for the battles the mod reports: what is read, and what is never counted twice.

Everything here works on the server's own results dict, which is what
battle_reports reads. Finding that dict on the object the service passes round
is the one part that cannot be checked against a real client; it lives in
results_dict.py and is checked in checks/results_dict.py.
"""

import os
import tempfile

from checks.battle_fixtures import ACCOUNT, Bonus, Link, Settings, results
from checks.common import check


def check_battle_report_reading():
    from unicum.battle_report import (metrics_of, missing_metrics, outcome_of, own_vehicles,
                                       report_of, survived)

    check('the avatar entry is not taken for a vehicle',
          len(own_vehicles(results()['personal'])) == 1)

    metrics = metrics_of(own_vehicles(results()['personal']))
    check('the client\'s kills are read as frags', metrics['frags'] == 3)
    check('damage is read as it stands', metrics['damage_dealt'] == 3120)
    check('all seven counters are always present', len(metrics) == 7)
    check('a counter the client omits reads as zero',
          metrics_of([{'kills': 1}])['damage_dealt'] == 0)
    # Which is right for the report and wrong for a reader: a mode granting no
    # XP and a client that renamed `xp` make the same battle of zeroes.
    check('a counter the client never sent is named',
          'xp' in missing_metrics([{'damageDealt': 10}]))
    check('and one it sent as zero is not',
          'xp' not in missing_metrics([{'xp': 0}]))
    check('nothing is named when every counter is there',
          not missing_metrics(own_vehicles(results()['personal'])))
    # A respawn mode gives a player several vehicles in one battle, and their
    # battle is the sum of them, which is how Wargaming counts it too.
    check('two vehicles in one battle are summed',
          metrics_of([{'kills': 1}, {'kills': 2}])['frags'] == 3)
    # Booleans are ints in Python: one counted as 1 would quietly inflate a score.
    check('a boolean is not counted as one',
          metrics_of([{'kills': True}])['frags'] == 0)

    check('the winning team means a win', outcome_of(1, 1) == 'win')
    check('the other team winning means a loss', outcome_of(2, 1) == 'loss')
    check('nobody winning means a draw', outcome_of(0, 1) == 'draw')
    # Not a loss: a battle whose outcome we would have to guess is not reported.
    check('an unreadable outcome is no outcome', outcome_of(None, 1) is None)
    check('an unreadable team is no outcome either', outcome_of(1, None) is None)

    check('a vehicle that came out alive survived', survived([{'deathReason': -1}]))
    check('a vehicle that died did not', not survived([{'deathReason': 0}]))
    check('one death in a battle ends its survival',
          not survived([{'deathReason': -1}, {'deathReason': 2}]))
    # False rather than True: a survival wrongly claimed is score the player
    # never earned, where one wrongly denied only costs them.
    check('nothing to read is not a survival', not survived([]))

    report = report_of(results(), constants=Bonus)
    check('a ranked battle is read as ranked', report['mode'] == 'ranked')
    # The modes are told apart by bonus type, so a Stronghold battle is never
    # reported as the ranked one a tournament would score.
    check('a stronghold battle is not read as ranked',
          report_of(results(common={'bonusType': Bonus.SORTIE_2}), constants=Bonus)['mode'] == 'stronghold')
    check('the battle is timed by its end, not by when it was read',
          report['finished_at'] == '2026-09-25T18:10:00Z')
    check('the outcome rides along', report['outcome'] == 'win')
    check('so does the survival', report['survived'] is True)


def check_battle_report_arena_id():
    from unicum.battle_report import arena_id_of, report_of, why_not

    # The whole reason this is a string: 2^64-1 sent as a JSON number comes back
    # a float, and the low-order digits are gone without a word.
    huge = 18446744073709551615
    check('an arena id is a string of digits', arena_id_of({'arenaUniqueID': huge}) == str(huge))
    check('and it keeps every digit',
          arena_id_of({'arenaUniqueID': huge}) == '18446744073709551615')
    check('a missing arena id is None', arena_id_of({}) is None)
    check('a zero arena id is None', arena_id_of({'arenaUniqueID': 0}) is None)
    check('a boolean arena id is None', arena_id_of({'arenaUniqueID': True}) is None)

    # Where the server actually puts it. Read from `common` for a while, which
    # meant a real client's every battle was dropped for having no arena id.
    check('the arena id is read from beside `common`, where the server puts it',
          report_of(results(), constants=Bonus)['arena_unique_id'] == '12457893456789012345')

    inside = results(arenaUniqueID=None)
    inside['common']['arenaUniqueID'] = 99
    check('and still from inside `common`, in case a client keeps it there',
          report_of(inside, constants=Bonus)['arena_unique_id'] == '99')

    check('a battle without an arena id is not reported',
          report_of(results(arenaUniqueID=None), constants=Bonus) is None)
    # An id found beside `common` must not then be read through a `common`
    # that is not there: that line would raise rather than skip the battle.
    check('an arena id with no `common` beside it is not reported',
          report_of({'arenaUniqueID': 1, 'personal': {'8721': {'team': 1}}}) is None)
    check('a battle with no vehicle of ours is not reported',
          report_of({'common': {'arenaUniqueID': 1}, 'personal': {'avatar': {}}}) is None)
    check('a battle whose outcome is unreadable is not reported',
          report_of(results(common={'winnerTeam': None}), constants=Bonus) is None)
    check('something that is not results at all is not reported', report_of(None) is None)

    # What the log says when a battle is refused. The keys alone said the
    # payload was the right one and not which reading refused it, which is the
    # difference between a one-line fix and another evening.
    check('a miss blames the arena id when that is what is missing',
          'arenaUniqueID' in why_not(results(arenaUniqueID=None)))
    check('a miss blames `personal` when no vehicle is ours',
          'personal' in why_not({'arenaUniqueID': 1, 'common': {'winnerTeam': 1},
                                 'personal': {'avatar': {}}}))
    check('a miss blames the teams when the outcome cannot be read',
          'winnerTeam' in why_not(results(common={'winnerTeam': None})))
    check('and it does not pretend to know when every reading passed',
          'mode' in why_not(results()))


def check_battle_report_queue():
    from unicum.battle_report import report_of
    from unicum.report_queue import Queue, deduplicate, trim

    first = {'arena_unique_id': '1'}
    second = {'arena_unique_id': '2'}
    check('a repeated arena is kept once',
          deduplicate([first, second, dict(first)]) == [first, second])
    # The client posts a battle's results again when an older one is opened from
    # the notification centre, and a counter that added it twice would credit
    # score nobody earned.
    check('the first of two reports of one arena is the one kept',
          deduplicate([{'arena_unique_id': '1', 'metrics': {'frags': 3}},
                       {'arena_unique_id': '1', 'metrics': {'frags': 9}}])[0]['metrics']['frags'] == 3)

    # The OLDEST go: a destination scoring this week's tournament wants this
    # week's battles, and a queue that refused new ones would stop capturing.
    reports = [{'arena_unique_id': str(index)} for index in range(5)]
    check('the queue drops its oldest when full',
          [r['arena_unique_id'] for r in trim(reports, 3)] == ['2', '3', '4'])
    check('a queue under the limit is untouched', trim(reports, 10) == reports)

    store = os.path.join(tempfile.mkdtemp(), 'battle-reports.json')
    queue = Queue(store=store)
    check('a fresh queue is empty', queue.all() == [])
    check('a captured battle is queued', queue.add(report_of(results(), constants=Bonus)))
    check('the same battle is not queued twice', not queue.add(report_of(results(), constants=Bonus)))
    check('and the queue still holds the one', len(queue.all()) == 1)

    # The point of the file: a battle that failed to send cannot be played again.
    check('the queue survives the client being closed', Queue(store=store).all() == queue.all())

    queue.drop(['12457893456789012345'])
    check('a report taken by a destination leaves the queue', queue.all() == [])
    check('and it is gone from the file too', Queue(store=store).all() == [])

    # A client killed mid-write leaves a truncated file. The battles in it are
    # gone either way; keeping it would only stop every capture after it.
    with open(store, 'wb') as handle:
        handle.write('{"schema": 1, "reports": [{"arena')
    check('an unreadable queue file starts a new queue', Queue(store=store).all() == [])

    _check_delivery()


def _check_delivery():
    """A report leaves only once every destination owed it has taken it."""
    from unicum.report_queue import Queue

    here, there = 'https://one.test/in', 'https://two.test/in'
    shared = os.path.join(tempfile.mkdtemp(), 'battle-reports.json')
    queue = Queue(store=shared)
    queue.add({'arena_unique_id': '1', 'mode': 'ranked'})
    queue.add({'arena_unique_id': '2', 'mode': 'random'})

    check('a destination is owed the modes it wants', len(queue.pending(here, ['ranked'])) == 1)
    check('and never a mode it did not ask for', queue.pending(here, ['onslaught']) == [])

    queue.mark(here, ['1', '2'])
    check('what a destination has taken is not offered to it again',
          queue.pending(here, ['ranked']) == [])
    # The whole point of tracking it per destination: one site taking a battle
    # must not make the next one think it was already sent there.
    check('but it is still owed to the destination that has not', len(queue.pending(there, ['ranked'])) == 1)
    check('and the delivery survives the client being closed',
          Queue(store=shared).pending(here, ['ranked']) == [])

    owed = {'ranked': [here, there], 'random': [here]}
    check('a report every destination owed it has taken leaves',
          queue.settle(lambda mode: owed.get(mode, ())) == 1)
    check('and the one another destination still waits for stays',
          [report['arena_unique_id'] for report in queue.all()] == ['1'])

    queue.mark(there, ['1'])
    check('the last destination taking it empties the queue',
          queue.settle(lambda mode: owed.get(mode, ())) == 1 and queue.all() == [])

    # A destination switched off after a battle was captured would otherwise
    # pin the queue open behind it for good.
    left = Queue(store=os.path.join(tempfile.mkdtemp(), 'q.json'))
    left.add({'arena_unique_id': '9', 'mode': 'ranked'})
    check('a report nobody is waiting for any more is dropped',
          left.settle(lambda mode: ()) == 1 and left.all() == [])


def check_battle_report_setting():
    from unicum.runtime.session import Session
    from unicum.settings import Settings, validate

    check('battles are reported unless the player says otherwise',
          validate({})['sendBattleResults'] is True)
    check('the switch survives a round trip',
          validate({'sendBattleResults': False})['sendBattleResults'] is False)
    settings = Settings(Session(generation=0),
                        store=os.path.join(tempfile.mkdtemp(), 'settings.json'))
    check('a fresh install reports them', settings.sends_battle_reports())
    settings.update({'sendBattleResults': False})
    check('turning it off stops them', not settings.sends_battle_reports())
    settings.update({'sendBattleResults': True, 'enabled': False})
    check('the mod off reports nothing either', not settings.sends_battle_reports())

    _check_setting_reachable()


def _check_setting_reachable():
    """The switch has to be where the player is, not only in a file.

    A setting that can be changed by hand-editing settings.json is a setting
    the player cannot turn off, and sending their battles anywhere is theirs to
    refuse first of all.
    """
    from unicum.settings import DEFAULTS, validate
    from unicum.settings_window import from_window, native_page, to_window

    values = validate(dict(DEFAULTS))
    check('the switch is in the mod\'s own window', to_window(values)['sendBattleResults'] is True)
    check('and unticking it there reaches settings.json',
          from_window({'sendBattleResults': False})['sendBattleResults'] is False)

    lines = [line.split(u'\t') for line in native_page(values, u'', False).split(u'\n')]
    check('and it has a box in the game\'s own settings tab too',
          any(line[0] == u'checkbox' and line[1] == u'sendBattleResults' for line in lines))


def check_battle_report_capture():
    from unicum.battle_reports import BattleReports
    from unicum.report_queue import Queue

    store = os.path.join(tempfile.mkdtemp(), 'battle-reports.json')
    reports = BattleReports(None, Settings(True), queue=Queue(store=store), link=Link())
    check('a battle that arrives is captured', reports.capture(results(), constants=Bonus))
    check('the same battle arriving again is not', not reports.capture(results(), constants=Bonus))

    # Stamped at capture, not read again when it is sent: a queue outlives the
    # client, and a battle credited to whoever is logged in the next evening is
    # a battle credited to the wrong player.
    check('the account that played the battle is stamped on the report',
          Queue(store=store).all()[0]['account'] == ACCOUNT)

    off = BattleReports(None, Settings(False), link=Link(),
                        queue=Queue(store=os.path.join(tempfile.mkdtemp(), 'q.json')))
    check('nothing is captured while the switch is off', not off.capture(results(), constants=Bonus))

    # A report naming nobody could never be attributed by any destination, so
    # it would sit on disk until the queue dropped it.
    nobody = BattleReports(None, Settings(True), link=Link(account=None),
                           queue=Queue(store=os.path.join(tempfile.mkdtemp(), 'q.json')))
    check('a battle nobody is logged in for is not captured',
          not nobody.capture(results(), constants=Bonus))

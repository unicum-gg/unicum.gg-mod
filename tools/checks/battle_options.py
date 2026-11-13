"""Checks for the battle options: whose ratings each mode shows, and reload announcements."""

from checks.common import check


def check_battle_modes(workdir):
    """Per mode, allies and enemies are switched apart, and survive a partial change."""
    import os
    from unicum.modes import mode_of, wg_mode_of
    from unicum.runtime.session import Session
    from unicum.settings import MODES, Settings, validate
    from unicum.settings_window.codec import from_window, to_window
    from unicum.settings_window.labels import TEAM_CHOICES

    class Bonus(object):
        REGULAR = 1
        RANKED = 22
        COMP7 = 43
        COMP7_LIGHT = 49
        SORTIE_2 = 20
        EPIC_BATTLE = 27
        TRAINING = 2
        EPIC_RANDOM = 24
        FORT_BATTLE_2 = 21

    check('a bonus type tells its mode apart',
          [mode_of(t, Bonus) for t in (1, 22, 43, 49, 20, 27, 2, 999)] ==
          ['random', 'ranked', 'onslaught', 'onslaught', 'stronghold', 'frontline', 'training', 'other'])

    # Which Wargaming block a per-vehicle figure is read from. Grand
    # Battles is the case worth a check of its own: this mod counts it as
    # random, because it is the random queue's own 30v30, while Wargaming
    # keeps a separate `epic` block for it -- and Frontline, which the game
    # also calls epic something, has no block at all.
    check('a bonus type names the block its figures come from',
          [wg_mode_of(t, Bonus) for t in (1, 24, 20, 21, 27, 22, 43, 2, 999)] ==
          ['random', 'epic', 'stronghold_skirmish', 'stronghold_defense',
           None, None, None, None, None])

    values = validate({})
    check('every mode shows both teams by default',
          all(values['modes'][mode] == {'allies': True, 'enemies': True} for mode in MODES))
    check('announcing reloads is off by default', values['autoReload'] == 'off')
    check('a settings.json that said true or false still says what it meant',
          validate({'autoReload': True})['autoReload'] == 'all'
          and validate({'autoReload': False})['autoReload'] == 'off'
          and validate({'autoReload': 'nonsense'})['autoReload'] == 'off')

    store = os.path.join(workdir, 'modes-check', 'settings.json')
    settings = Settings(Session(generation=0), store=store)
    settings.update({'modes': {'ranked': {'enemies': False}}})
    check('hiding the enemies of one mode keeps its allies and the other modes',
          not settings.shows_team('ranked', False) and settings.shows_team('ranked', True)
          and settings.shows_team('random', False))
    check('a mode it does not know follows "other"', settings.shows_team('seasonal', False))

    window = to_window(settings.values())
    check('a mode is one choice of teams in the window',
          TEAM_CHOICES[window['modeRanked']][0] == 'Allies only'
          and TEAM_CHOICES[window['modeOnslaught']][0] == 'Both teams')
    check('every choice of teams reads back to its two switches',
          [from_window({'modeRandom': index})['modes']['random'] for index in range(len(TEAM_CHOICES))]
          == [{'allies': a, 'enemies': e} for _, a, e in TEAM_CHOICES]
          and 'modes' not in from_window({'modeRandom': 7}) and 'modes' not in from_window({'modeRandom': True}))
    check('and read back to the same settings',
          validate(dict(settings.values(), **from_window(window))) == settings.values())


def check_reload_announcer():
    """A shot and the reload it starts are announced once, within the chat's limits."""
    from unicum.auto_reload import COOLDOWN, ReloadAnnouncer

    now = [100.0]
    sent = []
    announcer = ReloadAnnouncer(lambda: now[0], lambda: sent.append(now[0]))

    def settle():
        now[0] += 0.6
        announcer.tick()

    announcer.shells(1, 30, 1)
    announcer.reload(12.0, False)
    settle()
    check('a battle starting, with no shot, is not announced', sent == [])

    now[0] += 20.0
    announcer.shells(1, 29, 1)
    announcer.tick()
    check('a shot alone, with no reload reported, decides nothing', sent == [])
    announcer.reload(12.0, False)
    check('a shot then its reload is announced, the moment the reload lands',
          len(sent) == 1)
    settle()
    check('and the tick that follows does not announce it again', len(sent) == 1)

    now[0] += 12.0
    announcer.reload(12.0, False)
    announcer.shells(1, 28, 1)
    settle()
    check('the reload may come before the shot', len(sent) == 2)

    now[0] += 12.0
    announcer.reload(0.7, False)
    announcer.shells(1, 27, 1)
    now[0] += 0.2
    announcer.reload(11.5, False)
    settle()
    check('the end of the last reload at the shot does not hide the new one', len(sent) == 3)

    now[0] += 12.0
    announcer.shells(1, 26, 1)
    announcer.reload(2.5, False)
    settle()
    check('a reload shorter than the chat cooldown is not announced', len(sent) == 3)

    now[0] += COOLDOWN + 1
    announcer.shells(1, 25, 2)
    announcer.reload(2.0, True)
    settle()
    check('a shell out of a magazine that is not empty is not announced', len(sent) == 3)
    now[0] += 2.0
    announcer.shells(1, 24, 0)
    announcer.reload(20.0, True)
    settle()
    check('the last shell of a magazine is', len(sent) == 4)

    now[0] += 1.0
    announcer.shells(1, 23, 0)
    announcer.reload(20.0, True)
    settle()
    check('nothing within the cooldown of the last announcement', len(sent) == 4)

    now[0] += 30.0
    announcer.shells(1, 22, 1)
    now[0] += 5.0
    announcer.reload(12.0, False)
    announcer.tick()
    check('a shot and a reload far apart are not paired', len(sent) == 4)

    # Autoloaders only: a gun that reloads after every shot says nothing.
    picked = []
    only = ReloadAnnouncer(lambda: now[0], lambda: picked.append(now[0]),
                           allows=lambda magazine: bool(magazine))
    def settle_only():
        now[0] += 0.6
        only.tick()

    now[0] += 60.0
    only.shells(1, 10, 1)
    only.reload(20.0, False)
    settle_only()
    check('a single-shot gun is left out when only autoloaders are announced', picked == [])
    now[0] += 60.0
    only.shells(1, 9, 0)
    only.reload(20.0, True)
    settle_only()
    check('an autoloader with its magazine empty is still announced', len(picked) == 1)

    # A change of shell reloads the gun with the new one, and used to be
    # heard by nothing: the decision only ever armed on a shot.
    now[0] += 60.0
    only.swapped()
    only.reload(20.0, False)
    settle_only()
    check('a change of shell is announced on a single-shot gun, '
          'though its shots are not', len(picked) == 2)

    now[0] += 60.0
    only.swapped()
    only.reload(20.0, True)
    settle_only()
    check('and with shells still in the magazine, which is the point of it',
          len(picked) == 3)

    now[0] += 60.0
    only.swapped()
    settle_only()
    check('a press the client refused, bringing no reload, is not announced',
          len(picked) == 3)

    now[0] += 60.0
    only.swapped()
    only.reload(2.0, False)
    settle_only()
    check('nor a swap whose reload is under the chat cooldown', len(picked) == 3)

    # The shot came first and its reload is the one on the way.
    now[0] += 60.0
    only.shells(1, 8, 2)
    now[0] += 0.1
    only.swapped()
    only.reload(20.0, True)
    settle_only()
    check('a swap does not steal the reload of a shot already waiting',
          len(picked) == 3)

    # Not half a second later. The wait is there to tell the tail of the
    # previous reload from the one the shot started, and a report already
    # over the cooldown cannot lose that comparison, so it is acted on as it
    # arrives. Half a second of silence was heard as lag.
    now[0] += 60.0
    only.shells(1, 7, 0)
    only.reload(20.0, True)
    check('a reload past the cooldown is announced as it arrives, with no tick',
          len(picked) == 4)
    settle_only()
    check('and the settled tick does not announce it twice', len(picked) == 4)

    # The ambiguous case still waits: the first report is the tail of the
    # reload before, and the real one lands a moment later.
    now[0] += 60.0
    only.reload(0.4, True)
    only.shells(1, 6, 0)
    check('a report under the cooldown decides nothing by itself', len(picked) == 4)
    now[0] += 0.2
    only.reload(20.0, True)
    check('the report that settles it is acted on at once', len(picked) == 5)

    # The C key: a clip reloaded on purpose, with shells still in it. Heard by
    # nothing before, for the same reason a swap was not: the decision only
    # ever armed on a shot, and the press fires none.
    now[0] += 60.0
    only.reloaded()
    only.reload(20.0, True)
    settle_only()
    check('a clip reloaded by hand is announced', len(picked) == 6)

    now[0] += 60.0
    only.reloaded()
    settle_only()
    check('a press the client dropped, bringing no reload, is not announced',
          len(picked) == 6)

    # The press answers nothing, so a full clip or an autoloader reaches here
    # as an ordinary press. What keeps it quiet is that no reload follows,
    # which is the case above, not a guess made about the gun.
    now[0] += 60.0
    only.shells(1, 5, 2)
    now[0] += 0.1
    only.reloaded()
    only.reload(20.0, True)
    settle_only()
    check('a manual reload does not steal the reload of a shot already waiting',
          len(picked) == 6)

    # Off means off, for either press as much as for a shot.
    silent = []
    quiet = ReloadAnnouncer(lambda: now[0], lambda: silent.append(now[0]),
                            allows_press=lambda: False)
    now[0] += 60.0
    quiet.swapped()
    quiet.reload(20.0, False)
    now[0] += 0.6
    quiet.tick()
    check('a change of shell says nothing with announcements off', silent == [])
    now[0] += 60.0
    quiet.reloaded()
    quiet.reload(20.0, True)
    now[0] += 0.6
    quiet.tick()
    check('nor does a manual reload', silent == [])


def check_alt_only():
    """The battle ratings that wait for the extended info key, per surface."""
    from unicum.settings import validate
    from unicum.settings_window.codec import from_window, to_window

    values = validate({})
    check('ratings show without Alt by default',
          values['altOnly'] == {'markers': False, 'panel': False, 'tab': False, 'loading': False,
                                'results': False, 'skirmishRoom': False, 'stronghold': False,
                                'minimap': False})
    check('the skirmish room waits for Alt like a battle screen, the contacts never do',
          'skirmishRoom' in values['altOnly'] and 'stronghold' in values['altOnly']
          and 'contacts' not in values['altOnly'])
    values = validate({'altOnly': {'markers': True, 'panel': 'yes', 'loading': True}})
    check('waiting for Alt is set per surface, a bad value keeps the default',
          values['altOnly'] == {'markers': True, 'panel': False, 'tab': False, 'loading': True,
                                'results': False, 'skirmishRoom': False, 'stronghold': False,
                                'minimap': False})
    window = to_window(values)
    check('the Alt choices go to the window and back',
          window['altOnlyMarkers'] == 1 and window['altOnlyPanel'] == 0 and window['altOnlyLoading'] == 1
          and validate(dict(values, **from_window(window))) == values)


def _asked_badges():
    """A Badges that really draws, into a folder nobody keeps."""
    import tempfile

    from checks.extras import _VehicleScales, _badges
    return _badges(tempfile.mkdtemp(), _VehicleScales())


def _refuse(account_id, tank_id):
    """A vehicle reader that fails the check if it is ever called.

    The career choice must cost nothing: not a drawing, and not the read
    behind it. A flag would say the row came out empty; this says why.
    """
    raise AssertionError('asked for a vehicle record on the career choice')


def check_battle_results():
    """Who the post-battle results decorate, and with what."""
    from unicum.battle_results import averages, decorations

    class Entry(object):
        def __init__(self, flags, value):
            self.flags, self.value = flags, value

    class Settings(object):
        def __init__(self, rating=True, flags=True, figures='career'):
            self._rating, self._flags, self._figures = rating, flags, figures

        def metric(self, surface):
            return 'wnx' if self._rating else None

        def wants_vehicle(self, surface):
            return self._figures != 'career'

        def vehicle_metric(self, surface):
            return 'wnx'

        def shows_flags(self, surface):
            return self._flags

        def rating(self, entry, surface):
            return entry.value if self._rating else None

        def shows_average(self, surface):
            return True

        def __getitem__(self, key):
            return {'maxFlags': 2}[key]

    class Flags(object):
        def source(self, code):
            return None if code == 'XX' else 'img://flags/%s.png' % code

    class Scales(object):
        def color(self, metric, value):
            return '#4A92B7' if metric == 'wnx' else None

    entries = {1: Entry(['PL', 'XX', 'DE', 'FR'], 1933.6), 2: Entry(['FR'], 2500), 3: Entry([], None)}
    # The fourth field is the tank that player brought, None for one the
    # results do not name: a bot, or somebody who never spawned.
    players = [(1, ['Kretek_PL'], True, 2849), (2, ['Real_Name', 'Made_Up'], False, 3873),
               (3, ['Nothing'], True, 1281), (4, ['Unknown'], False, None)]
    shown = decorations(players, entries.get, Settings(), Flags(), Scales())
    check('the results show a player\'s rating and the flags that draw, up to the limit',
          shown['Kretek_PL'] == {'score': {'value': 1934, 'color': '#4A92B7'}, 'flags': ['img://flags/PL.png']})
    check('an anonymized player is listed under the real and the made-up name, one with nothing is left out',
          shown['Real_Name']['score']['value'] == 2500 and shown['Made_Up'] == shown['Real_Name']
          and 'Nothing' not in shown and 'Unknown' not in shown)
    check('without a rating shown, the flags alone stay',
          decorations(players[:1], entries.get, Settings(rating=False), Flags(), Scales())
          == {'Kretek_PL': {'score': None, 'flags': ['img://flags/PL.png']}})
    check('on the career alone, no tank is drawn and none is asked for',
          'vehicle' not in shown['Kretek_PL']
          and decorations(players[:1], entries.get, Settings(), Flags(), Scales(),
                          _asked_badges(), _refuse) == {'Kretek_PL': shown['Kretek_PL']})
    entries[5] = Entry([], 1000.0)
    check('each team\'s average is that of its players with a rating',
          averages(players + [(5, ['Other'], True, None)], entries.get, Settings(), Scales())
          == {'allies': {'value': 1467, 'color': '#4A92B7'}, 'enemies': {'value': 2500, 'color': '#4A92B7'}})
    check('no average without a rating shown',
          averages(players, entries.get, Settings(rating=False), Scales()) == {'allies': None, 'enemies': None})

    # ------------------------------------------------ the tank they brought
    from checks.extras import _Record, _VehicleScales

    records = {(1, 2849): _Record(), (2, 3873): _Record(wnx=None)}
    badges = _asked_badges()
    on_tank = decorations(players, entries.get, Settings(figures='tank'), Flags(),
                          _VehicleScales(), badges, lambda a, t: records.get((a, t)))
    check('a row carries what its player has done on the tank they brought',
          on_tank['Kretek_PL']['vehicle']['scope'] == 'mode'
          and 'rating' in on_tank['Kretek_PL']['vehicle']
          and 'battles' in on_tank['Kretek_PL']['vehicle'])
    check('with no rating for that mode, the win rate on the tank stands in',
          'rating' not in on_tank['Real_Name']['vehicle']
          and 'winrate' in on_tank['Real_Name']['vehicle'])
    check('a tank the site holds nothing about adds nothing, and the row stays out',
          'Nothing' not in on_tank and 'Unknown' not in on_tank)
    check('and the rating beside it is still the career one, unchanged',
          on_tank['Kretek_PL']['score'] == shown['Kretek_PL']['score'])

    # A row whose player has neither a rating nor a flag to show used to be
    # dropped. With a tank figure it has something to say, so it stays.
    bare = decorations(players[:1], entries.get, Settings(rating=False, flags=False, figures='tank'),
                       Flags(), _VehicleScales(), badges, lambda a, t: records.get((a, t)))
    check('a row whose only figure is the tank is still drawn',
          'vehicle' in bare['Kretek_PL'] and bare['Kretek_PL']['score'] is None
          and not bare['Kretek_PL']['flags'])

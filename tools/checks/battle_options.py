"""Checks for the battle options: whose ratings each mode shows, and reload announcements."""

from checks.common import check


def check_battle_modes(workdir):
    """Per mode, allies and enemies are switched apart, and survive a partial change."""
    import os
    from unicum.modes import mode_of
    from unicum.runtime.session import Session
    from unicum.settings import MODES, Settings, validate
    from unicum.settings_window import from_window, to_window

    class Bonus(object):
        REGULAR = 1
        RANKED = 22
        COMP7 = 43
        COMP7_LIGHT = 49
        SORTIE_2 = 20
        EPIC_BATTLE = 27
        TRAINING = 2

    check('a bonus type tells its mode apart',
          [mode_of(t, Bonus) for t in (1, 22, 43, 49, 20, 27, 2, 999)] ==
          ['random', 'ranked', 'onslaught', 'onslaught', 'stronghold', 'frontline', 'training', 'other'])

    values = validate({})
    check('every mode shows both teams by default',
          all(values['modes'][mode] == {'allies': True, 'enemies': True} for mode in MODES))
    check('announcing reloads is on by default', values['autoReload'] is True)

    store = os.path.join(workdir, 'modes-check', 'settings.json')
    settings = Settings(Session(generation=0), store=store)
    settings.update({'modes': {'ranked': {'enemies': False}}})
    check('hiding the enemies of one mode keeps its allies and the other modes',
          not settings.shows_team('ranked', False) and settings.shows_team('ranked', True)
          and settings.shows_team('random', False))
    check('a mode it does not know follows "other"', settings.shows_team('seasonal', False))

    window = to_window(settings.values())
    check('modes are spelled flat in the window',
          window['modeRankedEnemies'] is False and window['modeOnslaughtAllies'] is True)
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
    announcer.reload(12.0, False)
    announcer.tick()
    check('nothing is decided before the shot settles', sent == [])
    settle()
    check('a shot then its reload is announced', len(sent) == 1)

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


def check_alt_only():
    """The battle ratings that wait for the extended info key, per surface."""
    from unicum.settings import validate
    from unicum.settings_window import from_window, to_window

    values = validate({})
    check('ratings show without Alt by default', values['altOnly'] == {'markers': False, 'panel': False})
    values = validate({'altOnly': {'markers': True, 'panel': 'yes'}})
    check('waiting for Alt is set per surface, a bad value keeps the default',
          values['altOnly'] == {'markers': True, 'panel': False})
    window = to_window(values)
    check('the Alt switches go to the window and back',
          window['altOnlyMarkers'] is True and window['altOnlyPanel'] is False
          and validate(dict(values, **from_window(window))) == values)

"""Checks for the battle options: whose ratings each mode shows."""

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

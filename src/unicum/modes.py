"""Which kind of battle this is, and whose ratings and flags it shows.

settings.json says per kind of battle whether the allies' and the enemies'
ratings and flags show (settings.MODES). The kind comes from the arena's
bonus type, which tells Onslaught from its Light, training and tournament
variants and a Stronghold battle from a random one; the GUI type is coarser.
A bonus type not listed here, such as a seasonal event, is "other".
"""
import logging

from unicum.settings import MODES

_logger = logging.getLogger('unicum.modes')

# settings.MODES -> the ARENA_BONUS_TYPE names they cover. Names rather than
# numbers: a name missing from this client's constants is skipped.
_BONUS_TYPES = {
    'random': ('REGULAR', 'RANDOM_NP2', 'EPIC_RANDOM'),
    'ranked': ('RANKED',),
    'onslaught': ('COMP7', 'COMP7_LIGHT', 'TOURNAMENT_COMP7', 'TRAINING_COMP7'),
    'stronghold': ('SORTIE_2', 'FORT_BATTLE_2', 'CLAN', 'GLOBAL_MAP'),
    'frontline': ('EPIC_BATTLE', 'EPIC_BATTLE_TRAINING'),
    'training': ('TRAINING', 'EPIC_RANDOM_TRAINING'),
}

assert set(_BONUS_TYPES) | set(['other']) == set(MODES)


def mode_of(bonus_type, constants=None):
    """The settings.MODES name of an arena bonus type."""
    if constants is None:
        from constants import ARENA_BONUS_TYPE as constants
    for mode, names in _BONUS_TYPES.items():
        if bonus_type in [getattr(constants, name) for name in names if hasattr(constants, name)]:
            return mode
    return 'other'


def current_mode():
    """The kind of the battle in progress, or None outside one."""
    import BigWorld
    bonus_type = getattr(BigWorld.player(), 'arenaBonusType', None)
    return mode_of(bonus_type) if bonus_type is not None else None


def team_filter(settings):
    """team -> whether this battle shows the ratings and flags of that team's players.

    Read once for a pass over the battle's players. Shows everything
    whenever it cannot tell, so a missing piece never hides anything.
    """
    try:
        mode = current_mode()
        arena = None
        if mode is not None:
            from helpers import dependency
            from skeletons.gui.battle_session import IBattleSessionProvider
            arena = dependency.instance(IBattleSessionProvider).getArenaDP()
    except Exception:
        _logger.exception('could not tell whose ratings this battle shows')
        mode = arena = None
    if mode is None or arena is None:
        return lambda team: True

    def shows(team):
        return team is None or settings.shows_team(mode, arena.isAllyTeam(team))

    return shows

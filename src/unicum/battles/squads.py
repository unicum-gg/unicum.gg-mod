"""Which vehicles of a battle were in a platoon, numbered the way the game does.

The results carry a `prebattleID` per player, and it is tempting to read every
shared one as a platoon. It is not: a training room hands the SAME id to
everyone in it, so three players in a room read as a platoon and five do not,
which is exactly what a reader saw on the site and what the client never
shows. The client decides it per arena GUI type: each mode registers a squad
finder (random, Grand Battles, Frontline, Onslaught...), a training room
registers none, and each finder only counts a group whose size is a platoon's
in that mode (2 to 3, 2 to 7 in Onslaught), numbered from 1 within each team.

So nothing here restates that table. `finder_for` asks the client which finder
it would use for this battle's GUI type, and `squads` feeds it the battle,
which is what the game's own post-battle screen does
(`gui.battle_results.reusable.ReusableInfo.__findSquads`). A mode Wargaming
adds tomorrow comes with its own finder and is right here on the same day.

Kept apart from `extract` so that one stays pure: a replay read outside the
client has no finder to ask, and goes without platoons rather than with a guess.
"""
from __future__ import absolute_import

import logging

from unicum.battles.extract import _int

_logger = logging.getLogger('unicum.battles.squads')


def finder_for(gui_type):
    """The client's own squad finder class for this GUI type, or None.

    None for a mode that has no platoons at all, a training room among them,
    and outside the client. The post-battle finder wins when a mode registers
    one, as it does in the client.
    """
    try:
        from gui.shared.system_factory import (collectPostbattleSquadFinder,
                                               collectSquadFinder)
    except ImportError:
        return None
    try:
        finder = collectPostbattleSquadFinder(gui_type)
        if finder is None:
            finder, _ = collectSquadFinder(gui_type)
        return finder
    except Exception:
        _logger.exception('could not ask the client for the squad finder of %r',
                          gui_type)
        return None


def squads(results, finder_class):
    """{battle vehicle id: platoon number} for this battle, empty when none.

    `finder_class` is what `finder_for` answered. Every vehicle absent from
    the answer was not in a platoon, which is most of them.
    """
    if finder_class is None or not isinstance(results, dict):
        return {}
    players = results.get('players') or {}
    vehicles = results.get('vehicles') or {}
    by_account = {}
    for key, entry in vehicles.items():
        records = entry if isinstance(entry, list) else [entry]
        for record in records:
            if isinstance(record, dict) and _int(record.get('accountDBID')):
                by_account[_int(record.get('accountDBID'))] = _int(key)
                break
    seen = []
    for account, info in players.items():
        if not isinstance(info, dict):
            continue
        vehicle = by_account.get(_int(account))
        prebattle = _int(info.get('prebattleID'))
        if vehicle and prebattle:
            seen.append((_int(info.get('team')), prebattle, vehicle))
    if not seen:
        return {}
    try:
        # The teams the battle actually had, where the client reads them off
        # the arena type: the finder keys its tallies by team and refuses one
        # it was not built with.
        finder = finder_class(sorted(set(team for team, _, _ in seen)))
        for team, prebattle, vehicle in seen:
            finder.addVehicleInfo(team, prebattle, vehicle)
        return dict((_int(vehicle), _int(index))
                    for vehicle, index in finder.findSquads())
    except Exception:
        _logger.exception('could not number the platoons of this battle')
        return {}

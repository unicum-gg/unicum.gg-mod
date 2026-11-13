"""What a row of the post-battle results says, and which battles it counts.

Kept apart from the view because it is the half that answers a question
rather than the half that talks to the client: given a battle's results and
what the reader asked for, which name carries which figures. The package's
`__init__` owns the Gameface model, the extended info key, and the reloading
of the page's code; none of that is needed to know what a row should read.

The results carry each player twice, under their real name and under the
made-up one an anonymized battle shows to everybody else, and the page draws
whichever of the two the client handed it. Both are listed here, so the row
that ends up drawn finds the real account's figures either way.
"""
from __future__ import absolute_import

import logging

from unicum import figures, modes

_logger = logging.getLogger('unicum.battle_results.rows')

SURFACE = 'battleResults'


def tank_of(vehicles, account_id):
    """The vehicle a player brought, by its compact descriptor, or None.

    The client answers 0 for an account it holds no vehicle for, and 0 is not
    a tank: it travels on as None, so a caller can write `if tank_id` and mean
    it. A bot and a player who never spawned both arrive here as 0.
    """
    try:
        return vehicles.getVehicleInfo(vehicles.getVehicleID(account_id)).intCD or None
    except Exception:
        _logger.debug('no vehicle for %s in these results', account_id, exc_info=True)
        return None


def mode_of(results):
    """The per-vehicle mode key of the battle these results are of, or None.

    Read from the results and never from the arena. This screen opens in the
    garage, where the arena is either gone or already somebody else's, and a
    battle reopened from the notifications days later is very often not the
    mode being played now.
    """
    try:
        return modes.wg_mode_of(results.reusable.bonusType)
    except Exception:
        _logger.debug('could not read the mode of these results', exc_info=True)
        return None


def players_of(results):
    """[(account id, [the names the page may show], on the player's team, tank id)].

    The names are the real one, then the made-up one of an anonymized player.
    """
    own_team = results.reusable.personal.avatar.team
    vehicles = results.reusable.vehicles
    players = []
    for account_id, info in results.reusable.players.getPlayerInfoIterator():
        names = [info.realName]
        if info.fakeName and info.fakeName != info.realName:
            names.append(info.fakeName)
        players.append((account_id, names, info.team == own_team,
                        tank_of(vehicles, account_id)))
    return players


def averages(players, entry_of, settings, scales):
    """{'allies': {value, color} or None, 'enemies': ...}: each team's mean known rating."""
    metric = settings.metric(SURFACE)
    out = {'allies': None, 'enemies': None}
    if metric is None or not settings.shows_average(SURFACE):
        return out
    for side, ally in (('allies', True), ('enemies', False)):
        values = [settings.rating(entry_of(account_id), SURFACE) for account_id, _, on_team, _ in players
                  if on_team == ally and entry_of(account_id) is not None]
        values = [value for value in values if value is not None]
        if values:
            value = int(round(sum(values) / float(len(values))))
            color = scales.color(metric, value)
            out[side] = {'value': value, 'color': color} if color else None
    return out


def decorations(players, entry_of, settings, flags, scales, badges=None, vehicle_of=None):
    """{name shown: {score, flags, vehicle}} for the players with something to show.

    `vehicle_of(account id, tank id)` gives what that player has done on the
    tank they brought, in the mode this battle was. It is optional because
    the figure is: a reader on the career alone never asks for it, and the
    two callers that only want names and flags pass nothing.

    A player the site knows nothing about is skipped whole, tank included.
    The two reads are asked for together and the page is redrawn as each
    lands, so a row that is missing only because its player has not arrived
    yet appears a moment later rather than never.
    """
    metric = settings.metric(SURFACE)
    limit = settings['maxFlags'] if settings.shows_flags(SURFACE) else 0
    wants_vehicle = (vehicle_of is not None and badges is not None
                     and settings.wants_vehicle(SURFACE))
    vehicle_metric = settings.vehicle_metric(SURFACE) if wants_vehicle else None
    out = {}
    for account_id, names, _, tank_id in players:
        entry = entry_of(account_id)
        if entry is None:
            continue
        value = settings.rating(entry, SURFACE)
        color = scales.color(metric, value) if value is not None else None
        sources = [flags.source(code) for code in entry.flags[:limit]] if limit else []
        shown = {'score': {'value': int(round(value)), 'color': color} if color else None,
                 'flags': [source for source in sources if source]}
        if wants_vehicle and tank_id:
            found = figures.vehicle_figures(badges, scales,
                                            vehicle_of(account_id, tank_id), vehicle_metric)
            if found is not None:
                shown['vehicle'] = found
        if shown['score'] or shown['flags'] or shown.get('vehicle'):
            for name in names:
                if name:
                    out[name] = shown
    return out

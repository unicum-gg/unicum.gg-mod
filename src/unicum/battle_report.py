"""One battle, read out of the results dict the client was sent.

Pure reading, and nothing about when or how a battle arrives: that is
`battle_reports.py`, which captures, and `results_dict.py`, which finds the
dict. Separated because the two halves fail for unrelated reasons -- where to
sit was wrong twice over on a real client while every one of these readings
was right, and once the capture was attached it was a misread key that dropped
every battle. Each half is worth reading without the other in the way.

A report that had to be guessed at is worse than a missing one, because it
counts. So every reading here refuses rather than approximates.
"""
import time

from unicum import modes


# The seven counters that travel per battle, and the key each one is read from
# in the client's own results. The client's spelling on the left is not ours:
# `kills` is `frags` everywhere a rating is computed.
METRICS = (
    ('xp', 'xp'),
    ('damage_dealt', 'damageDealt'),
    ('damage_received', 'damageReceived'),
    ('frags', 'kills'),
    ('spotted', 'spotted'),
    ('capture_points', 'capturePoints'),
    ('dropped_capture_points', 'droppedCapturePoints'),
)

# `personal` is keyed by vehicle, with one entry that is not a vehicle.
_NOT_A_VEHICLE = ('avatar', )

# What the client puts in `deathReason` for a vehicle that came out alive.
_ALIVE = -1


def own_vehicles(personal):
    """The player's own vehicles in a battle's results.

    A battle holds more than one when the mode lets a player respawn, so
    nothing here assumes a single vehicle: the counters are summed over all of
    them, which is also how Wargaming counts a Frontline battle.
    """
    if not isinstance(personal, dict):
        return []
    return [value for key, value in personal.items()
            if key not in _NOT_A_VEHICLE and isinstance(value, dict)]


def missing_metrics(vehicles):
    """The counters no vehicle reported, which the report therefore counts as zero.

    A counter the client never sent and a counter the player did not earn are
    the same number in the report, deliberately: a destination validating an
    incomplete one would reject it. They are not the same fact though, and only
    this tells them apart -- a client that renames a counter would otherwise
    report a battle of zeroes that looks exactly like an idle player.
    """
    return [ours for ours, theirs in METRICS
            if not any(theirs in vehicle for vehicle in vehicles)]


def metrics_of(vehicles):
    """{our name: value} for the seven counters, summed over the vehicles.

    A counter the client does not report reads as zero rather than being left
    out: a destination validating the report would reject an incomplete one,
    and a missing counter is indistinguishable from an idle player anyway.
    """
    out = {}
    for ours, theirs in METRICS:
        total = 0
        for vehicle in vehicles:
            value = vehicle.get(theirs)
            # Booleans are ints in Python and would count as 1. Nothing in
            # these results is a bool today, and a client that changed its
            # mind about one would corrupt a counter rather than skip it.
            if isinstance(value, bool) or not isinstance(value, (int, long, float)):
                continue
            total += int(value)
        out[ours] = max(total, 0)
    return out


def survived(vehicles):
    """Whether the player came out of the battle alive.

    Alive means no vehicle of theirs died, which is what Wargaming's own
    `survived_battles` counts. With nothing to read, the answer is False: a
    survival wrongly claimed is worth score the player did not earn, where one
    wrongly denied only costs them.
    """
    if not vehicles:
        return False
    for vehicle in vehicles:
        if vehicle.get('deathReason', _ALIVE) != _ALIVE:
            return False
    return True


def outcome_of(winner_team, own_team):
    """'win', 'loss' or 'draw' from the winning team and the player's own.

    Team 0 is the client's way of saying nobody won. Returns None when either
    team is unreadable: a battle whose result we would have to guess is not
    captured at all, rather than counted as a loss.
    """
    if not isinstance(winner_team, (int, long)) or isinstance(winner_team, bool):
        return None
    if not isinstance(own_team, (int, long)) or isinstance(own_team, bool):
        return None
    if winner_team == 0:
        return 'draw'
    return 'win' if winner_team == own_team else 'loss'


def finished_at(common, now=None):
    """The battle's end as `YYYY-MM-DDTHH:MM:SSZ`, in UTC.

    Built from the arena's creation and its duration, which is when the battle
    actually ended -- not when this ran. The two differ by however long the
    results took to arrive, and by everything a queued report waits on disk.

    Falls back to now when the client gives neither, which is wrong by seconds
    and never by days; a destination refusing a future timestamp would reject
    the report, so nothing here is allowed to drift forward.
    """
    created = common.get('arenaCreateTime') if isinstance(common, dict) else None
    duration = common.get('duration') if isinstance(common, dict) else None
    stamp = None
    if isinstance(created, (int, long, float)) and not isinstance(created, bool):
        stamp = float(created)
        if isinstance(duration, (int, long, float)) and not isinstance(duration, bool):
            stamp += float(duration)
    if stamp is None:
        stamp = time.time() if now is None else now
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(stamp))


def arena_id_of(holder):
    """`arenaUniqueID` out of the dict holding it, as decimal digits, or None.

    A string because it is an unsigned 64-bit value: sent as a JSON number it
    is already damaged, most parsers falling back to a float beyond 2^53 and
    dropping the low-order digits without a word. Python 2 holds it exactly as
    a long, so the only place it can be lost is on the wire.
    """
    if not isinstance(holder, dict):
        return None
    value = holder.get('arenaUniqueID')
    if isinstance(value, bool) or not isinstance(value, (int, long)):
        return None
    if value <= 0:
        return None
    return str(value)


def report_of(results, mode=None, now=None, constants=None):
    """One battle's report, in the shape a destination is given, or None.

    None whenever the results are not a battle this can honestly describe: no
    arena id, no readable outcome, no vehicle of the player's own. A report
    that had to be guessed at is worse than a missing one, because it counts.

    `constants` is passed through to `modes.mode_of`, as its own callers do, so
    the mode a battle is read as can be checked outside a client.
    """
    if not isinstance(results, dict):
        return None
    common = results.get('common')
    # The server puts `arenaUniqueID` beside `common`, not inside it: a real
    # client's payload carries arenaUniqueID, avatars, common, personal,
    # players and vehicles at the top. It was modelled the other way round
    # here, so every battle was dropped for having no arena id. Both places
    # are read now, the outer one first.
    arena_id = arena_id_of(results) or arena_id_of(common)
    if arena_id is None:
        return None
    # Guarded for its own sake: now that the id can be found without `common`
    # having been read, this is the first line that would touch it.
    if not isinstance(common, dict):
        return None
    vehicles = own_vehicles(results.get('personal'))
    if not vehicles:
        return None
    own_team = vehicles[0].get('team')
    outcome = outcome_of(common.get('winnerTeam'), own_team)
    if outcome is None:
        return None
    if mode is None:
        mode = modes.mode_of(common.get('bonusType'), constants)
    return {
        'arena_unique_id': arena_id,
        'mode': mode,
        'finished_at': finished_at(common, now),
        'outcome': outcome,
        'survived': survived(vehicles),
        'metrics': metrics_of(vehicles),
    }


def why_not(results):
    """Which reading a results dict failed, for a log line that can be acted on.

    The keys alone were not enough the first time this fired: they said the
    payload was the right one, and not which of the three readings refused it.
    """
    if not isinstance(results, dict):
        return 'not a dict at all'
    common = results.get('common')
    if arena_id_of(results) is None and arena_id_of(common) is None:
        return 'no usable arenaUniqueID, either beside `common` or inside it'
    if not isinstance(common, dict):
        return 'no `common`'
    vehicles = own_vehicles(results.get('personal'))
    if not vehicles:
        return 'no vehicle of the player own under `personal`'
    if outcome_of(common.get('winnerTeam'), vehicles[0].get('team')) is None:
        return 'neither `winnerTeam` nor the player own team could be read'
    return 'every reading passed, so the mode is what refused it'

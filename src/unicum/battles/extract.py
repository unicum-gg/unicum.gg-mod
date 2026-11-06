"""One battle's results, turned into what the site is sent.

Pure: results in, a dict out, and the tables that say which field becomes
which. No client, no session, no disk, which is why
`tools/backfill_replays.py` can build the same body out of a `.wotreplay`
months later by calling `payload` directly.
"""
from __future__ import absolute_import

import logging

from unicum.battles.naming import cluster

_logger = logging.getLogger('unicum.battles.extract')

# The result's own key for each of ours. Renamed rather than passed through:
# `damageAssistedRadio` is the game's word for it and `radio` is ours, and the
# short names are the ones the site's column names were built from.
_FROM = {
    'team': 'team',
    'tank': 'typeCompDescr',
    'damage': 'damageDealt',
    'radio': 'damageAssistedRadio',
    'track': 'damageAssistedTrack',
    'stun': 'damageAssistedStun',
    'blocked': 'damageBlockedByArmor',
    'received': 'damageReceived',
    'shots': 'shots',
    'hits': 'directHits',
    'piercings': 'piercings',
    'spotted': 'spotted',
    'kills': 'kills',
    'lifeTime': 'lifeTime',
    'deathReason': 'deathReason',
    'capturePoints': 'capturePoints',
    'xp': 'xp',
    'credits': 'credits',
    'health': 'health',
    'maxHealth': 'maxHealth',
}

# The rest of what the game's own post-battle panel shows about one player,
# which the results carry and the roster has no column for.
#
# Sent only when non-zero, which is most of the saving: `sniper` is 0 on every
# vehicle that never shot past 300 metres, `repaired` on everyone without a
# repair kit used on an ally, and so on. Thirty vehicles carrying ten zeroes
# each would be a third of a battle's payload spent saying nothing.
_EXTRA = {
    # Damage dealt from more than 300 metres, which is the game's own wording.
    'sniper': 'sniperDamageDealt',
    'splash': 'explosionHits',
    'hitsReceived': 'directHitsReceived',
    'piercingsReceived': 'piercingsReceived',
    # Shots that landed and did nothing: the armour did its job.
    'bounced': 'noDamageDirectHitsReceived',
    # What would have landed had the armour not been there.
    'potential': 'potentialDamageReceived',
    'repaired': 'healthRepair',
    # Metres driven.
    'mileage': 'mileage',
    'defended': 'droppedCapturePoints',
    'teamDamage': 'tdamageDealt',
    # Allies destroyed, which the game shows beside the damage done to them.
    'teamKills': 'tkills',
    # Hits taken from a shell's blast rather than from the shell itself.
    'splashReceived': 'explosionHitsReceived',
    # Enemy vehicles damaged, which the game shows beside the ones destroyed.
    'damaged': 'damaged',
}

# The battle-scoped vehicle id of whoever killed them, so the panel can name
# them the way the game does ("Destroyed by a shot (isakh)"). Not in `_EXTRA`
# because 0 is meaningful here: it is what the results say when nobody did.
_KILLER = 'killerID'

# Which of those are summed when a vehicle has more than one record, the rest
# describing the vehicle rather than its deeds. Measured: every battle in a
# 1424-replay sample had exactly one record per vehicle, Onslaught included.
# Frontline is where it is not: a player who respawns in another tank gets
# one record PER TANK under the same vehicle id (the client's own
# `reusable/vehicles.py` keys its details by `(vehicleID, intCD)`), so the
# sum is the whole battle and `_TANK` below says which tank did what.
_SUMMED = ('damage', 'radio', 'track', 'stun', 'blocked', 'received', 'shots',
           'hits', 'piercings', 'spotted', 'kills', 'lifeTime',
           'capturePoints', 'xp', 'credits')

# What each tank of a multi-tank vehicle is sent with, so the site can say
# which tank did what. A subset on purpose: the totals above already carry
# everything, and this is the breakdown the game's own Frontline report draws.
# Sent only when there is more than one record, which is never outside the
# respawn modes, so a random battle's payload does not grow by a byte.
_TANK = ('damage', 'radio', 'track', 'stun', 'blocked', 'spotted', 'kills',
         'xp', 'lifeTime')

# What `deathReason` says when nobody killed them. Not 0: that is a real
# reason, and the commonest one.
SURVIVED = -1

# What the game's own Detailed Report shows about credits, experience and
# bonds, mapped from the results' own names.
#
# **This exists for the reporting client alone.** The results carry it under
# `personal.<vehicle>`, and the other twenty-nine players have no economy in
# the payload at any price: it is what this account earned, not a fact about
# the battle. So it is sent once per battle rather than per vehicle, and the
# site shows it only on the page of the player it belongs to.
_PERSONAL = {
    'creditsBase': 'originalCredits',
    'creditsBooster': 'boosterCredits',
    'creditsEvent': 'eventCredits',
    'creditsOrder': 'orderCredits',
    'creditsPenalty': 'creditsPenalty',
    'creditsCompensation': 'creditsContributionIn',
    'creditsSubtotal': 'subtotalCredits',
    'repairCost': 'autoRepairCost',
    'credits': 'credits',
    'xpBase': 'originalXP',
    'xpBooster': 'boosterXP',
    'xpEvent': 'eventXP',
    'xpPremiumVehicle': 'premiumVehicleXP',
    'xpPenalty': 'xpPenalty',
    'xp': 'xp',
    'freeXp': 'freeXP',
    # The free experience behind each experience line, which the game's
    # Detailed Report draws as a second column beside the experience.
    'freeXpBase': 'originalFreeXP',
    'freeXpBooster': 'boosterFreeXP',
    'freeXpEvent': 'eventFreeXP',
    'freeXpOrder': 'orderFreeXP',
    'freeXpWotPlus': 'wotPlusFreeXP',
    'freeXpSubtotal': 'subtotalFreeXP',
    # WoT Plus's own battle bonus, and the credits it put aside in the
    # reserve stock, both lines of the game's report.
    'creditsWotPlus': 'wotPlusCredits',
    'xpWotPlus': 'wotPlusXP',
    'piggyBank': 'piggyBank',
    'crewXp': 'tmenXP',
    'bonds': 'crystal',
    'bondsBase': 'originalCrystal',
    # The mark of excellence this battle left the gun at, as a whole percent.
    #
    # The state AFTER the battle, because that is the only one the results
    # carry: there is a `prevMarkOfMastery` for the mastery badge and nothing
    # of the kind for this, so what a single battle GAINED is the difference
    # with the last battle in the same tank, which is the server's job and not
    # the client's.
    #
    # Dropped when it is zero, like everything else in this table, and that is
    # exactly right here: Battle Royale reports zero because the mode does not
    # count towards marks at all, and writing that down would read as a gun
    # that fell back to nothing.
    'markPercent': 'damageRating',
}

# The two costs the results report as a list, `[credits, gold]`: only the
# credits half is spent by default, and a player who paid gold for shells did
# so deliberately and knows.
_PERSONAL_LISTS = {
    'ammoCost': 'autoLoadCost',
    'suppliesCost': 'autoEquipCost',
}

def _int(value, default=0):
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _vehicle(key, records):
    """One vehicle's whole battle, however many lives it took.

    The identity comes from the first record and the deeds are summed, because
    a vehicle that respawned did all of it. `health` and `deathReason` come
    from the LAST record: they describe how the battle left them, and the first
    life of a respawning vehicle always ends in a death.

    `tank` stays the first record's, which is what every site reader keyed on
    before `tanks` existed. It is NOT the tank that did the totals: on a
    Frontline battle played in three tanks it was the only one named, and the
    whole battle's damage was drawn under it. `tanks` is what says otherwise.
    """
    first, last = records[0], records[-1]
    out = {'id': _int(key)}
    account = _int(first.get('accountDBID'))
    # A vehicle with no account is a bot, and has nobody to name.
    if account:
        out['account'] = account
    for ours, theirs in _FROM.items():
        out[ours] = _int(first.get(theirs))
    for ours in _SUMMED:
        out[ours] = sum(_int(record.get(_FROM[ours])) for record in records)
    out['health'] = _int(last.get('health'))
    out['deathReason'] = _int(last.get('deathReason'), SURVIVED)
    out['maxHealth'] = max(_int(record.get('maxHealth')) for record in records)
    # The medals the battle awarded them, by the game's own ids. Kept only when
    # there are any: they are empty on about 99 of every 100 vehicles, and an
    # empty list on every one of thirty would be a third of the payload saying
    # nothing. `inBattleAchievements` is always empty in the results, so it is
    # not read.
    medals = []
    for record in records:
        medals.extend(_int(one) for one in (record.get('achievements') or [])
                      if _int(one))
    if medals:
        out['medals'] = medals
    for ours, theirs in _EXTRA.items():
        total = sum(_int(record.get(theirs)) for record in records)
        if total:
            out[ours] = total
    # The marks painted on this gun, for EVERY vehicle in the battle and not
    # just ours: the results carry it in the public half, so a battle names the
    # marks of all thirty.
    #
    # From the last record and never summed. It is a state the vehicle arrived
    # with, so adding a respawn's together would give six marks on a gun that
    # has three. Kept only when there are any, like the medals above: thirty
    # vehicles carrying an explicit zero would be a third of the payload
    # saying nothing, and an absent mark reads as no mark.
    marks = _int(last.get('marksOnGun'))
    if marks:
        out['marks'] = marks
    killer = _int(last.get(_KILLER))
    if killer:
        out['killer'] = killer
    if len(records) > 1:
        out['tanks'] = [_tank(record) for record in records]
    return out

def _tank(record):
    """One tank's share of a vehicle that fought in several."""
    out = {'tank': _int(record.get(_FROM['tank']))}
    for ours in _TANK:
        out[ours] = _int(record.get(_FROM[ours]))
    out['deathReason'] = _int(record.get('deathReason'), SURVIVED)
    return out

def payload(results, arena, version, squads=None):
    """What one battle is sent as, or None when these results do not describe one.

    `arena` is (map name, gameplay id) for the battle's arenaTypeID, and
    `version` the client's own: neither is in the results, both are in the
    client. `squads` is {battle vehicle id: platoon number}, which only the
    client's own squad finder can say (see `battles.squads`); absent, no
    vehicle is marked. Everything else is read from what the server sent.
    """
    if not isinstance(results, dict):
        return None
    arena_id = results.get('arenaUniqueID')
    common = results.get('common') or {}
    vehicles = results.get('vehicles') or {}
    started = _int(common.get('arenaCreateTime'))
    map_name, gameplay = arena if arena else (None, None)
    if not arena_id or not started or not map_name or not vehicles:
        return None
    rows = []
    for key, entry in vehicles.items():
        records = [record for record in (entry if isinstance(entry, list) else [entry])
                   if isinstance(record, dict)]
        if records:
            row = _vehicle(key, records)
            # Only on the vehicles that were in one, like the medals: most
            # players go in alone, and a platoon number of 0 on each of them
            # would say nothing.
            squad = (squads or {}).get(row['id'])
            if squad:
                row['squad'] = squad
            rows.append(row)
    if not rows:
        return None
    avatar = (results.get('personal') or {}).get('avatar') or {}
    out = {
        # Text, not a number: the game's id runs to 19 digits and no JSON
        # number survives that. The server's column is text for the same
        # reason, so the value that crosses is the value the game produced.
        'arenaUniqueId': str(arena_id),
        'startedAt': started,
        'mapName': map_name,
        'battleType': _int(common.get('bonusType')),
        'gameplayId': gameplay,
        'duration': _int(common.get('duration')),
        'winnerTeam': _int(common.get('winnerTeam')),
        'finishReason': _int(common.get('finishReason')),
        'clientVersion': version,
        'server': cluster(avatar.get('replayURL')),
        'vehicles': sorted(rows, key=lambda row: row['id']),
    }
    own = personal(results)
    if own:
        out['personal'] = own
    return out

def personal(results):
    """What this battle earned the reporting player, or None.

    Read from `personal.<vehicle>`, which is the one block the results carry
    about the client's own account rather than about the battle. Sent field by
    field and only when non-zero, so a battle that earned no bonds and fired no
    reserve carries neither.

    **One entry per tank played, summed.** In Frontline a player who respawns
    in another tank has one `personal` entry per tank, and the game's Detailed
    Report adds them all (`reusable/personal.py` feeds every one to its
    economics records). Reading the first one alone, which this did, sent a
    third of the battle's credits for a player who fought in three tanks.
    """
    if not isinstance(results, dict):
        return None
    entries = [value for key, value in (results.get('personal') or {}).items()
               if key != 'avatar' and isinstance(value, dict)]
    if not entries:
        return None
    out = {}
    for ours, theirs in _PERSONAL.items():
        # The mark of excellence is a state of ONE gun, so it means nothing
        # summed, and with several guns there is no saying whose it is.
        if ours == 'markPercent':
            continue
        value = sum(_int(own.get(theirs)) for own in entries)
        if value:
            out[ours] = value
    if len(entries) == 1:
        mark = _int(entries[0].get(_PERSONAL['markPercent']))
        if mark:
            out['markPercent'] = mark
    for ours, theirs in _PERSONAL_LISTS.items():
        # A tuple, not a list: the client's own results schema declares
        # autoLoadCost and autoEquipCost as `tuple`, and DictPacker keeps that
        # type all the way to postResult. Testing for `list` alone sent every
        # battle up with no ammunition and no supplies cost, so the detailed
        # report showed neither and the credits never added up. The fixture in
        # tools/checks used lists, because it was lifted out of a .wotreplay,
        # whose second block is JSON -- which is how a check passed on data the
        # client never produces.
        cost = 0
        for own in entries:
            value = own.get(theirs)
            cost += (_int(value[0]) if isinstance(value, (list, tuple)) and value
                     else _int(value))
        if cost:
            out[ours] = cost
    # The first victory of the day, as the game's factor times ten (20 is the
    # x2). Not in `_PERSONAL`, because zero is not what a battle without it
    # says: every other battle of the day carries 10, and sending that would
    # put a field saying nothing on every battle. A factor, so never summed.
    daily = max(_int(own.get('dailyXPFactor10')) for own in entries)
    if daily > 10:
        out['xpDailyFactor'] = daily
    if any(own.get('isPremium') for own in entries):
        out['premium'] = True
    return out or None

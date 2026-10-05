"""The battles this client played, sent to unicum.gg.

Wargaming's API publishes an account's running totals and nothing whatever
about a single battle: not who was in it, not what each of them did, not which
map or which cluster. So a battle on unicum.gg exists only because somebody
running this mod was in it, and this module is the whole of that path.

Where the numbers come from
---------------------------
The client's own battle results, handed to us by the game. Not a .wotreplay:
recording is a player setting, and new accounts do not get it at its highest,
so reading files would quietly collect from a subset of players and call it the
playerbase. The results arrive in every client, for every battle, whatever that
setting says.

Read by patching `BattleResultsService.postResult`, which receives the raw
dictionary the server sent. **Not `onResultPosted`**, which was the first
attempt: that event hands over a stats controller, and only the Gameface one
(`RandomBattleResultStatsCtrl`) implements `getResults`. Every Flash mode --
Ranked, CyberSport, Stronghold, Maps Training, and the fallback any bonus type
we have not met lands on -- inherits `IBattleResultStatsCtrl.getResults`, which
returns None. Those modes would have reported nothing at all, and said so in
the log as if the extractor had refused them. `postResult` is upstream of every
composer, so it is the one place that sees all of them.

The raw dictionary is the same structure a replay carries in its second block,
which is how the extractor below could be measured against 1913 real battles
before it ever ran in the client. What the dictionary does NOT carry is the
map's name, the gameplay and the client version: those live in a replay's meta
block, not in the results, so they are read from the client here and passed in.

What one battle costs
---------------------
Measured over 1913 real battles: 10.2 KB of JSON for a thirty-vehicle random
battle, 4.9 KB for a fourteen-vehicle skirmish, 20.8 KB for a sixty-vehicle
Frontline. Against a 1293 KB replay of the same battle, which is the reason
this is what gets sent rather than the file.

One battle, any sender
----------------------
A battle names all thirty of its players, so it reaches the server from
whichever participant happens to run the mod, and the id it is keyed by is a
deduplication key rather than an ownership one: the second sender of a battle
is answered "already known" rather than refused. Coverage grows by whole teams.

When it sends, and what it is allowed to forget
-----------------------------------------------
Appended to a file the moment the results land, sent from the garage. Appended
rather than rewritten because this runs on the thread that draws the game: one
battle is a 10 KB line, where rewriting a full queue was 44 ms and three
dropped frames, landing exactly on the results screen's animation.

**A battle leaves the queue only when the server names it.** The answer lists
ids, never counts, and that is load-bearing: the queue is the only copy of a
battle not yet stored, and a count cannot be acted on, so a client reading
counts had no choice but to drop the whole batch on any answer it could not
make sense of -- including an HTML error page served with a 200.
"""
import json
import logging
import os
import re
import time

from unicum import config

_logger = logging.getLogger('unicum.battles')

# Where battles wait until the server has taken them, one JSON object a line.
#
# A line a battle, because this file is appended to from the battle results
# handler, on the thread that draws the game. The whole-file rewrite only
# happens once a flush has been answered, which is at the garage.
QUEUE = os.path.join('mods', 'configs', 'unicum', 'battles.ndjson')

# The ids the server has already answered for, so a battle whose results the
# player reopens from the notification centre is not offered again.
#
# `postResult` runs again for a battle read out of the client's own cache, so
# without this every stroll through the notification centre reposted up to
# twenty battles. This is the same job `loadouts.py` gives its fingerprint
# store, and leaving it out was the half of that pattern this module missed.
SETTLED = os.path.join('mods', 'configs', 'unicum', 'battles-sent.json')

# How many settled ids to remember. A fortnight of heavy play, at 20 bytes an
# id, so the file stays a few kilobytes.
_MAX_SETTLED = 500

# Battles per request.
#
# Five rather than the twenty-five the endpoint accepts, and the measurement is
# why: a thirty-vehicle battle is 10.2 KB of JSON, so twenty-five of them would
# be a quarter of a megabyte in one call on a connection we know nothing about,
# and a failure would throw all of it away rather than a fifth of it. That is
# the same reasoning as the loadout upload's own batch, and the same numbers.
_BATCH = 5

# How long after the garage appears the queue is flushed. The garage has a
# sign-in, a carousel and the rest of this mod to draw first, and a battle
# that has already waited for the player to leave the results screen is not
# urgent.
_START_DELAY = 12.0

# How long after a battle's results land before trying to send it.
#
# The results arrive while the player is still watching the screen they
# arrived on, and the client is busy drawing it. Waiting means the send lands
# in the quiet afterwards.
_SEND_DELAY = 25.0

# The least time between two flushes that actually sent something.
#
# Only a flush that reached the network counts, which is the fix for a real
# bug: the interval used to be stamped before the attempt, so the garage's
# flush at +12s consumed it and the battle's own at +25s was refused for the
# 13 seconds between them. The battle then waited for the next garage, which is
# after the next battle.
_MIN_INTERVAL = 60.0

# How long a flush may be in flight before another is allowed to start.
#
# `_busy` has callbacks for its only releases, and three paths never reach one.
# The worst is real rather than theoretical: the WGNI token requester is a
# process-wide singleton with ONE callback slot (TokenRequester.py), shared
# with the loadout upload and the client's own portal code, and whoever asks
# last overwrites the pending callback AND cancels the timeout that would have
# rescued it. Without a deadline here, one unlucky overlap stopped this client
# sending battles until the next reload, silently, while its queue filled up
# and started dropping the oldest.
_BUSY_DEADLINE = 90.0

# How long to stay quiet after the server says the quota is spent.
#
# Without this, every garage restarted the same burst against a server that
# had just said no, and the queue never drained. The server's own Retry-After
# is preferred when it sends one.
_QUOTA_BACKOFF = 900.0

# How many battles the queue keeps when the server cannot be reached.
#
# A queue that grew without a bound would be a file that grows without a
# bound. Two hundred battles is more than a week of heavy play, and past that
# the oldest go: a battle nobody could send for a week is one somebody else in
# it has almost certainly sent already. Dropping one is logged, because it is
# the only place this module loses data on purpose.
_MAX_QUEUED = 200

# The cluster, out of the results' own replayURL:
#     .../1790451702.EU.202.19011738950705142.59_asia_great_wall.wotsrvreplay
# Wargaming records every random battle server-side and hands the player the
# path to their own. Nothing public serves it, so what is kept is the cluster
# the battle ran on, which is a fact nobody else collects.
_CLUSTER = re.compile(r'\.([A-Z]{2,5})\.([0-9]{1,4})\.')

# The client version, out of `World of Tanks v.2.4.0.2 #966`. The exe reports
# only `2.4.0.0`, and the difference between 2.4.0.1 and 2.4.0.2 is exactly
# what decides whether a replay still plays.
_VERSION = re.compile(r'v\.\s*([0-9]+(?:\.[0-9]+)+)')

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
    # Enemy vehicles damaged, which the game shows beside the ones destroyed.
    'damaged': 'damaged',
}

# The battle-scoped vehicle id of whoever killed them, so the panel can name
# them the way the game does ("Destroyed by a shot (isakh)"). Not in `_EXTRA`
# because 0 is meaningful here: it is what the results say when nobody did.
_KILLER = 'killerID'

# Which of those are summed when a vehicle has more than one life, the rest
# describing the vehicle rather than its deeds. Measured: every battle in a
# 1424-replay sample had exactly one record per vehicle, Onslaught included,
# so this is for the respawn modes and for whatever the game adds next.
_SUMMED = ('damage', 'radio', 'track', 'stun', 'blocked', 'received', 'shots',
           'hits', 'piercings', 'spotted', 'kills', 'lifeTime',
           'capturePoints', 'xp', 'credits')

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
    'crewXp': 'tmenXP',
    'bonds': 'crystal',
    'bondsBase': 'originalCrystal',
}

# The two costs the results report as a list, `[credits, gold]`: only the
# credits half is spent by default, and a player who paid gold for shells did
# so deliberately and knows.
_PERSONAL_LISTS = {
    'ammoCost': 'autoLoadCost',
    'suppliesCost': 'autoEquipCost',
}


def cluster(replay_url):
    """'EU-202' out of the results' own replayURL, or None."""
    if not replay_url:
        return None
    found = _CLUSTER.search(replay_url)
    return '%s-%s' % (found.group(1), found.group(2)) if found else None


def client_version(full):
    """'2.4.0.2' out of 'World of Tanks v.2.4.0.2 #966', or None.

    The xml version rather than the exe's, which stops at `2.4.0.0`: a replay
    plays on the build it was recorded on and not on the one before it.
    """
    if not full:
        return None
    if isinstance(full, bytes):
        # A byte string holding a UTF-8 non-breaking space would raise on the
        # unicode replace below, and the only symptom would be every battle
        # carrying no client version at all.
        try:
            full = full.decode('utf-8')
        except UnicodeDecodeError:
            full = full.decode('latin-1')
    # The client writes these with non-breaking spaces.
    found = _VERSION.search(full.replace(u'\xa0', u' '))
    return found.group(1) if found else None


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
    killer = _int(last.get(_KILLER))
    if killer:
        out['killer'] = killer
    return out


def payload(results, arena, version):
    """What one battle is sent as, or None when these results do not describe one.

    `arena` is (map name, gameplay id) for the battle's arenaTypeID, and
    `version` the client's own: neither is in the results, both are in the
    client. Everything else is read from what the server sent.
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
            rows.append(_vehicle(key, records))
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
    """
    if not isinstance(results, dict):
        return None
    own = None
    for key, value in (results.get('personal') or {}).items():
        if key != 'avatar' and isinstance(value, dict):
            own = value
            break
    if own is None:
        return None
    out = {}
    for ours, theirs in _PERSONAL.items():
        value = _int(own.get(theirs))
        if value:
            out[ours] = value
    for ours, theirs in _PERSONAL_LISTS.items():
        value = own.get(theirs)
        cost = _int(value[0]) if isinstance(value, list) and value else _int(value)
        if cost:
            out[ours] = cost
    if own.get('isPremium'):
        out['premium'] = True
    return out or None


def arena_names(arena_type_id):
    """(map name, gameplay id) for an arenaTypeID, from the client's own cache.

    `45_north_america` and `ctf`, the arena's names rather than the titles a
    player reads: a title is translated, and these have to mean the same thing
    in every client that sends one.
    """
    try:
        import ArenaType
        arena = ArenaType.g_cache.get(arena_type_id)
        if arena is None:
            return None
        return (getattr(arena, 'geometryName', None),
                getattr(arena, 'gameplayName', None))
    except Exception:
        _logger.exception('could not name arena %s', arena_type_id)
        return None


def full_version():
    """The client's own version, as '2.4.0.2', or None."""
    try:
        from helpers import getFullClientVersion
        return client_version(getFullClientVersion())
    except Exception:
        _logger.exception('could not read the client version')
        return None


def read_answer(body):
    """(stored, known, [(id, reason)]) from the endpoint, or None if it was not it.

    **None is the whole point of this function.** An answer the mod cannot
    parse and an answer that stored nothing have to be different things,
    because the caller deletes what the server names and the queue is the only
    copy. Reading a login page or a CDN error served with a 200 as "nothing was
    stored, carry on" is how a whole queue disappears in one flush.

    So an answer counts only if it names at least one of the three lists, and
    all of them are read by name rather than by position.
    """
    try:
        answer = json.loads(body)
    except (TypeError, ValueError):
        return None
    if not isinstance(answer, dict):
        return None
    stored, known, refused = [], [], []
    named = False
    for key, into in (('stored', stored), ('known', known)):
        value = answer.get(key)
        if isinstance(value, list):
            named = True
            into.extend(str(item) for item in value if item)
    rejected = answer.get('rejected')
    if isinstance(rejected, list):
        named = True
        for row in rejected:
            if isinstance(row, dict) and row.get('arenaUniqueId'):
                refused.append((str(row['arenaUniqueId']), row.get('reason') or '?'))
    return (stored, known, refused) if named else None


def load_queue():
    """The battles a previous session wrote down and could not send."""
    out = []
    try:
        with open(QUEUE, 'rb') as handle:
            lines = handle.read().decode('utf-8').splitlines()
    except (IOError, OSError, UnicodeDecodeError):
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            battle = json.loads(line)
        except ValueError:
            # One torn line, from a crash mid-append, is not worth the rest of
            # the queue.
            continue
        if isinstance(battle, dict) and battle.get('arenaUniqueId'):
            out.append(battle)
    return out


def append_queued(battle):
    """Add one battle to the file, without reading or rewriting it.

    This runs inside the battle results handler, on the thread that draws the
    game. One line is 10 KB and a fraction of a millisecond; serialising the
    whole queue here was 31 ms of `json.dumps` plus 12 ms of write, measured on
    200 battles, landing on the results screen's own animation.
    """
    try:
        folder = os.path.dirname(QUEUE)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(QUEUE, 'ab') as handle:
            handle.write(json.dumps(battle).encode('utf-8') + b'\n')
        return True
    except (IOError, OSError):
        _logger.exception('could not append to %s', QUEUE)
        return False


def save_queue(battles):
    """Rewrite the file. Only ever called once a flush has been answered."""
    try:
        folder = os.path.dirname(QUEUE)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(QUEUE, 'wb') as handle:
            handle.write(b''.join(json.dumps(battle).encode('utf-8') + b'\n'
                                  for battle in battles))
    except (IOError, OSError):
        _logger.exception('could not write %s', QUEUE)


def load_settled():
    try:
        with open(SETTLED, 'rb') as handle:
            stored = json.loads(handle.read().decode('utf-8'))
    except (IOError, OSError, ValueError, UnicodeDecodeError):
        return []
    if not isinstance(stored, list):
        return []
    return [str(item) for item in stored if item][-_MAX_SETTLED:]


def save_settled(ids):
    try:
        folder = os.path.dirname(SETTLED)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(SETTLED, 'wb') as handle:
            handle.write(json.dumps(list(ids)[-_MAX_SETTLED:]).encode('utf-8'))
    except (IOError, OSError):
        _logger.exception('could not write %s', SETTLED)


def queued(battles, battle):
    """`battles` with `battle` added, deduplicated, oldest dropped past the cap."""
    out = [row for row in battles
           if row.get('arenaUniqueId') != battle['arenaUniqueId']]
    out.append(battle)
    return out[-_MAX_QUEUED:]


def settled(battles, done):
    """`battles` without the ids the server has answered for.

    Only the ids. A battle the answer did not mention stays in the queue, even
    when the call succeeded: a partial acceptance the client cannot see is
    exactly the case where dropping the batch loses data for good.
    """
    answered = set(done)
    return [row for row in battles if row.get('arenaUniqueId') not in answered]


class Reporter(object):

    def __init__(self, session, settings, link):
        self._session = session
        self._settings = settings
        self._link = link
        self._queue = load_queue()
        self._settled = load_settled()
        self._busy_since = None
        self._last_flush = 0.0
        self._quiet_until = 0.0

    def install(self):
        """Read every mode's results, by patching the one place they all pass.

        See the module docstring: `onResultPosted` only carries readable
        results for the Gameface path, so a patch on `postResult` is what makes
        Ranked, Stronghold, CyberSport and everything else report at all.
        """
        try:
            from gui.battle_results.service import BattleResultsService
        except ImportError:
            _logger.exception('no battle results service; battles are not reported')
            return
        self._session.patch(BattleResultsService, 'postResult', self._wrap_post)
        try:
            from PlayerEvents import g_playerEvents
            # The garage, which is the one place the account is there to prove.
            self._session.subscribe(g_playerEvents.onAccountShowGUI, self._on_garage)
        except ImportError:
            _logger.exception('no player events; battles only flush after one lands')
        # The garage may already be up: the event fires when it appears, and a
        # mod installed after that would otherwise hold its queue until the
        # player next came back from a battle. `flush` refuses anywhere else.
        self._session.callback(_START_DELAY, self.flush)
        _logger.info('installed, %d battle(s) waiting', len(self._queue))

    def _wrap_post(self, original):
        """`postResult` with a look at the raw results on the way through.

        The client's own return value decides whether `requestResults`
        considers the battle posted, so it is handed back untouched and our
        own work is guarded whole: an exception here would make the client
        believe the results failed to arrive.
        """
        reporter = self

        def postResult(service, result, needToShowUI=True):
            try:
                reporter._record(result)
            except Exception:
                _logger.exception('could not write down a battle')
            return original(service, result, needToShowUI)

        return postResult

    def _sends(self):
        try:
            return self._settings.sends_battles()
        except Exception:
            _logger.exception('could not read the battle setting')
            return False

    def _record(self, results):
        """One battle's results, straight off the server. Write it down."""
        if not self._sends():
            return
        arena_id = str((results or {}).get('arenaUniqueID') or '')
        if arena_id and arena_id in self._settled:
            # Reopened from the notification centre: the client replays the
            # whole path for a cached battle, and this is the same battle.
            return
        common = (results or {}).get('common') or {}
        battle = payload(results,
                         arena_names(_int(common.get('arenaTypeID'), -1)),
                         full_version())
        if battle is None:
            _logger.info('battle %s carried nothing we could describe', arena_id or '?')
            return
        if any(row.get('arenaUniqueId') == battle['arenaUniqueId']
               for row in self._queue):
            return
        if len(self._queue) >= _MAX_QUEUED:
            dropped = self._queue[0]
            _logger.warning('the queue is full at %d; dropping battle %s unsent',
                            _MAX_QUEUED, dropped.get('arenaUniqueId'))
        self._queue = queued(self._queue, battle)
        if append_queued(battle):
            _logger.info('battle %s written down, %d waiting',
                         battle['arenaUniqueId'], len(self._queue))
        self._session.callback(_SEND_DELAY, self.flush)

    def _on_garage(self, *args):
        try:
            self._session.callback(_START_DELAY, self.flush)
        except Exception:
            # onAccountShowGUI is a SafeEvent (events_container._createEvent),
            # so the client would swallow this anyway and keep calling the
            # listeners after us. Guarded all the same, to say in the log that
            # the flush was never scheduled rather than leave it a silence.
            _logger.exception('could not schedule a flush at the garage')

    def _free(self, now):
        """Whether no flush is in flight, or the one that is has run too long."""
        if self._busy_since is None:
            return True
        if now - self._busy_since < _BUSY_DEADLINE:
            return False
        _logger.warning('a flush has been in flight for %.0fs with no answer; '
                        'starting another', now - self._busy_since)
        return True

    def flush(self):
        """Send what is waiting, a batch at a time."""
        if not self._queue or not self._sends():
            return
        now = time.time()
        if not self._free(now):
            return
        if now < self._quiet_until:
            return
        if now - self._last_flush < _MIN_INTERVAL:
            return
        try:
            from helpers import isPlayerAccount
            if not isPlayerAccount():
                return
        except ImportError:
            return
        self._busy_since = now
        self._post()

    def _done(self):
        self._busy_since = None

    def _post(self):
        # Re-read every batch: unticking the box has to stop the flush that is
        # already running, not only the next one. A full queue is forty calls.
        if not self._sends():
            _logger.info('battle sharing turned off; %d battle(s) stay on disk',
                         len(self._queue))
            self._done()
            return
        batch = self._queue[:_BATCH]
        if not batch:
            self._done()
            return
        body = json.dumps({'battles': batch})

        def answered(response):
            code = getattr(response, 'responseCode', None)
            if code == 429:
                # Back off rather than come straight back at the next garage,
                # which is what turned a spent quota into a permanent burst.
                wait = _seconds(getattr(response, 'responseHeaders', None)) or _QUOTA_BACKOFF
                self._quiet_until = time.time() + wait
                self._done()
                _logger.warning('the server is rate limiting us; quiet for %.0fs, '
                                '%d battle(s) still waiting', wait, len(self._queue))
                return
            if code != 200:
                # Kept, not dropped: a battle a network refused is one the next
                # garage sends.
                self._done()
                _logger.warning('battle upload stopped on HTTP %s, %d still waiting',
                                code, len(self._queue))
                return
            answer = read_answer(getattr(response, 'body', None))
            if answer is None:
                # A 200 carrying something that is not our answer. Nothing is
                # named, so nothing is forgotten.
                self._done()
                _logger.warning('the server answered 200 with something that is not '
                                'an upload result; %d battle(s) kept',
                                len(self._queue))
                return
            stored, known, refused = answer
            # Exactly what was named, and nothing else.
            names = list(stored) + list(known) + [id_ for id_, _ in refused]
            if not names:
                self._done()
                _logger.warning('the server named no battle at all; %d kept',
                                len(self._queue))
                return
            self._queue = settled(self._queue, names)
            self._settled = (self._settled + names)[-_MAX_SETTLED:]
            save_queue(self._queue)
            save_settled(self._settled)
            if refused:
                _logger.warning('%d battle(s) refused for good: %s', len(refused),
                                ', '.join('%s %s' % pair for pair in refused))
            _logger.info('%d stored, %d already known, %d waiting',
                         len(stored), len(known), len(self._queue))
            if self._queue:
                self._post()
            else:
                self._done()

        self._last_flush = time.time()
        self._request('%s/api/game/battles' % config.API_BASE.rstrip('/'), answered,
                      method='POST', post_data=body)

    def _request(self, url, answered, method='GET', post_data=''):
        """Signed with whatever proves this account, and nothing if neither does.

        The same two proofs as the loadout upload: the link's secret when the
        player has one, otherwise the client's own WGNI web token, which
        unicum.gg has Wargaming confirm. A battle is a statement about thirty
        accounts and the server checks that this one is among them, which it
        can only do if it knows which account is speaking.
        """
        secret = getattr(self._link, 'secret', None)
        if secret:
            self._fetch(url, answered, {'Authorization': 'Bearer %s' % secret},
                        method, post_data)
            return

        def with_token(response):
            if not (response and response.isValid()):
                _logger.info('no web token; battles wait for the next garage')
                self._done()
                return
            self._fetch(url, answered, {
                'X-Wargaming-Token': str(response.getToken()),
                'X-Wargaming-Region': config.REGION,
            }, method, post_data)

        try:
            from constants import TOKEN_TYPE
            from gui.shared.utils.requesters import getTokenRequester
            requester = getTokenRequester(TOKEN_TYPE.WGNI)
            if requester.isInProcess():
                # Somebody else holds the singleton's one callback slot. The
                # deadline in `_free` is what makes this recoverable rather
                # than final.
                self._done()
                return
            requester.request(timeout=10.0)(with_token)
        except Exception:
            _logger.exception('could not ask for a web token')
            self._done()

    def _fetch(self, url, answered, headers, method, post_data):
        headers = dict(headers)
        headers['Content-Type'] = 'application/json'
        self._session.fetch(url, answered, headers=headers,
                            timeout=config.API_TIMEOUT, method=method,
                            post_data=post_data)


def _seconds(headers):
    """The server's own Retry-After in seconds, or None."""
    if not isinstance(headers, dict):
        return None
    for key, value in headers.items():
        if str(key).lower() == 'retry-after':
            seconds = _int(value, 0)
            return seconds if 0 < seconds <= 86400 else None
    return None


def install(session, settings, link):
    reporter = Reporter(session, settings, link)
    reporter.install()
    return reporter

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

`statsCtrl.getResults().results` is the raw dictionary the server sent, the
same structure a replay carries in its second block, which is how the
extractor below could be measured against 1424 real battles before it ever ran
in the client. What the dictionary does NOT carry is the map's name, the
gameplay and the client version: those live in a replay's meta block, not in
the results, so they are read from the client here and passed in.

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

When it sends
-------------
Queued to disk the moment the results land, sent from the garage. Queued
rather than sent on the spot because the request needs the account, because a
client that loses the network must not lose the battle, and because the player
has just finished a battle and is owed the frames.
"""
import json
import logging
import os
import re
import time

from unicum import config

_logger = logging.getLogger('unicum.battles')

# Where battles wait until the server has taken them. Beside the loadout
# store, for the same reason: a configs folder survives a mod update.
STORE = os.path.join('mods', 'configs', 'unicum', 'battles.json')

# Battles per request.
#
# Five rather than the twenty-five the endpoint accepts, and the measurement is
# why: a thirty-vehicle battle is 10.2 KB of JSON, so twenty-five of them would
# be a quarter of a megabyte in one call on a connection we know nothing about,
# and a failure would throw all of it away rather than a fifth of it. That is
# the same reasoning as the loadout upload's own batch, and the same numbers.
# Five is 51 KB for random battles, and still clears a forty-battle backlog in
# eight calls, well inside what the endpoint allows in an hour.
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

# The least time between two flushes, so a player opening old results from the
# notification centre cannot turn that into a request each.
_MIN_INTERVAL = 60.0

# How many battles the queue keeps when the server cannot be reached.
#
# A queue that grew without a bound would be a file that grows without a
# bound. Two hundred battles is more than a week of heavy play, and past that
# the oldest go: a battle nobody could send for a week is one somebody else in
# it has almost certainly sent already.
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
    return {
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


def load_queue():
    """The battles a previous session wrote down and could not send."""
    try:
        with open(STORE, 'rb') as handle:
            stored = json.loads(handle.read().decode('utf-8'))
    except (IOError, OSError, ValueError):
        return []
    if not isinstance(stored, list):
        return []
    return [row for row in stored
            if isinstance(row, dict) and row.get('arenaUniqueId')]


def save_queue(battles):
    try:
        folder = os.path.dirname(STORE)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(STORE, 'wb') as handle:
            handle.write(json.dumps(battles).encode('utf-8'))
    except (IOError, OSError):
        _logger.exception('could not write %s', STORE)


def queued(battles, battle):
    """`battles` with `battle` added, deduplicated, oldest dropped past the cap.

    Deduplicated because opening an old battle from the notification centre
    posts its results again, and that is the same battle rather than a second
    one.
    """
    out = [row for row in battles
           if row.get('arenaUniqueId') != battle['arenaUniqueId']]
    out.append(battle)
    return out[-_MAX_QUEUED:]


def settled(battles, done):
    """`battles` without the ids the server has answered for."""
    answered = set(done)
    return [row for row in battles if row.get('arenaUniqueId') not in answered]


def read_answer(body):
    """(stored, known, [(id, reason)]) out of the endpoint's answer."""
    try:
        answer = json.loads(body)
    except (TypeError, ValueError):
        return (0, 0, [])
    if not isinstance(answer, dict):
        return (0, 0, [])
    refused = []
    for row in answer.get('rejected') or []:
        if isinstance(row, dict) and row.get('arenaUniqueId'):
            refused.append((row['arenaUniqueId'], row.get('reason') or '?'))
    return (_int(answer.get('stored')), _int(answer.get('known')), refused)


class Reporter(object):

    def __init__(self, session, settings, link):
        self._session = session
        self._settings = settings
        self._link = link
        self._queue = load_queue()
        self._busy = False
        self._last_flush = 0.0

    def install(self):
        try:
            from helpers import dependency
            from skeletons.gui.battle_results import IBattleResultsService
            service = dependency.instance(IBattleResultsService)
        except Exception:
            _logger.exception('no battle results service; battles are not reported')
            return
        self._session.subscribe(service.onResultPosted, self._on_result)
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

    def _on_garage(self, *args):
        self._session.callback(_START_DELAY, self.flush)

    def _sends(self):
        try:
            return self._settings.sends_battles()
        except Exception:
            _logger.exception('could not read the battle setting')
            return False

    def _on_result(self, reusable, stats_ctrl, _window):
        """One battle's results have landed. Write it down, then send it later.

        Guarded whole: this runs on a WG Event with the client's own listeners
        after it, and a handler that raised would stop them.
        """
        try:
            if not self._sends():
                return
            results = getattr(stats_ctrl.getResults(), 'results', None)
            common = (results or {}).get('common') or {}
            battle = payload(results,
                             arena_names(_int(common.get('arenaTypeID'), -1)),
                             full_version())
            if battle is None:
                _logger.info('battle %s is not one we can describe',
                             getattr(reusable, 'arenaUniqueID', '?'))
                return
            self._queue = queued(self._queue, battle)
            save_queue(self._queue)
            _logger.info('battle %s written down, %d waiting',
                         battle['arenaUniqueId'], len(self._queue))
            self._session.callback(_SEND_DELAY, self.flush)
        except Exception:
            _logger.exception('could not write down a battle')

    def flush(self):
        """Send what is waiting, a batch at a time."""
        if self._busy or not self._queue or not self._sends():
            return
        try:
            from helpers import isPlayerAccount
            if not isPlayerAccount():
                return
        except ImportError:
            return
        now = time.time()
        if now - self._last_flush < _MIN_INTERVAL:
            return
        self._busy = True
        self._last_flush = now
        self._post()

    def _post(self):
        batch = self._queue[:_BATCH]
        if not batch:
            self._busy = False
            return
        body = json.dumps({'battles': batch})

        def answered(response):
            code = getattr(response, 'responseCode', None)
            if code != 200:
                # Kept rather than dropped: a battle a network refused is one
                # the next garage sends. A body the server will never accept is
                # the one exception, and it says so by naming it in `rejected`
                # with a 200 rather than by refusing the call.
                self._busy = False
                _logger.warning('battle upload stopped on HTTP %s, %d still waiting',
                                code, len(self._queue))
                return
            stored, known, refused = read_answer(response.body)
            # The refused are settled too. A battle the server has told us it
            # will not take is one we would otherwise offer for ever.
            self._queue = settled(self._queue,
                                  [row['arenaUniqueId'] for row in batch])
            save_queue(self._queue)
            if refused:
                _logger.warning('%d battle(s) refused: %s', len(refused),
                                ', '.join('%s %s' % pair for pair in refused))
            _logger.info('%d battle(s) stored, %d already known, %d waiting',
                         stored, known, len(self._queue))
            self._post()

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
                self._busy = False
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
                self._busy = False
                return
            requester.request(timeout=10.0)(with_token)
        except Exception:
            _logger.exception('could not ask for a web token')
            self._busy = False

    def _fetch(self, url, answered, headers, method, post_data):
        headers = dict(headers)
        headers['Content-Type'] = 'application/json'
        self._session.fetch(url, answered, headers=headers,
                            timeout=config.API_TIMEOUT, method=method,
                            post_data=post_data)


def install(session, settings, link):
    reporter = Reporter(session, settings, link)
    reporter.install()
    return reporter

"""Everything unicum.gg knows about a roster, from GET /{region}/resolve.

A roster arrives all at once: up to fifteen players in a skirmish room, a
screenful of clans in the detachment list, 3300 contacts. So ids are
collected and asked for together, and answers are cached, rather than one
request per name. Together, but not all in the same breath: the batches leave
a few at a time (_MAX_IN_FLIGHT), since a contacts list is 33 of them and no
one player's client should hand a server that in one go. One answer carries a
player's or clan's languages, flags, ratings and win rates, so every surface
of the mod reads the same entry.

The endpoint also accepts clan tags. The Stronghold detachment list is a web
page whose rows carry a tag and nothing else, and `tags=` maps each one to
its clan id while putting the clan itself in the same answer.
"""
import logging
import time
import urllib

from unicum import config
from unicum.api import store as disk
from unicum.api.http import parse
from unicum.api.batching import _chunk, _keys, _tag_key, _vehicle_key
from unicum.api.entry import (CLANS, NAMES, PLAYERS, TAGS, VEHICLES, Entry,
                              Vehicle)

_logger = logging.getLogger('unicum.api')

# Long enough to coalesce a burst of batches into one write.
_SAVE_DELAY = 10.0

# How long to wait before looking again, when the write came due in a battle.
# Short enough to land in the garage rather than at the next battle's start,
# long enough that a whole battle costs a handful of attribute lookups.
_BATTLE_RETRY = 30.0

# How long a failed request keeps its ids from being asked for again. Without
# it, a server that is down gets the whole roster again on every redraw.
_RETRY_AFTER = 60.0

# Requests of this cache in the air at once; the rest wait their turn. A
# contacts list of 3300 is 33 batches, and firing them together asks one
# server to answer 3300 players in one breath -- a burst one player's client
# has no business making. Spread out, the same work arrives at a pace a
# server can hold, and a screen fills a little at a time instead of all or
# nothing.
_MAX_IN_FLIGHT = 4


class Lookup(object):
    """Cache in front of GET /{region}/resolve."""

    def __init__(self, session, region, store=None, api_base=None):
        self._session = session
        self._region = region
        self._api_base = (api_base or config.API_BASE).rstrip('/')
        self._cache = {}          # (kind, id) -> Entry
        # (account id, tank id, mode) -> Vehicle. Apart from `_cache` on
        # purpose: these are not written to disk. A roster's ratings are
        # worth warming a session with, a battle's per-vehicle records are
        # asked for once per battle and would be stale before the next one.
        self._vehicles = {}
        self._tags = {}           # TAG -> (clan id or None, fetched_at)
        # NICKNAME (lowered) -> (account id or None, fetched_at). In memory
        # only, unlike the tags beside it, and on purpose: a clan tag is as
        # good tomorrow as today, where a player renames and the id behind a
        # name is the one thing a saved copy would get wrong. Re-asking costs
        # one request in a window that is already making one.
        self._names = {}
        self._in_flight = set()   # (kind, id or TAG)
        self._retry_at = {}       # (kind, id or TAG) -> time
        self._queued = []         # batches waiting for a turn
        self._running = 0         # requests in the air
        self._store = store if store is not None else config.RESOLVE_STORE
        self._dirty = False
        self._save_scheduled = False
        self._load()
        session.on_close(self._save)

    def get(self, kind, entity_id):
        """Cached entry, however old, or None if it was never answered.

        Never triggers a fetch: this is called from inside the VO builders,
        which are synchronous and must not grow a network dependency. An old
        answer keeps being drawn until the fresh one replaces it -- deleting
        stale entries once blanked every flag of a contacts list at once.
        """
        return self._cache.get((kind, entity_id))

    def vehicle(self, account_id, tank_id, mode=None):
        """Cached record for a pair, however old, or None if never answered.

        Never triggers a fetch, exactly like `get`: the panels that read this
        are synchronous VO builders.
        """
        return self._vehicles.get(_vehicle_key(account_id, tank_id, mode))

    def needs_vehicle(self, account_id, tank_id, mode=None):
        """Whether a pair should be asked for: never answered, or stale."""
        key = _vehicle_key(account_id, tank_id, mode)
        flight = (VEHICLES, key)
        if flight in self._in_flight or self._retry_at.get(flight, 0) > time.time():
            return False
        held = self._vehicles.get(key)
        return held is None or self._is_stale(held.fetched_at)

    def clan_id(self, tag):
        """The clan id behind a tag, or None when unknown or not asked yet."""
        found = self._tags.get(_tag_key(tag))
        return found[0] if found else None

    def knows_tag(self, tag):
        """Whether the server has answered for this tag, clan or no clan."""
        return _tag_key(tag) in self._tags

    def account_id(self, name):
        """The account id behind a nickname, or None when unknown or unasked."""
        found = self._names.get(_tag_key(name))
        return found[0] if found else None

    def knows_name(self, name):
        """Whether the server has answered for this nickname, account or no."""
        return _tag_key(name) in self._names

    def needs_fetch(self, kind, entity_id):
        """Whether an id should be asked for: never answered, or gone stale.

        False while a request for it is on the wire, and for a while after
        one failed, so a view that redraws meanwhile does not queue it again.
        """
        key = (kind, entity_id)
        if key in self._in_flight or self._retry_at.get(key, 0) > time.time():
            return False
        entry = self._cache.get(key)
        return entry is None or self._is_stale(entry.fetched_at)

    def prefetch(self, players=(), clans=(), tags=(), names=(), vehicles=(),
                 mode=None, on_ready=None):
        """Fetch whatever is missing or stale, then call on_ready once.

        on_ready fires even when nothing had to be fetched, so a caller can
        use it as its single "now redraw" signal. A tag whose clan id is
        already known is refreshed through that id rather than the tag.

        `vehicles` is (account id, vehicle id) pairs and `mode` the mode to
        describe them over, which ride in the same request as the roster:
        the whole point of this endpoint is that a battle costs one.

        `names` is nicknames, for the one roster that prints no id at all:
        the Stronghold detachment preview. It behaves as `tags` does, a name
        already resolved being refreshed through its account id rather than
        asked for by name a second time.
        """
        clans = list(clans)
        players = list(players)
        wanted_tags = []
        for tag in tags:
            key = _tag_key(tag)
            known = self._tags.get(key)
            if known is not None and not self._is_stale(known[1]):
                if known[0]:
                    clans.append(known[0])
                continue
            if (TAGS, key) not in self._in_flight and \
                    self._retry_at.get((TAGS, key), 0) <= time.time() and \
                    key not in wanted_tags:
                wanted_tags.append(key)
        wanted_names = []
        for name in names:
            key = _tag_key(name)
            known = self._names.get(key)
            if known is not None and not self._is_stale(known[1]):
                if known[0]:
                    players.append(known[0])
                continue
            if (NAMES, key) not in self._in_flight and \
                    self._retry_at.get((NAMES, key), 0) <= time.time() and \
                    key not in wanted_names:
                wanted_names.append(key)

        batches = _chunk(self._missing(PLAYERS, players),
                         self._missing(CLANS, clans), wanted_tags, wanted_names,
                         self._missing_vehicles(vehicles, mode), mode)
        if not batches:
            if on_ready is not None:
                on_ready()
            return

        # on_ready means "everything asked for has been answered", so it
        # waits for the last batch rather than firing per request.
        outstanding = [len(batches)]
        for batch in batches:
            self._dispatch(batch, outstanding, on_ready)

    def _missing(self, kind, ids):
        out = []
        for entity_id in ids:
            if not entity_id:
                continue
            entity_id = int(entity_id)
            if self.needs_fetch(kind, entity_id) and entity_id not in out:
                out.append(entity_id)
        return out

    def _missing_vehicles(self, pairs, mode):
        out = []
        for pair in pairs:
            try:
                account_id, tank_id = int(pair[0]), int(pair[1])
            except (TypeError, ValueError, IndexError):
                continue
            if not account_id or not tank_id:
                continue
            key = _vehicle_key(account_id, tank_id, mode)
            if self.needs_vehicle(account_id, tank_id, mode) and key not in out:
                out.append(key)
        return out

    def _dispatch(self, batch, outstanding, on_ready):
        """Queue a batch, and send what the limit allows."""
        # Marked in flight on the way into the queue, not on the way out: a
        # redraw while a batch waits must not ask for the same ids again.
        self._in_flight.update(_keys(batch))
        self._queued.append((batch, outstanding, on_ready))
        self._pump()

    def _pump(self):
        while self._session.alive and self._running < _MAX_IN_FLIGHT and self._queued:
            self._running += 1
            self._send(*self._queued.pop(0))

    def _send(self, batch, outstanding, on_ready):
        keys = _keys(batch)

        def done(payload):
            try:
                if payload is None:
                    retry = time.time() + _RETRY_AFTER
                    for key in keys:
                        self._retry_at[key] = retry
                else:
                    self._absorb(batch, payload)
            finally:
                self._in_flight.difference_update(keys)
                self._running -= 1
                outstanding[0] -= 1
                if outstanding[0] <= 0 and on_ready is not None:
                    on_ready()
                # After the counters, so a caller's on_ready runs before the
                # next request rather than behind it.
                self._pump()

        self._session.fetch(self._url(batch), lambda response: done(parse(response, 'resolve')),
                            timeout=config.RESOLVE_TIMEOUT)

    def _url(self, batch):
        parts = []
        for kind in (PLAYERS, CLANS, TAGS, NAMES):
            if batch[kind]:
                parts.append('%s=%s' % (kind, ','.join(
                    urllib.quote(str(value), safe='') for value in batch[kind])))
        if batch[VEHICLES]:
            parts.append('%s=%s' % (VEHICLES, ','.join(
                '%d:%d' % (key[0], key[1]) for key in batch[VEHICLES])))
            # Only with the pairs it describes. Sent alone it would be a mode
            # the server has to validate for nothing, and refused if the
            # client is in a battle whose mode it does not publish.
            if batch['mode']:
                parts.append('mode=%s' % urllib.quote(str(batch['mode']), safe=''))
        return '%s/api/%s/resolve?%s' % (self._api_base, self._region, '&'.join(parts))

    def _absorb(self, batch, payload):
        now = time.time()
        for kind in (PLAYERS, CLANS):
            answered = payload.get(kind) or {}
            for entity_id in batch[kind]:
                raw = answered.get(str(entity_id))
                self._cache[(kind, entity_id)] = (
                    Entry.from_api(kind, raw, now) if isinstance(raw, dict)
                    else Entry(fetched_at=now))
                self._retry_at.pop((kind, entity_id), None)
        # Clans reached through a tag come back under `clans` too, keyed by
        # an id the batch did not name.
        answered_tags = dict((_tag_key(t), i) for t, i in (payload.get(TAGS) or {}).items())
        for key in batch[TAGS]:
            clan_id = answered_tags.get(key)
            self._tags[key] = (int(clan_id) if clan_id else None, now)
            self._retry_at.pop((TAGS, key), None)
            raw = (payload.get(CLANS) or {}).get(str(clan_id)) if clan_id else None
            if isinstance(raw, dict):
                self._cache[(CLANS, int(clan_id))] = Entry.from_api(CLANS, raw, now)
        # Players reached through a nickname come back under `players`,
        # keyed by an id the batch did not name, exactly as a tag's clan does.
        answered_names = dict((_tag_key(n), i)
                              for n, i in (payload.get(NAMES) or {}).items())
        for key in batch[NAMES]:
            account_id = answered_names.get(key)
            self._names[key] = (int(account_id) if account_id else None, now)
            self._retry_at.pop((NAMES, key), None)
            raw = (payload.get(PLAYERS) or {}).get(str(account_id)) if account_id else None
            if isinstance(raw, dict):
                self._cache[(PLAYERS, int(account_id))] = Entry.from_api(PLAYERS, raw, now)
        self._absorb_vehicles(batch, payload)
        self._dirty = True
        self._schedule_save()

    def _absorb_vehicles(self, batch, payload):
        """The pairs answered, and the ones that were not.

        A list keyed by the pair rather than a map keyed by the account, which
        is what the endpoint sends and why: one account can be asked about on
        two vehicles, and a map would answer for one of them.
        """
        if not batch[VEHICLES]:
            return
        now = time.time()
        answered = {}
        for raw in payload.get(VEHICLES) or ():
            if not isinstance(raw, dict):
                continue
            try:
                pair = (int(raw.get('accountId')), int(raw.get('tankId')))
            except (TypeError, ValueError):
                continue
            answered[pair] = raw
        for key in batch[VEHICLES]:
            raw = answered.get((key[0], key[1]))
            self._vehicles[key] = (Vehicle.from_api(raw, now) if raw is not None
                                   else Vehicle(fetched_at=now))
            self._retry_at.pop((VEHICLES, key), None)

    @staticmethod
    def _is_stale(fetched_at):
        return time.time() - fetched_at > config.REFRESH_SECONDS

    def _load(self):
        """Warm the cache from the last session; see store.py."""
        self._cache, self._tags = disk.load(self._store, self._region)

    def _schedule_save(self, delay=_SAVE_DELAY):
        """Write soon, not now, not once per answer, and never in a battle.

        Closing the session also saves, but only on a clean shutdown: a crash
        would otherwise throw away everything learned since the game started.

        Not in a battle, because the write is synchronous and a battle is
        where a stall is felt: a roster resolves thirty players at its start,
        which is exactly what makes the write come due ten seconds later. So
        a write that falls in one waits for the garage. What a crash in the
        meantime loses is a cold first paint, not data -- every entry is
        refetchable, and the next session asks for whatever is missing.
        """
        if self._save_scheduled or not self._dirty:
            return
        self._save_scheduled = True

        def flush():
            self._save_scheduled = False
            if _in_battle():
                self._schedule_save(_BATTLE_RETRY)
                return
            self._save()

        self._session.callback(delay, flush)

    def _save(self):
        if self._dirty and self._store and disk.save(
                self._store, self._region, self._cache, self._tags):
            self._dirty = False


def _in_battle():
    """Whether a battle is on, so a write can wait for the garage.

    `isPlayerAvatar` is the client's own test, and it is one attribute
    lookup: the player entity grows an `arena` when the avatar is created
    and has none in the garage.

    Guarded, because this runs from a scheduled callback. An exception here
    would not just skip one write, it would cancel the only thing that ever
    reschedules one -- so when the question cannot be answered the answer is
    "no", and the cache gets written rather than postponed forever.
    """
    try:
        from helpers import isPlayerAvatar
        return isPlayerAvatar()
    except Exception:
        _logger.debug('could not tell whether a battle is on', exc_info=True)
        return False

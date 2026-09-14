"""Everything unicum.gg knows about a roster, from GET /{region}/resolve.

A roster arrives all at once: up to fifteen players in a skirmish room, a
screenful of clans in the detachment list, 3300 contacts. So ids are
collected and asked for together, and answers are cached, rather than one
request per name. One answer carries a player's or clan's languages, flags,
ratings and win rates, so every surface of the mod reads the same entry.

The endpoint also accepts clan tags. The Stronghold detachment list is a web
page whose rows carry a tag and nothing else, and `tags=` maps each one to
its clan id while putting the clan itself in the same answer.

Until the endpoint is deployed everywhere, a server that answers 404 is
talked to the old way: see legacy.py. Languages keep working; ratings are
simply absent.
"""
import logging
import time
import urllib

from unicum import config
from unicum.api import legacy
from unicum.api import store as disk
from unicum.api.entry import CLANS, PLAYERS, TAGS, Entry

_logger = logging.getLogger('unicum.api')

# Ids per kind per request, the endpoint's own cap. A longer list is refused,
# not truncated, and the contacts list alone is ~3300 ids.
_CHUNK = 100

# Long enough to coalesce a burst of batches into one write.
_SAVE_DELAY = 10.0

# How long a failed request keeps its ids from being asked for again. Without
# it, a server that is down gets the whole roster again on every redraw.
_RETRY_AFTER = 60.0


class Lookup(object):
    """Cache in front of GET /{region}/resolve."""

    def __init__(self, session, region, store=None, api_base=None):
        self._session = session
        self._region = region
        self._api_base = (api_base or config.API_BASE).rstrip('/')
        self._cache = {}          # (kind, id) -> Entry
        self._tags = {}           # TAG -> (clan id or None, fetched_at)
        self._in_flight = set()   # (kind, id or TAG)
        self._retry_at = {}       # (kind, id or TAG) -> time
        self._legacy = False
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

    def clan_id(self, tag):
        """The clan id behind a tag, or None when unknown or not asked yet."""
        found = self._tags.get(_tag_key(tag))
        return found[0] if found else None

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

    def prefetch(self, players=(), clans=(), tags=(), on_ready=None):
        """Fetch whatever is missing or stale, then call on_ready once.

        on_ready fires even when nothing had to be fetched, so a caller can
        use it as its single "now redraw" signal. A tag whose clan id is
        already known is refreshed through that id rather than the tag.
        """
        clans = list(clans)
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

        batches = _chunk(self._missing(PLAYERS, players),
                         self._missing(CLANS, clans), wanted_tags)
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

    def _dispatch(self, batch, outstanding, on_ready):
        keys = _keys(batch)
        self._in_flight.update(keys)

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
                outstanding[0] -= 1
                if outstanding[0] <= 0 and on_ready is not None:
                    on_ready()

        if self._legacy:
            legacy.fetch(self._session, self._api_base, self._region, batch, done)
            return

        def received(response):
            code = getattr(response, 'responseCode', None)
            if code == 404 and not self._legacy:
                # This server predates /resolve. Every later batch goes the
                # old way too; this one is sent again, not dropped.
                _logger.warning('%s has no /resolve, falling back to languages only',
                                self._api_base)
                self._legacy = True
            if self._legacy:
                legacy.fetch(self._session, self._api_base, self._region, batch, done)
                return
            done(legacy.parse(response, 'resolve'))

        self._session.fetch(self._url(batch), received, timeout=config.API_TIMEOUT)

    def _url(self, batch):
        parts = []
        for kind in (PLAYERS, CLANS, TAGS):
            if batch[kind]:
                parts.append('%s=%s' % (kind, ','.join(
                    urllib.quote(str(value), safe='') for value in batch[kind])))
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
        self._dirty = True
        self._schedule_save()

    @staticmethod
    def _is_stale(fetched_at):
        return time.time() - fetched_at > config.REFRESH_SECONDS

    def _load(self):
        """Warm the cache from the last session; see store.py."""
        self._cache, self._tags = disk.load(self._store, self._region)

    def _schedule_save(self):
        """Write soon, not now, and not once per answer.

        Closing the session also saves, but only on a clean shutdown: a crash
        would otherwise throw away everything learned since the game started.
        """
        if self._save_scheduled or not self._dirty:
            return
        self._save_scheduled = True

        def flush():
            self._save_scheduled = False
            self._save()

        self._session.callback(_SAVE_DELAY, flush)

    def _save(self):
        if self._dirty and self._store and disk.save(
                self._store, self._region, self._cache, self._tags):
            self._dirty = False


def _tag_key(tag):
    return str(tag).strip().upper()


def _keys(batch):
    return set((kind, value) for kind in (PLAYERS, CLANS, TAGS) for value in batch[kind])


def _chunk(players, clans, tags):
    """Requests of at most _CHUNK values per kind, kinds sharing a request."""
    batches = []
    offset = 0
    while offset < max(len(players), len(clans), len(tags)):
        batches.append({PLAYERS: players[offset:offset + _CHUNK],
                        CLANS: clans[offset:offset + _CHUNK],
                        TAGS: tags[offset:offset + _CHUNK]})
        offset += _CHUNK
    return batches

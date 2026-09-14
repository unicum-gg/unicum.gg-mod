"""Language lookup against unicum.gg's resolve endpoint.

A roster arrives all at once: up to fifteen players in a skirmish room, a
screenful of clans in the detachment list. So ids are collected and asked
for together, and answers are cached, rather than one request per name.

The endpoint answers with the country codes already resolved, so nothing in
this mod has to know that `en` means the UK flag on EU and the US one
elsewhere. That mapping stays on the server, where it can change without a
mod release.
"""
import json
import logging
import os
import time

from unicum import config

_logger = logging.getLogger('unicum.api')

PLAYERS = 'players'
CLANS = 'clans'

# Ids per request. A battle roster is fifteen, but the lobby asks about every
# contact it knows -- 3293 on a real account -- and that many ids makes a
# ~40 KB query string that comes back empty. Chunking keeps each URL small
# enough to survive any proxy between here and the API.
_CHUNK = 100

# Long enough to coalesce a burst of batches into one write.
_SAVE_DELAY = 10.0


def _chunk(players, clans):
    """Split two id lists into requests of at most _CHUNK ids each.

    Players and clans travel together while there is room, so the common
    case -- a roster and its handful of clans -- stays one request.
    """
    batches = []
    remaining_players, remaining_clans = list(players), list(clans)
    while remaining_players or remaining_clans:
        take_clans = remaining_clans[:_CHUNK]
        remaining_clans = remaining_clans[_CHUNK:]
        take_players = remaining_players[:_CHUNK - len(take_clans)]
        remaining_players = remaining_players[_CHUNK - len(take_clans):]
        batches.append({PLAYERS: take_players, CLANS: take_clans})
    return batches


class Entry(object):
    """One resolved entity. `source` says how the answer was arrived at."""

    __slots__ = ('languages', 'countries', 'source', 'fetched_at')

    def __init__(self, languages, countries, source, fetched_at):
        self.languages = languages
        self.countries = countries
        self.source = source
        self.fetched_at = fetched_at

    @property
    def primary(self):
        """Country code to show when there is only room for one flag."""
        return self.countries[0] if self.countries else None

    @property
    def flags(self):
        """Country codes to draw, in the API's order, each once, at most a few.

        Two languages can share a flag (en and en-us could both come back as
        GB-UKM on EU), and a name field has room for a handful at most.
        """
        out = []
        for code in self.countries:
            if code and code not in out:
                out.append(code)
            if len(out) >= config.MAX_FLAGS:
                break
        return out


class LanguageLookup(object):
    """Cache in front of GET /{region}/languages/resolve."""

    def __init__(self, session, region, store=None):
        self._session = session
        self._region = region
        # (kind, id) -> Entry. A miss the server could not resolve is cached
        # as an empty Entry too, otherwise every roster redraw would ask
        # again for the same unknown accounts.
        self._cache = {}
        self._in_flight = set()
        self._store = store if store is not None else config.LANGUAGE_STORE
        self._dirty = False
        self._save_scheduled = False
        self._load()
        session.on_close(self._save)

    def _load(self):
        """Warm the cache from the last session.

        Without this the first draw of anything is unmarked: these lookups
        are answered over the network but consumed synchronously, so a cold
        cache means one blank pass every time the game starts. Languages are
        inferred from clan history and refreshed hourly upstream, so day-old
        answers are fine to paint with while the live ones arrive.
        """
        if not self._store or not os.path.isfile(self._store):
            return
        try:
            with open(self._store, 'rb') as handle:
                stored = json.load(handle)
        except (IOError, ValueError):
            _logger.warning('could not read %s, starting cold', self._store)
            return
        if stored.get('region') != self._region:
            return
        now = time.time()
        for kind in (PLAYERS, CLANS):
            for key, raw in (stored.get(kind) or {}).items():
                try:
                    entity_id = int(key)
                except ValueError:
                    continue
                self._cache[(kind, entity_id)] = Entry(
                    raw.get('languages') or [], raw.get('countries') or [],
                    raw.get('source'), now)
        _logger.info('warmed %s entries from %s', len(self._cache), self._store)

    def _schedule_save(self):
        """Write soon, not now, and not once per answer.

        Closing the session also saves, but that only runs on a clean
        shutdown. A crash mid-session would otherwise throw away everything
        learned since the game started.
        """
        if self._save_scheduled or not self._dirty:
            return
        self._save_scheduled = True

        def flush():
            self._save_scheduled = False
            self._save()

        self._session.callback(_SAVE_DELAY, flush)

    def _save(self):
        if not self._dirty or not self._store:
            return
        payload = {'region': self._region, PLAYERS: {}, CLANS: {}}
        for (kind, entity_id), entry in self._cache.items():
            # Unresolved entries are deliberately not persisted: the answer
            # may simply not exist yet upstream, and writing it down would
            # keep it missing for a day.
            if entry.countries:
                payload[kind][str(entity_id)] = {
                    'languages': entry.languages,
                    'countries': entry.countries,
                    'source': entry.source,
                }
        try:
            directory = os.path.dirname(self._store)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            with open(self._store, 'wb') as handle:
                json.dump(payload, handle)
            self._dirty = False
        except (IOError, OSError):
            _logger.exception('could not write %s', self._store)

    def get(self, kind, entity_id):
        """Cached entry, however old, or None if it was never answered.

        Deliberately never triggers a fetch: this is called from inside the
        VO builders, which are synchronous and must not grow a network
        dependency. Callers ask needs_fetch() for that.

        Stale entries used to be deleted here, which turned "old" into
        "unknown": open the contacts list more than a few minutes after the
        last lookup and every flag vanished at once while 3000 ids went back
        on the wire. A player's language does not change in minutes, so an
        old answer keeps being drawn until the new one replaces it.
        """
        return self._cache.get((kind, entity_id))

    def needs_fetch(self, kind, entity_id):
        """Whether an id should be asked for: never answered, or gone stale.

        False while a request for it is already on the wire, so a view that
        redraws during a lookup does not queue the same id twice.
        """
        key = (kind, entity_id)
        if key in self._in_flight:
            return False
        entry = self._cache.get(key)
        return entry is None or self._is_stale(entry)

    @staticmethod
    def _is_stale(entry):
        return time.time() - entry.fetched_at > config.REFRESH_SECONDS

    def prefetch(self, players=(), clans=(), on_ready=None):
        """Fetch whatever is missing, then call on_ready once.

        on_ready fires even when nothing had to be fetched, so a caller can
        use it as its single "now redraw" signal.
        """
        missing_players = self._missing(PLAYERS, players)
        missing_clans = self._missing(CLANS, clans)
        batches = _chunk(missing_players, missing_clans)
        if not batches:
            if on_ready is not None:
                on_ready()
            return

        # on_ready means "everything asked for has been answered", so it
        # waits for the last batch rather than firing per request.
        outstanding = [len(batches)]

        for wanted in batches:
            self._dispatch(wanted, outstanding, on_ready)

    def _dispatch(self, wanted, outstanding, on_ready):
        for kind, ids in wanted.items():
            self._in_flight.update((kind, i) for i in ids)

        def received(response):
            try:
                self._absorb(wanted, response)
            finally:
                for kind, ids in wanted.items():
                    self._in_flight.difference_update((kind, i) for i in ids)
                outstanding[0] -= 1
                if outstanding[0] <= 0 and on_ready is not None:
                    on_ready()

        self._session.fetch(self._url(wanted), received,
                            timeout=config.API_TIMEOUT)

    def _missing(self, kind, ids):
        out = []
        for entity_id in ids:
            if not entity_id:
                continue
            entity_id = int(entity_id)
            if not self.needs_fetch(kind, entity_id):
                continue
            if entity_id not in out:
                out.append(entity_id)
        return out

    def _url(self, wanted):
        parts = []
        for kind in (PLAYERS, CLANS):
            if wanted[kind]:
                parts.append('%s=%s' % (
                    kind, ','.join(str(i) for i in wanted[kind])))
        return '%s/api/%s/languages/resolve?%s' % (
            config.API_BASE, self._region, '&'.join(parts))

    def _absorb(self, wanted, response):
        try:
            self._absorb_payload(wanted, response)
        finally:
            self._schedule_save()

    def _absorb_payload(self, wanted, response):
        payload = self._parse(response)
        now = time.time()
        for kind in (PLAYERS, CLANS):
            resolved = payload.get(kind) or {}
            for entity_id in wanted[kind]:
                raw = resolved.get(str(entity_id))
                if raw is None:
                    # Absent means the server could not resolve it, which is
                    # an answer. Cached as empty so it is not asked again on
                    # the next redraw.
                    self._cache[(kind, entity_id)] = Entry([], [], None, now)
                    continue
                self._cache[(kind, entity_id)] = Entry(
                    raw.get('languages') or [],
                    raw.get('countries') or [],
                    raw.get('source'),
                    now)
                self._dirty = True

    def _parse(self, response):
        code = getattr(response, 'responseCode', None)
        if code != 200:
            _logger.warning('resolve failed with HTTP %s', code)
            return {}
        try:
            return json.loads(response.body)
        except (TypeError, ValueError):
            _logger.warning('resolve returned a body that is not JSON')
            return {}

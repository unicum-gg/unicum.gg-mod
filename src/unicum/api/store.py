"""The lookup's answers on disk, between sessions.

Its job is the first paint: answers come over the network but are consumed
synchronously, so without it every game start draws one unmarked contacts
list before they arrive. Entries keep the time they were fetched, so old ones
are drawn at once and refreshed in the background rather than trusted for
another half hour.
"""
import json
import logging
import os

from unicum.api.entry import CLANS, PLAYERS, TAGS, Entry

_logger = logging.getLogger('unicum.api')

_VERSION = 2


def load(path, region):
    """({(kind, id): Entry}, {TAG: (clan id, fetched_at)}), empty if unusable."""
    cache, tags = {}, {}
    if not path or not os.path.isfile(path):
        return cache, tags
    try:
        with open(path, 'rb') as handle:
            stored = json.load(handle)
    except (IOError, ValueError):
        _logger.warning('could not read %s, starting cold', path)
        return cache, tags
    if stored.get('version') != _VERSION or stored.get('region') != region:
        return cache, tags
    for kind in (PLAYERS, CLANS):
        for key, raw in (stored.get(kind) or {}).items():
            try:
                cache[(kind, int(key))] = Entry.from_store(raw)
            except (TypeError, ValueError, AttributeError):
                continue
    for tag, raw in (stored.get(TAGS) or {}).items():
        try:
            tags[tag] = (int(raw['id']), float(raw['fetchedAt']))
        except (TypeError, ValueError, KeyError):
            continue
    _logger.info('warmed %s entries and %s tags from %s', len(cache), len(tags), path)
    return cache, tags


def save(path, region, cache, tags):
    """Write the known answers; True once they are on disk."""
    payload = {'version': _VERSION, 'region': region, PLAYERS: {}, CLANS: {}, TAGS: {}}
    for (kind, entity_id), entry in cache.items():
        # "Unknown" is not written down: the server may simply not hold the
        # account yet, and a stored miss would hide it for a day.
        if entry.known:
            payload[kind][str(entity_id)] = entry.to_store()
    for tag, (clan_id, fetched_at) in tags.items():
        if clan_id:
            payload[TAGS][tag] = {'id': clan_id, 'fetchedAt': fetched_at}
    try:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(path, 'wb') as handle:
            json.dump(payload, handle)
        return True
    except (IOError, OSError):
        _logger.exception('could not write %s', path)
        return False

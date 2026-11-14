"""How a roster is cut into requests, and how a key is made.

The pure half of `resolve.py`: no state, no session, no disk. Given the ids a
caller wants, which requests to send; given a tag or a pair, the key the cache
holds it under. Split out when the module it came from went past the size this
repo holds its modules to, and this was the half that answers without asking
anything.
"""
from __future__ import absolute_import

from unicum.api.entry import CLANS, NAMES, PLAYERS, TAGS, VEHICLES

# Ids per kind per request, the endpoint's own cap. A longer list is refused,
# not truncated, and the contacts list alone is ~3300 ids.
_CHUNK = 100

# Vehicle pairs per request, which is the endpoint's own lower cap for them:
# a pair costs two indexed reads where an id costs part of one, and the
# roster this exists for is thirty.
_VEHICLE_CHUNK = 60


def _tag_key(tag):
    return str(tag).strip().upper()


def _vehicle_key(account_id, tank_id, mode):
    """What a pair is cached under: the pair AND the mode.

    The mode belongs in the key because it decides the figures: the same
    vehicle in a Random battle and in an Advance are two different records,
    and one overwriting the other is how a reader gets shown the wrong one.
    """
    return (int(account_id), int(tank_id), str(mode or ''))


def _keys(batch):
    keys = set((kind, value) for kind in (PLAYERS, CLANS, TAGS, NAMES)
               for value in batch[kind])
    keys.update((VEHICLES, key) for key in batch[VEHICLES])
    return keys


def _chunk(players, clans, tags, names=(), vehicles=(), mode=None):
    """Requests of at most _CHUNK values per kind, kinds sharing a request.

    The vehicle pairs have their own, lower ceiling, so a request carries at
    most sixty of them beside its hundred ids.
    """
    vehicles = list(vehicles)
    batches = []
    offset = 0
    pairs = 0
    names = list(names)
    while (offset < max(len(players), len(clans), len(tags), len(names))
           or pairs < len(vehicles)):
        batches.append({PLAYERS: players[offset:offset + _CHUNK],
                        CLANS: clans[offset:offset + _CHUNK],
                        TAGS: tags[offset:offset + _CHUNK],
                        NAMES: names[offset:offset + _CHUNK],
                        VEHICLES: vehicles[pairs:pairs + _VEHICLE_CHUNK],
                        'mode': mode})
        offset += _CHUNK
        pairs += _VEHICLE_CHUNK
    return batches

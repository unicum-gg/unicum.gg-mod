"""The facts about a battle that its own results do not carry.

The map, the client's version and the cluster it ran on are things the client
knows and the server's results never mention, so each is read from wherever
the client keeps it. Kept apart from `extract` because none of it is about a
battle: it is about the client reporting one.
"""
from __future__ import absolute_import

import logging
import re

_logger = logging.getLogger('unicum.battles.naming')

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

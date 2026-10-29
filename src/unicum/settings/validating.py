"""Turning whatever is on disk into settings this mod can trust.

`validate` is the only way in. It takes anything -- a file written by an older
build, a hand-edited dict, a value of the wrong type -- and answers a complete
set of settings, because every reader in the mod assumes every key is present
and of the right shape. A bad value keeps the default rather than raising: a
player who typed a word where a number goes should lose that one setting, not
the mod.
"""
from __future__ import absolute_import

import logging

from unicum.settings.defaults import (_RATED_BY_DEFAULT, _TWITCH_CHANNEL,
                                      AVERAGED, BATTLE_CHAT_CHOICES, DEFAULTS,
                                      EXTRAS, MAX_FLAGS, MAX_PANEL, METRICS,
                                      MIN_PANEL, MINIMAP_NAME_CHOICES, MODES,
                                      RELOAD_CHOICES, SURFACES, WINDOWS)

_logger = logging.getLogger('unicum.settings.validating')

def _reload_choice(raw):
    """The announcing choice; True and False are what it was before it was one."""
    if raw is True:
        return 'all'
    if raw is False or raw is None:
        return 'off'
    return raw if raw in RELOAD_CHOICES else DEFAULTS['autoReload']

def _minimap_names(raw):
    """The minimap label choice, falling back to the client's own."""
    return raw if raw in MINIMAP_NAME_CHOICES else DEFAULTS['minimapNames']

def _battle_chat(twitch):
    """Where the Twitch chat shows in battle.

    True and False are what this was before it was a choice: a checkbox for
    the battle chat, which is why True reads as 'chat' rather than as the
    window that was not on offer then.
    """
    raw = twitch.get('battle')
    if raw in BATTLE_CHAT_CHOICES:
        return raw
    legacy = twitch.get('battleChat')
    if isinstance(legacy, bool):
        return 'chat' if legacy else 'off'
    return DEFAULTS['twitch']['battle']

def validate(raw):
    """A complete, valid settings dict: defaults for anything missing or wrong."""
    if not isinstance(raw, dict):
        raw = {}
    raw = _migrate(raw)
    values = {
        'enabled': _bool(raw.get('enabled'), DEFAULTS['enabled']),
        'metric': raw.get('metric') if raw.get('metric') in METRICS else DEFAULTS['metric'],
        'window': raw.get('window') if raw.get('window') in WINDOWS else DEFAULTS['window'],
        'battles': raw.get('battles') if raw.get('battles') in EXTRAS else DEFAULTS['battles'],
        'winrate': raw.get('winrate') if raw.get('winrate') in EXTRAS else DEFAULTS['winrate'],
        'winrateDecimal': _bool(raw.get('winrateDecimal'), DEFAULTS['winrateDecimal']),
        'maxFlags': DEFAULTS['maxFlags'],
        'tankButton': _bool(raw.get('tankButton'), DEFAULTS['tankButton']),
        'autoReload': _reload_choice(raw.get('autoReload')),
        'minimapNames': _minimap_names(raw.get('minimapNames')),
    }
    alt_only = raw.get('altOnly') if isinstance(raw.get('altOnly'), dict) else {}
    values['altOnly'] = dict((key, _bool(alt_only.get(key), default))
                             for key, default in DEFAULTS['altOnly'].items())
    context_menu = raw.get('contextMenu') if isinstance(raw.get('contextMenu'), dict) else {}
    values['contextMenu'] = dict((key, _bool(context_menu.get(key), default))
                                 for key, default in DEFAULTS['contextMenu'].items())
    values['sendLoadouts'] = _bool(raw.get('sendLoadouts'), DEFAULTS['sendLoadouts'])
    values['sendBattles'] = _bool(raw.get('sendBattles'), DEFAULTS['sendBattles'])
    values['sendReplays'] = _bool(raw.get('sendReplays'), DEFAULTS['sendReplays'])
    values['measurePerformance'] = _bool(raw.get('measurePerformance'),
                                         DEFAULTS['measurePerformance'])
    twitch = raw.get('twitch') if isinstance(raw.get('twitch'), dict) else {}
    values['twitch'] = {'channel': twitch_channel(twitch.get('channel')),
                        'battle': _battle_chat(twitch),
                        'garage': _bool(twitch.get('garage'), DEFAULTS['twitch']['garage']),
                        'garageCollapsed': _bool(twitch.get('garageCollapsed'),
                                                 DEFAULTS['twitch']['garageCollapsed']),
                        'garagePosition': _position(twitch.get('garagePosition')),
                        'garageSize': panel_size(twitch.get('garageSize')),
                        'battlePosition': _position(twitch.get('battlePosition'))}
    modes = raw.get('modes') if isinstance(raw.get('modes'), dict) else {}
    values['modes'] = {}
    for mode in MODES:
        given = modes.get(mode) if isinstance(modes.get(mode), dict) else {}
        values['modes'][mode] = dict((team, _bool(given.get(team), default))
                                     for team, default in DEFAULTS['modes'][mode].items())
    max_flags = raw.get('maxFlags')
    if isinstance(max_flags, int) and not isinstance(max_flags, bool):
        values['maxFlags'] = min(max(max_flags, 1), MAX_FLAGS)
    for surface in SURFACES:
        given = raw.get(surface) if isinstance(raw.get(surface), dict) else {}
        values[surface] = dict((key, _bool(given.get(key), default))
                               for key, default in DEFAULTS[surface].items())
    return values

def _migrate(raw):
    """Read settings.json as earlier versions wrote it.

    First one switch per surface with global flags and ratings switches, then
    a rating per surface ("none", "wn8", ...). The one rating kept is the
    first a surface showed.
    """
    migrated = dict(raw)
    if any(isinstance(raw.get(s), bool) for s in SURFACES):
        for surface in SURFACES:
            shown = raw.get(surface) is not False
            rated = shown and raw.get('ratings') is not False and surface in _RATED_BY_DEFAULT
            migrated[surface] = {'flags': shown and raw.get('flags') is not False, 'rating': rated,
                                 'average': rated and raw.get('averages') is not False}
    chosen = [raw[s].get('rating') for s in SURFACES
              if isinstance(raw.get(s), dict) and raw[s].get('rating') in METRICS + ('none',)]
    if chosen:
        rated = [rating for rating in chosen if rating != 'none']
        if 'metric' not in raw and rated:
            migrated['metric'] = rated[0]
        for surface in SURFACES:
            section = dict(migrated[surface]) if isinstance(migrated.get(surface), dict) else {}
            if isinstance(section.get('rating'), basestring):
                section['rating'] = section['rating'] != 'none'
                migrated[surface] = section
    return migrated

def twitch_channel(value):
    """A Twitch channel name as typed, "#Name" or a channel URL, as its login; else ''."""
    if not isinstance(value, basestring):
        return ''
    login = value.strip().rstrip('/').split('/')[-1].lstrip('#').lower()
    return login if _TWITCH_CHANNEL.match(login) else ''

def _merge(target, changes):
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value

def _position(value):
    """[left, top] in rem where the player dragged the garage panel, or None for its own place."""
    if (isinstance(value, list) and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        return [max(0, min(10000, int(v))) for v in value]
    return None

def panel_size(value):
    """[width, height] in rem the player resized the garage panel to, or None for its own."""
    if (isinstance(value, list) and len(value) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        return [max(low, min(high, int(v)))
                for v, low, high in zip(value, MIN_PANEL, MAX_PANEL)]
    return None

def _bool(value, default):
    return value if isinstance(value, bool) else default

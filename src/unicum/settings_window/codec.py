"""Settings to window values and back, with nothing in between.

Text and dicts in, values out. The round trip is what the checks hold this
to: anything the page can show has to read back to the setting it came from,
because a value that does not survive the trip is a setting that silently
resets itself the next time the window opens.
"""
from __future__ import absolute_import

import logging

from unicum.settings import (AVERAGED, BATTLE_CHAT_CHOICES, EXTRAS,
                             METRICS, MINIMAP_NAME_CHOICES, MODES,
                             RELOAD_CHOICES, SURFACES,
                             TEXT_SIZE_CHOICES, WINDOWS)
from unicum.settings_window.labels import (_ALT_KEYS, _ALT_SCREENS,
                                           _MENU_KEYS, _SURFACE_LABELS,
                                           CARD_VAR, HIDE_BATTLES_VAR,
                                           HIDE_VAR,
                                           MINIMAP_NAME_LABELS,
                                           RELOAD_LABELS, SHOW_CHOICES,
                                           TEAM_CHOICES, WHEN_CHOICES)
from unicum.settings import FIGURE_CHOICES, FIGURED

_logger = logging.getLogger('unicum.settings_window.codec')

def read_native(text):
    """What the settings tab sends back ("var\tkind\tvalue" a line), as the window's raw values.

    Kinds: d a dropdown's index (offset added), c a checkbox, b a button.
    Returns (raw values, buttons clicked).
    """
    raw, buttons = {}, []
    for line in (text or u'').split(u'\n'):
        parts = line.split(u'\t')
        if len(parts) != 3:
            continue
        var, kind, value = parts
        if kind == u'd':
            try:
                raw[str(var)] = int(value)
            except ValueError:
                continue
        elif kind == u'c':
            raw[str(var)] = value == u'1'
        elif kind == u'b':
            buttons.append(str(var))
    return raw, buttons

def read_peek(text):
    """The tab's peeked values: a choice made but not yet applied.

    Sent on every change, so the preview can show what the choice would
    look like before it is saved. An empty dict means nothing is pending,
    which is also what the tab sends when Apply, OK or Cancel settles it.

    Its lines carry a field more than a change does ("peek\tvar\tkind\t
    value"), which is what keeps `read_native` from reading them as changes
    and saving them: that one counts fields and skips anything that is not
    three.
    """
    peek = {}
    for line in (text or u'').split(u'\n'):
        parts = line.split(u'\t')
        if len(parts) != 4 or parts[0] != u'peek':
            continue
        _, var, kind, value = parts
        if not var:
            # The settling line: everything pending is gone.
            return {}
        if kind == u'd':
            try:
                peek[str(var)] = int(value)
            except ValueError:
                continue
        elif kind == u'c':
            peek[str(var)] = value == u'1'
    return peek


def apply_window(raw, settings, link):
    """A page's values into settings.json, and the site-owned boxes into the link.

    The card's box and the two hiding boxes are not settings: one lives in
    account.json and the others are a row on the site, so none can go through
    `settings.update`. They are read off the same page all the same, because
    to the player they are boxes in the same list.
    """
    wanted = raw.get(CARD_VAR)
    if isinstance(wanted, bool) and link is not None and wanted != (not link.card_hidden):
        if wanted:
            link.show_card()
        else:
            link.hide_card()
    hidden = raw.get(HIDE_VAR)
    # Absent from the page for anyone who is not a supporter, which is the
    # same thing as leaving it alone.
    if isinstance(hidden, bool) and link is not None and hidden != link.loadouts_hidden:
        link.hide_loadouts(hidden)
    battles_hidden = raw.get(HIDE_BATTLES_VAR)
    # Absent from the page for a game not linked to an account.
    if (isinstance(battles_hidden, bool) and link is not None
            and battles_hidden != link.battles_hidden):
        link.hide_battles(battles_hidden)
    settings.update(from_window(raw))

def to_window(values, card_shown=True, loadouts_hidden=False, battles_hidden=False):
    """What the window stores for these settings: flat, choices by index."""
    window = {CARD_VAR: card_shown, HIDE_VAR: loadouts_hidden,
              HIDE_BATTLES_VAR: bool(battles_hidden),
              'enabled': values['enabled'], 'maxFlags': values['maxFlags'], 'tankButton': values['tankButton'],
              'sendLoadouts': values['sendLoadouts'],
              'sendReplays': values['sendReplays'],
              'measurePerformance': values['measurePerformance'],
              'autoReload': RELOAD_CHOICES.index(values['autoReload']),
              'minimapNames': MINIMAP_NAME_CHOICES.index(values['minimapNames']),
              'twitchChannel': values['twitch']['channel'],
              'twitchBattle': BATTLE_CHAT_CHOICES.index(values['twitch']['battle']),
              'twitchPanelText': TEXT_SIZE_CHOICES.index(values['twitch']['panelText']),
              'twitchBattleText': TEXT_SIZE_CHOICES.index(values['twitch']['battleText']),
              'twitchGarage': values['twitch']['garage'],
              'metric': METRICS.index(values['metric']), 'window': WINDOWS.index(values['window']),
              'winrate': EXTRAS.index(values['winrate']), 'battles': EXTRAS.index(values['battles']),
              'winrateDecimal': values['winrateDecimal']}
    for key in _ALT_KEYS:
        window[_alt_key(key)] = 1 if values['altOnly'][key] else 0
    for key in _MENU_KEYS:
        window[_menu_key(key)] = values['contextMenu'][key]
    for mode in MODES:
        teams = values['modes'][mode]
        window[_mode_key(mode)] = _choice_of(TEAM_CHOICES, teams['allies'], teams['enemies'])
    for surface in SURFACES:
        window[_show_key(surface)] = _choice_of(SHOW_CHOICES, values[surface]['rating'], values[surface]['flags'])
    for surface in FIGURED:
        window[_figures_key(surface)] = FIGURE_CHOICES.index(values[surface]['figures'])
    return window

def from_window(raw):
    """settings.json changes from what the window sends back."""
    changes = {}
    for key in ('enabled', 'tankButton', 'sendLoadouts', 'sendReplays',
                'measurePerformance', 'winrateDecimal'):
        if isinstance(raw.get(key), bool):
            changes[key] = raw[key]
    announced = _index(raw.get('autoReload'), RELOAD_CHOICES)
    if announced is not None:
        changes['autoReload'] = RELOAD_CHOICES[announced]
    labelled = _index(raw.get('minimapNames'), MINIMAP_NAME_CHOICES)
    if labelled is not None:
        changes['minimapNames'] = MINIMAP_NAME_CHOICES[labelled]
    context_menu = dict((key, bool(raw[_menu_key(key)])) for key in _MENU_KEYS
                        if isinstance(raw.get(_menu_key(key)), bool))
    if context_menu:
        changes['contextMenu'] = context_menu
    alt_only = dict((key, bool(raw[_alt_key(key)])) for key in _ALT_KEYS
                    if _index(raw.get(_alt_key(key)), WHEN_CHOICES) is not None)
    if alt_only:
        changes['altOnly'] = alt_only
    twitch = {}
    if isinstance(raw.get('twitchChannel'), basestring):
        twitch['channel'] = raw['twitchChannel']
    battle = _index(raw.get('twitchBattle'), BATTLE_CHAT_CHOICES)
    if battle is not None:
        twitch['battle'] = BATTLE_CHAT_CHOICES[battle]
    if isinstance(raw.get('twitchGarage'), bool):
        twitch['garage'] = raw['twitchGarage']
    for var, key in (('twitchPanelText', 'panelText'), ('twitchBattleText', 'battleText')):
        step = _index(raw.get(var), TEXT_SIZE_CHOICES)
        if step is not None:
            twitch[key] = TEXT_SIZE_CHOICES[step]
    if twitch:
        changes['twitch'] = twitch
    if _index(raw.get('metric'), METRICS) is not None:
        changes['metric'] = METRICS[raw['metric']]
    if _index(raw.get('window'), WINDOWS) is not None:
        changes['window'] = WINDOWS[raw['window']]
    for key in ('winrate', 'battles'):
        if _index(raw.get(key), EXTRAS) is not None:
            changes[key] = EXTRAS[raw[key]]
    if isinstance(raw.get('maxFlags'), (int, float)) and not isinstance(raw.get('maxFlags'), bool):
        changes['maxFlags'] = int(raw['maxFlags'])
    for surface in SURFACES:
        index = _index(raw.get(_show_key(surface)), SHOW_CHOICES)
        if index is not None:
            _, rating, flags = SHOW_CHOICES[index]
            changes[surface] = {'rating': rating, 'flags': flags}
            if surface in AVERAGED:
                changes[surface]['average'] = rating
    for surface in FIGURED:
        index = _index(raw.get(_figures_key(surface)), FIGURE_CHOICES)
        if index is not None:
            # Into whatever this surface already has in `changes`, not over
            # it: the show dropdown above writes its own dict for the same
            # surface, and the last one to assign would win.
            changes.setdefault(surface, {})['figures'] = FIGURE_CHOICES[index]
    modes = {}
    for mode in MODES:
        index = _index(raw.get(_mode_key(mode)), TEAM_CHOICES)
        if index is not None:
            _, allies, enemies = TEAM_CHOICES[index]
            modes[mode] = {'allies': allies, 'enemies': enemies}
    if modes:
        changes['modes'] = modes
    return changes

def _show_key(surface):
    return surface + 'Show'


def _figures_key(surface):
    return surface + 'Figures'

def _mode_key(mode):
    return 'mode%s' % (mode[0].upper() + mode[1:])

def _alt_key(key):
    return 'altOnly' + key.capitalize()

def _menu_key(key):
    return 'contextMenu' + key.capitalize()

def _choice_of(choices, first, second):
    """The index of the (label, first, second) option in `choices` matching two switches."""
    for index, (_, a, b) in enumerate(choices):
        if a == first and b == second:
            return index
    return 0

def _index(value, options):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < len(options):
        return int(value)
    return None

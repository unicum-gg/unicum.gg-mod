"""The settings page, written out twice for two UI backends.

`template` builds the page izeberg's modsSettingsApi draws, and `native_page`
the same page for the client's own settings tab. Two renderings of one page,
which is why they sit together: a row added to one and forgotten in the other
is the mistake this arrangement is meant to make obvious.
"""
from __future__ import absolute_import

import logging

from unicum.settings import EXTRAS, MAX_FLAGS, METRICS, MODES, WINDOWS
from unicum.settings_window.labels import (_ALT_SCREENS, _CHOICE_WIDTH,
                                           _CONNECT_TOOLTIP, _EXTRA_LABELS,
                                           _LINK_TOOLTIPS, _MENU_KEYS,
                                           _MODES_TOOLTIP, _RESET_TOOLTIP,
                                           _RULE, _SURFACE_LABELS,
                                           _TAB_TOOLTIP, _WINDOW_LABELS,
                                           BATTLES_LABEL, CARD_LABEL,
                                           CARD_VAR, CONNECT_VAR,
                                           DISCORD_VAR, HIDE_VAR, LINKS,
                                           MEASURE_LABEL, MINIMAP_NAME_LABELS,
                                           RELOAD_LABELS, REPLAYS_LABEL,
                                           RESET_BUTTON, RESET_LABEL,
                                           RESET_VAR, SHOW_CHOICES,
                                           SOURCE_VAR, SUPPORT_VAR,
                                           TEAM_CHOICES, WHEN_CHOICES,
                                           _GARAGE_SURFACES, _MODE_LABELS,
                                           _SPACER, BATTLES_TOOLTIP,
                                           GARAGE_CHAT_LABEL, HIDE_LABEL,
                                           REPLAYS_TOOLTIP)
from unicum.settings_window.codec import (_alt_key, _menu_key, _mode_key,
                                          _show_key, to_window)

_logger = logging.getLogger('unicum.settings_window.page')

def _heading(templates, text):
    return templates.createLabel(u'%s  %s' % (text.upper(), _RULE))

def channel_label(channel, linked):
    """The Twitch section's channel line."""
    if not channel:
        return u'Channel: not linked'
    return u'Channel: %s' % channel if linked else u'Channel: %s (Connect to write in it)' % channel

def _button_line(templates, text, var, button, tooltip=None):
    # A label with a button: the API draws one on any component that names a
    # varName, which is what the button's callback reports.
    return dict(templates.createLabel(text, tooltip=tooltip), varName=var,
                button=templates.createButton(width=90, height=24, text=button))

def template(values, channel=u'', linked=False, card_shown=True,
             supporter=False, loadouts_hidden=False):
    """The API's page for these settings, showing `values` and the Twitch channel followed.

    `linked` is whether the Twitch chat can be written to, `card_shown` whether
    the account card shows for the account logged in. `supporter` decides
    whether the hiding box is drawn at all, and `loadouts_hidden` where it sits.
    """
    from gui.modsSettingsApi import templates
    window = to_window(values, card_shown, loadouts_hidden)

    def checkbox(label, var, tooltip=None):
        return templates.createCheckbox(label, var, window[var], tooltip=tooltip)

    def choice(label, var, options, tooltip=None):
        return templates.createDropdown(label, var, list(options), window[var], tooltip=tooltip, width=_CHOICE_WIDTH)

    def show(surface):
        return choice(_SURFACE_LABELS[surface], _show_key(surface), [c[0] for c in SHOW_CHOICES])

    garage = [
        _heading(templates, 'Garage'),
        choice('Rating', 'metric', [metric.upper() for metric in METRICS]),
        choice('Period', 'window', [_WINDOW_LABELS[w] for w in WINDOWS],
               tooltip='{HEADER}Rating period{/HEADER}{BODY}Last 30 days falls back to overall while the '
                       '30-day value is not computed yet.{/BODY}'),
        choice('Win rate', 'winrate', [_EXTRA_LABELS[e] for e in EXTRAS],
               tooltip='{HEADER}Win rate{/HEADER}{BODY}Drawn beside the rating, wherever the rating is '
                       'drawn, in grey so the badge stays what you read first. Its period is its own: a '
                       'rating reads as form, a win rate is usually wanted over a whole career.{/BODY}'),
        checkbox('Win rate to a tenth', 'winrateDecimal',
                 tooltip='{HEADER}Win rate to a tenth{/HEADER}{BODY}Draws 58.7% instead of 59%. Off by '
                         'default: the rating badge beside it is a whole number too, and a tenth of a '
                         'point is not something you read at a glance.{/BODY}'),
        choice('Battles', 'battles', [_EXTRA_LABELS[e] for e in EXTRAS],
               tooltip='{HEADER}Battles{/HEADER}{BODY}How many battles the player has, beside the rating. '
                       'Shortened past ten thousand in the players panel, where a column is all the room '
                       'there is, and written out in full everywhere else.{/BODY}'),
        templates.createNumericStepper('Flags per player or clan', 'maxFlags', window['maxFlags'], 1, MAX_FLAGS, 1),
        templates.createEmpty(_SPACER),
    ]
    garage.extend(show(surface) for surface in _GARAGE_SURFACES)
    garage.extend([
        choice('Skirmish room: when', _alt_key('skirmishRoom'), WHEN_CHOICES,
               tooltip='{HEADER}Skirmish room{/HEADER}{BODY}While Alt is held, the members ratings and '
                       'flags show, and the average of the detachment with them. The order they are '
                       'sorted in stays whatever you chose.{/BODY}'),
        choice('Stronghold: when', _alt_key('stronghold'), WHEN_CHOICES),
        choice('Battle results: when', _alt_key('results'), WHEN_CHOICES),
        templates.createEmpty(_SPACER),
        checkbox('Tank menu button', 'tankButton',
                 tooltip='{HEADER}Tank menu button{/HEADER}{BODY}A unicum.gg button beside the vehicle menu, '
                         'with links for the selected tank: its unicum.gg tabs, AI assistants and its '
                         'build.{/BODY}'),
        checkbox('Right-click a player', _menu_key('players'),
                 tooltip='{HEADER}Right-click a player{/HEADER}{BODY}Adds unicum.gg entries to the menu the '
                         'game opens on a player: their page, and the AI assistants. In battle, in the battle '
                         'results, in your contacts and in a skirmish room.{/BODY}'),
        checkbox('Right-click a tank', _menu_key('vehicles'),
                 tooltip='{HEADER}Right-click a tank{/HEADER}{BODY}The same on the menu the game opens on a '
                         'vehicle: the carousel, the tech tree, the shop and the comparison.{/BODY}'),
        checkbox('Share my loadouts', 'sendLoadouts',
                 tooltip='{HEADER}Share my loadouts{/HEADER}{BODY}Sends how you have set your tanks up, so your own unicum.gg page shows them: equipment, crew skills, field modifications, ammunition. Nothing about anyone else, and Wargaming publishes none of it, so a page is only as complete as the players who share. Untick it to stop, and to have everything already sent deleted.{/BODY}'),
    ])
    # Only for the accounts that may use it. A box drawn greyed out for
    # everybody else would be advertising the subscription rather than
    # describing a setting, and this list is a list of settings.
    if supporter:
        garage.append(checkbox(
            HIDE_LABEL, HIDE_VAR,
            tooltip='{HEADER}' + HIDE_LABEL + '{/HEADER}{BODY}Keeps sending your loadouts, so they still count '
                    'towards what the site can say about a tank, but takes them off your own public page. To '
                    'stop sending them altogether, and delete the ones already sent, untick Share my loadouts '
                    'instead.{/BODY}'))
    garage.extend([
        checkbox(BATTLES_LABEL, 'sendBattles', tooltip=BATTLES_TOOLTIP),
        checkbox(REPLAYS_LABEL, 'sendReplays', tooltip=REPLAYS_TOOLTIP),
        checkbox(CARD_LABEL, CARD_VAR,
                 tooltip='{HEADER}' + CARD_LABEL + '{/HEADER}{BODY}The card under the mission cards that '
                         'links this game to your unicum.gg account, or says which one it is linked to. Its '
                         'cross hides it for the account logged in; tick this to bring it back.{/BODY}'),
        checkbox(MEASURE_LABEL, 'measurePerformance',
                 tooltip='{HEADER}' + MEASURE_LABEL + '{/HEADER}{BODY}Times everything this mod does on the '
                         'thread that draws the game and writes a table to python.log every ten seconds, '
                         'worst first. Turn it on only to answer a question about frame rate, and send the '
                         'table with the report. It measures this mod alone, not the game and not the other '
                         'mods installed.{/BODY}'),
        checkbox(GARAGE_CHAT_LABEL, 'twitchGarage'),
        # Connect only while it has something to do: once the chat can be
        # written to, the line only says which channel it is.
        (templates.createLabel(channel_label(channel, linked), tooltip=_CONNECT_TOOLTIP) if linked else
         _button_line(templates, channel_label(channel, linked), CONNECT_VAR, 'Connect', _CONNECT_TOOLTIP)),
        templates.createEmpty(_SPACER),
    ])
    garage.extend(_button_line(templates, text, var, word, _LINK_TOOLTIPS[var]) for var, text, word in LINKS)
    garage.append(_button_line(templates, RESET_LABEL, RESET_VAR, RESET_BUTTON, _RESET_TOOLTIP))

    battle = [
        _heading(templates, 'Battle'),
        show('battle'),
        templates.createEmpty(_SPACER),
    ]
    battle.extend(choice(_MODE_LABELS[mode], _mode_key(mode), [c[0] for c in TEAM_CHOICES],
                         tooltip=_MODES_TOOLTIP if mode == MODES[0] else None) for mode in MODES)
    battle.append(templates.createEmpty(_SPACER))
    battle.extend(choice(label, _alt_key(key), WHEN_CHOICES, tooltip=_TAB_TOOLTIP if key == 'tab' else None)
                  for key, label in _ALT_SCREENS)
    battle.extend([
        templates.createEmpty(_SPACER),
        checkbox('Twitch chat in battle', 'twitchBattleChat'),
        choice('Announce reloading', 'autoReload', RELOAD_LABELS,
               tooltip='{HEADER}Announce reloading{/HEADER}{BODY}Sends the "Reloading!" message to your team '
                       'by itself, as F8 does. Every gun announces after each shot; autoloaders only, once a '
                       'magazine is empty, which is far less talking. Reloads shorter than the 5-second limit '
                       'of the chat are never announced.{/BODY}'),
        choice('Minimap labels', 'minimapNames', MINIMAP_NAME_LABELS,
               tooltip='{HEADER}Minimap labels{/HEADER}{BODY}What is written beside a vehicle on the minimap. '
                       'The game writes the vehicle; calling out a flank usually wants the player. This only '
                       'changes a label the game was already going to write, so it stays off entirely while '
                       'the game\'s own minimap names are turned off.{/BODY}'),
    ])
    return {'modDisplayName': 'unicum.gg', 'enabled': values['enabled'],
            'column1': garage, 'column2': battle}

def native_page(values, channel=u'', linked=False, card_shown=True,
                supporter=False, loadouts_hidden=False):
    """The same settings for the unicum.gg tab of the game's settings window (settings_tab.py).

    The same variables and the same choices as template(), laid out for a
    window this mod draws itself: sub-tabs, framed groups in two columns, a
    line a setting. As text the AS3 side reads without a JSON parser, a line
    an item, its fields apart by tabs:

      tab       label
      group     column (0 or 1), title
      dropdown  var, label, selected index, offset, options apart by "|"
      checkbox  var, label, 1 or 0
      text      label
      button    var, label, button text

    A dropdown sends back its index plus its offset: maxFlags counts from 1.
    """
    window = to_window(values, card_shown, loadouts_hidden)
    lines = []

    def tab(label):
        lines.append(u'tab\t' + label)

    def group(column, title):
        lines.append(u'group\t%d\t%s' % (column, title))

    def dropdown(label, var, options, offset=0):
        lines.append(u'dropdown\t%s\t%s\t%d\t%d\t%s' % (var, label, window[var] - offset, offset,
                                                         u'|'.join(options)))

    def show(surface):
        dropdown(_SURFACE_LABELS[surface], _show_key(surface), [c[0] for c in SHOW_CHOICES])

    def checkbox(label, var):
        lines.append(u'checkbox\t%s\t%s\t%d' % (var, label, 1 if window[var] else 0))

    tab(u'Garage')
    group(0, u'Stats')
    dropdown(u'Rating', 'metric', [metric.upper() for metric in METRICS])
    dropdown(u'Period', 'window', [_WINDOW_LABELS[w] for w in WINDOWS])
    dropdown(u'Win rate', 'winrate', [_EXTRA_LABELS[e] for e in EXTRAS])
    checkbox(u'Win rate to a tenth', 'winrateDecimal')
    dropdown(u'Battles', 'battles', [_EXTRA_LABELS[e] for e in EXTRAS])
    dropdown(u'Flags per player or clan', 'maxFlags', [str(n) for n in range(1, MAX_FLAGS + 1)], offset=1)
    group(0, u'Garage')
    checkbox(u'Tank menu button', 'tankButton')
    checkbox(u'Right-click a player', _menu_key('players'))
    checkbox(u'Right-click a tank', _menu_key('vehicles'))
    checkbox(u'Share my loadouts', 'sendLoadouts')
    if supporter:
        checkbox(HIDE_LABEL, HIDE_VAR)
    checkbox(BATTLES_LABEL, 'sendBattles')
    checkbox(REPLAYS_LABEL, 'sendReplays')
    checkbox(CARD_LABEL, CARD_VAR)
    checkbox(MEASURE_LABEL, 'measurePerformance')
    group(1, u'Screens')
    for surface in _GARAGE_SURFACES:
        show(surface)
    dropdown(u'Skirmish room: when', _alt_key('skirmishRoom'), WHEN_CHOICES)
    dropdown(u'Stronghold: when', _alt_key('stronghold'), WHEN_CHOICES)
    dropdown(u'Battle results: when', _alt_key('results'), WHEN_CHOICES)
    group(1, u'unicum.gg')
    for var, text, word in LINKS:
        lines.append(u'button	%s	%s	%s' % (var, text, word))
    lines.append(u'button	%s	%s	%s' % (RESET_VAR, RESET_LABEL, RESET_BUTTON))

    tab(u'Battle')
    group(0, u'What and when')
    show('battle')
    for key, label in _ALT_SCREENS:
        dropdown(label, _alt_key(key), WHEN_CHOICES)
    group(0, u'Tools')
    dropdown(u'Announce reloading', 'autoReload', RELOAD_LABELS)
    dropdown(u'Minimap labels', 'minimapNames', MINIMAP_NAME_LABELS)
    group(1, u'Whose stats, per mode')
    for mode in MODES:
        dropdown(_MODE_LABELS[mode], _mode_key(mode), [c[0] for c in TEAM_CHOICES])

    tab(u'Twitch')
    group(0, u'Twitch')
    if linked:
        lines.append(u'text\t' + channel_label(channel, linked))
    else:
        lines.append(u'button\t%s\t%s\tConnect' % (CONNECT_VAR, channel_label(channel, linked)))
    checkbox(GARAGE_CHAT_LABEL, 'twitchGarage')
    checkbox(u'Chat in battle', 'twitchBattleChat')
    return u'\n'.join(line.replace(u'\n', u' ') for line in lines)

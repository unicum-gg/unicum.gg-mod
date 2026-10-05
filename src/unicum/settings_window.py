"""The settings in izeberg's modsSettingsApi window, when that mod is installed.

Optional: without gui.modsSettingsApi this does nothing, and settings.json
stays the way to change anything. With it, the window shows a page for the
mod (in CHAMPi's settings window too, which reads the same API), and every
change there is written to settings.json, the one source of truth.

The window only knows flat values, each choice by the index of its option:
what a screen shows is <surface>Show (SHOW_CHOICES), whose stats a battle
mode shows mode<Mode> (TEAM_CHOICES), and when a screen shows them
altOnly<Screen> (WHEN_CHOICES).

Two behaviours of the API (1.7.0) shape this:

  - setModTemplate resets the window's saved values whenever the template
    differs from the last one registered. The template is built from the
    current settings, so a reset lands on what settings.json already says.
  - Callbacks are added to an event and never removed by the API, so every
    reload of this package would stack one. The session removes its own on
    close, and a callback that outlives its session does nothing.
"""
import json
import logging

from unicum.settings import AVERAGED, EXTRAS, MAX_FLAGS, METRICS, MODES, RELOAD_CHOICES, SURFACES, WINDOWS

_logger = logging.getLogger('unicum.settings_window')

LINKAGE = 'gg.unicum'

_WINDOW_LABELS = {'recent': 'Last 30 days', 'total': 'Overall'}

# The plain figures beside a rating, in the order of EXTRAS. Overall rather
# than the rating's own period by default: "how many battles has this player"
# is a question about a career, not about this month.
_EXTRA_LABELS = {'off': 'Off', 'total': 'Overall', 'recent': 'Last 30 days'}
_MODE_LABELS = {
    'random': 'Random battles',
    'ranked': 'Ranked battles',
    'onslaught': 'Onslaught',
    'stronghold': 'Stronghold',
    'frontline': 'Frontline',
    'training': 'Training rooms',
    'other': 'Other modes',
}
# The API has two columns and no sections, one control a line. So the page is
# the game's two places: the garage in the first column, the battle in the
# second, each holding everything that happens there. Every line reads the
# same way: where, then a dropdown among the same options as its neighbours,
# all of one width. Not a radio button group: CHAMPi's window draws one as a
# row of buttons, but Aslain's Mod Menu as a column of radio buttons, four
# lines a choice.
_SPACER = 12

# Wide enough for the longest option, "Ratings and flags".
_CHOICE_WIDTH = 200

# (label, rating, flags): what a screen shows. A team or detachment average
# goes with the ratings, being one.
SHOW_CHOICES = (
    ('Ratings and flags', True, True),
    ('Ratings only', True, False),
    ('Flags only', False, True),
    ('Nothing', False, False),
)

# (label, allies, enemies): whose stats a battle mode shows.
TEAM_CHOICES = (
    ('Both teams', True, True),
    ('Allies only', True, False),
    ('Enemies only', False, True),
    ('Nobody', False, False),
)

# When a screen shows them: at once, or while the extended info key is held.
WHEN_CHOICES = ('Always', 'While Alt is held')

# Which reloads are announced, in the order of RELOAD_CHOICES.
RELOAD_LABELS = ('Never', 'Every gun', 'Autoloaders only')

_SURFACE_LABELS = {
    'contacts': 'Contacts list',
    'profile': 'Profile',
    'skirmishRoom': 'Skirmish room',
    'stronghold': 'Stronghold',
    'battleResults': 'Battle results',
    'battle': 'In battle',
}
_GARAGE_SURFACES = ('contacts', 'profile', 'skirmishRoom', 'stronghold', 'battleResults')

# The battle's screens that can wait for Alt, and the altOnly key of each.
_ALT_SCREENS = (('markers', 'Above tanks'), ('panel', 'Players list'), ('tab', 'Tab screen'),
                ('loading', 'Loading screen'))
_ALT_KEYS = ('markers', 'panel', 'tab', 'loading', 'results', 'skirmishRoom', 'stronghold')

# The two right-click switches, kept apart because they are wanted apart: the
# tank menus reach the tech tree and the shop, where a player menu never goes.
_MENU_KEYS = ('players', 'vehicles')

# Nor any rule, so a heading draws its own with em dashes: box-drawing
# characters are missing from the window's font and drew nothing.
_RULE = u'\u2014' * 16


def _heading(templates, text):
    return templates.createLabel(u'%s  %s' % (text.upper(), _RULE))


# The line carrying a button: the Twitch section's Connect. Linking the account
# alone is the garage's account card (account_card.js).
CONNECT_VAR = 'twitchConnect'

_CONNECT_TOOLTIP = ('{HEADER}Twitch{/HEADER}{BODY}The channel is the one linked to your unicum.gg account. '
                    'Connect links this game to that account and your Twitch channel, in your browser: nothing '
                    'to type, you only confirm. Then the battle chat has a TO TWITCH receiver, and the garage '
                    'panel a field to write in your chat.{/BODY}')


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


# The button opening the site's support page in the player's browser. Not a
# setting: nothing is stored, the click only opens the page.
SUPPORT_VAR = 'support'

DISCORD_VAR = 'discord'

SOURCE_VAR = 'source'

DISCORD_URL = 'https://discord.gg/Hqbfb8YPbU'

SOURCE_URL = 'https://github.com/unicum-gg/unicum.gg-mod'

# Each line of the unicum.gg section: the variable, what it says, and the
# button's own word. Order matters, it is the order they are drawn in.
LINKS = (
    (SUPPORT_VAR, 'unicum.gg is free and has no ads', 'Support'),
    (DISCORD_VAR, 'Questions, ideas and bug reports', 'Discord'),
    (SOURCE_VAR, "The mod's source and its issues", 'GitHub'),
)

_LINK_TOOLTIPS = {
    SUPPORT_VAR: ('{HEADER}Support unicum.gg{/HEADER}{BODY}The site and this mod are free, with no ads and '
                  'nothing held back for payers. Opens the support page in your browser, where you choose '
                  'what you give, if anything.{/BODY}'),
    DISCORD_VAR: ('{HEADER}Discord{/HEADER}{BODY}The unicum.gg server, where the mod is talked about: ask a '
                  'question, say what is missing, or report what went wrong. Opens in your browser.{/BODY}'),
    SOURCE_VAR: ('{HEADER}GitHub{/HEADER}{BODY}Everything this mod does is written down and open to read. '
                 'Opens the repository in your browser, where issues are filed too.{/BODY}'),
}


# The button putting every setting back to what it was before anything was
# changed. Not a setting either: the click acts, nothing is stored.
RESET_VAR = 'resetDefaults'

RESET_LABEL = 'Every setting back to its default'

RESET_BUTTON = 'Reset'

_RESET_TOOLTIP = ('{HEADER}Reset{/HEADER}{BODY}Puts every setting of this mod back to what it was when it '
                  'was installed, at once, in this window and in the mods list alike. Nothing else is '
                  'touched: the account this game is linked to stays linked.{/BODY}')


def reset_defaults(settings):
    """Every setting back to its default, and a system message saying so."""
    from unicum.settings import DEFAULTS
    settings.update(json.loads(json.dumps(DEFAULTS)))
    _logger.info('the settings were put back to their defaults')
    try:
        from gui import SystemMessages
        from gui.shared.notifications import NotificationPriorityLevel
        SystemMessages.pushMessage(u'unicum.gg: the settings are back to their defaults.',
                                   type=SystemMessages.SM_TYPE.Information,
                                   priority=NotificationPriorityLevel.MEDIUM)
    except Exception:
        _logger.debug('could not say that the settings were reset', exc_info=True)


def handle_button(var, settings, content):
    """What a button of either page does, apart from Twitch's Connect."""
    if var == RESET_VAR:
        reset_defaults(settings)
        return True
    return open_link(var, content)


def link_url(var, content):
    """Where a link button goes, or None for a variable that is not one."""
    from unicum import tank_button
    if var == SUPPORT_VAR:
        return tank_button.support_url(content)
    return {DISCORD_VAR: DISCORD_URL, SOURCE_VAR: SOURCE_URL}.get(var)


def open_link(var, content):
    """A link button's page in the player's browser; True if it was one."""
    url = link_url(var, content)
    if url is None:
        return False
    from unicum import tank_button
    tank_button.open_url(url)
    return True


# The account card's checkbox. Not a settings.json value: the card's own cross
# hides it for the Wargaming account logged in, in account.json, and this box
# is the way back, which the cross alone never offered.
CARD_VAR = 'accountCard'

# Labels the garage's notices send the player looking for, so a notice and the
# window cannot name the same box differently. The Twitch panel's notice once
# pointed at "Twitch chat in the garage", a box that never existed.
CARD_LABEL = 'unicum.gg account card'
GARAGE_CHAT_LABEL = 'Chat panel in the garage'

# Not a settings.json value either: the site owns this row, and the box is
# only drawn for the accounts allowed to move it.
HIDE_VAR = 'hideLoadouts'
HIDE_LABEL = 'Hide my loadouts from my page'

# DRAFT WORDING, pending approval: this is public text a player reads before
# deciding, the box is ticked when they first see it, and the decision it asks
# for is about other people's battles as much as their own.
#
# The last sentence is the one that has to be there. The loadout box above
# promises that unticking deletes what was already sent, and this one cannot
# promise the same: a battle is thirty players' data and one of them cannot
# withdraw it for the others. A ticked-by-default box whose words let a player
# assume otherwise would be the dishonest version of this feature.
BATTLES_LABEL = 'Share the battles I play'
BATTLES_TOOLTIP = (
    '{HEADER}' + BATTLES_LABEL + '{/HEADER}{BODY}Sends the result of each battle you finish: the map, '
    'the mode, and what every vehicle in it did. Wargaming publishes none of this, so a battle exists '
    'on unicum.gg only because somebody who was in it shared it. A battle names all thirty players, so '
    'sharing yours shares theirs too, and theirs shares yours. The result alone: no chat, no replay, '
    'nothing about what you own; the replay file is the separate setting below. Untick it to stop '
    'sending; battles already shared stay, because they are thirty '
    "players' results and not one account's to take back.{/BODY}")

REPLAYS_LABEL = 'Share the replay file too'
REPLAYS_TOOLTIP = (
    '{HEADER}' + REPLAYS_LABEL + '{/HEADER}{BODY}Sends the .wotreplay your client already writes '
    'for each battle, on top of the result. It carries everything your client saw, the battle chat '
    'included, which the result does not: so it shares what the other twenty-nine typed as well as '
    'what you typed. It is kept for a 3D view of a battle, which needs shell paths and hit geometry '
    'that cannot be collected after the fact. Your client keeps only the last battle unless you '
    'changed that, so this takes a copy before the next one overwrites it. Untick it to stop '
    'sending; files already sent stay.{/BODY}')

MEASURE_LABEL = 'Measure what this mod costs'


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


def apply_window(raw, settings, link):
    """A page's values into settings.json, and the two site-owned boxes into the link.

    The card's box and the loadout-hiding box are not settings: one lives in
    account.json and the other is a row on the site, so neither can go through
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
    settings.update(from_window(raw))


_MODES_TOOLTIP = ('{HEADER}Whose stats, per mode{/HEADER}{BODY}Enemies only or Nobody keep the other team\'s '
                  'ratings and flags out of a mode, ranked battles for instance. It applies everywhere in battle: '
                  'players list, Tab, loading screen and above tanks.{/BODY}')

_TAB_TOOLTIP = ('{HEADER}Tab screen{/HEADER}{BODY}Press Tab first, then Alt: Alt then Tab switches windows. The '
                'random battles\' Tab screen shows no ratings either way.{/BODY}')


def to_window(values, card_shown=True, loadouts_hidden=False):
    """What the window stores for these settings: flat, choices by index."""
    window = {CARD_VAR: card_shown, HIDE_VAR: loadouts_hidden,
              'enabled': values['enabled'], 'maxFlags': values['maxFlags'], 'tankButton': values['tankButton'],
              'sendLoadouts': values['sendLoadouts'],
              'sendBattles': values['sendBattles'],
              'measurePerformance': values['measurePerformance'],
              'autoReload': RELOAD_CHOICES.index(values['autoReload']),
              'twitchChannel': values['twitch']['channel'], 'twitchBattleChat': values['twitch']['battleChat'],
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
    return window


def from_window(raw):
    """settings.json changes from what the window sends back."""
    changes = {}
    for key in ('enabled', 'tankButton', 'sendLoadouts', 'sendBattles',
                'measurePerformance', 'winrateDecimal'):
        if isinstance(raw.get(key), bool):
            changes[key] = raw[key]
    announced = _index(raw.get('autoReload'), RELOAD_CHOICES)
    if announced is not None:
        changes['autoReload'] = RELOAD_CHOICES[announced]
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
    if isinstance(raw.get('twitchBattleChat'), bool):
        twitch['battleChat'] = raw['twitchBattleChat']
    if isinstance(raw.get('twitchGarage'), bool):
        twitch['garage'] = raw['twitchGarage']
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


class SettingsWindow(object):

    def __init__(self, session, settings, link=None):
        self._session = session
        self._settings = settings
        self._link = link
        self._chat = None
        # (channel followed, Twitch chat writable, game linked, account name,
        # card shown, supports the site, loadouts hidden) as the page shows
        # them. It has to match what `_register` unpacks and what
        # `_check_state` builds: `install` registers off this one, before the
        # link has answered anything.
        self._state = (u'', False, False, None, True, False, False)
        self._alive = True
        self._api = None

    def install(self):
        try:
            from gui.modsSettingsApi import g_modsSettingsApi
        except ImportError:
            _logger.info('modsSettingsApi not installed, settings.json only')
            return
        self._api = g_modsSettingsApi
        self._register()
        self._session.on_close(self._remove)
        self._settings.on_change(self._on_settings)
        _logger.info('registered in modsSettingsApi as %s', LINKAGE)

    def follow_twitch(self, chat):
        """Show the channel `chat` follows, and the account link, as they change."""
        self._chat = chat
        if self._api is not None:
            self._session.repeat(2.0, self._check_state)

    def _check_state(self):
        link = self._link
        linked = bool(link is not None and link.secret)
        state = (self._chat.channel if self._chat is not None else u'',
                 linked and link.twitch == 'ready', linked, link.name if linked else None,
                 self._card_shown(), self._supporter(), self._hidden())
        if state == self._state:
            return
        self._state = state
        # A new template replaces the page; its callbacks are added again, so
        # the ones already on the API's events come off first.
        self._unregister()
        self._register()

    def _card_shown(self):
        return not (self._link is not None and self._link.card_hidden)

    def _supporter(self):
        return bool(self._link is not None and self._link.supporter)

    def _hidden(self):
        return bool(self._link is not None and self._link.loadouts_hidden)

    def _register(self):
        channel, writable, linked, name, card_shown, supporter, hidden = self._state
        self._api.setModTemplate(LINKAGE, template(self._settings.values(), channel, writable, card_shown,
                                                   supporter, hidden),
                                 self._on_window, self._on_button)
        # The API keeps its own copy of every value and sends it back as the
        # player's choice. For the card that copy can be stale (the card's
        # cross changes the truth without going through the window), and an
        # old "shown" coming back would undo the cross: so it is set to the
        # truth first.
        self._api.updateModSettings(LINKAGE, to_window(self._settings.values(), card_shown, hidden))

    def _on_window(self, linkage, raw):
        if not self._alive or linkage != LINKAGE or not isinstance(raw, dict):
            return
        apply_window(raw, self._settings, self._link)

    def _on_button(self, linkage, var_name, value=None):
        if not self._alive or linkage != LINKAGE:
            return
        if handle_button(var_name, self._settings, 'mods-list'):
            return
        if self._link is not None and var_name == CONNECT_VAR:
            self._link.connect(_linked_notice)

    def _on_settings(self):
        """Keep the window in step with a hand edit of settings.json."""
        # The API answers with onSettingsChanged, which lands in _on_window
        # with values that change nothing.
        self._api.updateModSettings(LINKAGE, to_window(self._settings.values(), self._card_shown()))

    def _remove(self):
        self._alive = False
        self._unregister()

    def _unregister(self):
        instance = getattr(self._api, '_ModsSettingsApi__instance', None)
        for name, handler in (('onSettingsChanged', self._on_window), ('onButtonClicked', self._on_button)):
            event = getattr(instance, name, None)
            try:
                event -= handler
            except Exception:
                _logger.debug('could not unregister %s', name, exc_info=True)


def _linked_notice(name, twitch):
    """Tell the player, in the garage notifications, how linking ended."""
    from gui import SystemMessages
    if name is None:
        SystemMessages.pushMessage('unicum.gg: the game could not be linked. Try Connect again.',
                                   type=SystemMessages.SM_TYPE.Warning)
    else:
        SystemMessages.pushMessage('unicum.gg: linked to %s. Start a battle chat message with !t to write '
                                   'in your Twitch chat.' % name, type=SystemMessages.SM_TYPE.Information)


def install(session, settings, link=None):
    window = SettingsWindow(session, settings, link)
    window.install()
    return window

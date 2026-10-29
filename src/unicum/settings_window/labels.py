"""Every word the settings page shows, and the choices behind them.

Data, with one exception. Kept apart because this is the file somebody opens
to change what a setting is called, and nothing here decides anything: no
client, no state, no behaviour, so a wording change cannot break a page.

The exception is `linked_notice`, which three modules call to say an account
was linked. It was private and reached into from outside, which is what #3
calls the sign that this was more than a size problem, so it has a public
name and a home now.
"""
from __future__ import absolute_import

import logging

_logger = logging.getLogger('unicum.settings_window.labels')

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

# What the minimap writes beside a vehicle. "Vehicle" is the client untouched.
MINIMAP_NAME_LABELS = ('Vehicle', 'Player', 'Vehicle and player')

# Where the Twitch chat shows in battle, in the order of BATTLE_CHAT_CHOICES.
# "In a window" is the chat window of the queue screen, kept up over the
# battle; "In both" shows every message twice, which some players want.
BATTLE_CHAT_LABELS = ('Off', 'In the battle chat', 'In a window', 'In both')

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
                ('loading', 'Loading screen'), ('minimap', 'Minimap'))
_ALT_KEYS = ('markers', 'panel', 'tab', 'loading', 'results', 'skirmishRoom', 'stronghold',
             'minimap')

# The two right-click switches, kept apart because they are wanted apart: the
# tank menus reach the tech tree and the shop, where a player menu never goes.
_MENU_KEYS = ('players', 'vehicles')

# Nor any rule, so a heading draws its own with em dashes: box-drawing
# characters are missing from the window's font and drew nothing.
_RULE = u'\u2014' * 16

# The line carrying a button: the Twitch section's Connect. Linking the account
# alone is the garage's account card (account_card.js).
CONNECT_VAR = 'twitchConnect'

_CONNECT_TOOLTIP = ('{HEADER}Twitch{/HEADER}{BODY}The channel is the one linked to your unicum.gg account. '
                    'Connect links this game to that account and your Twitch channel, in your browser: nothing '
                    'to type, you only confirm. Then the battle chat has a TO TWITCH receiver, and the garage '
                    'panel a field to write in your chat.{/BODY}')

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

# The account card's checkbox. Not a settings.json value: the card's own cross
# hides it for the Wargaming account logged in, in account.json, and this box
# is the way back, which the cross alone never offered.
CARD_VAR = 'accountCard'

# Labels the garage's notices send the player looking for, so a notice and the
# window cannot name the same box differently. The Twitch panel's notice once
# pointed at "Twitch chat in the garage", a box that never existed.
CARD_LABEL = 'unicum.gg account card'
GARAGE_CHAT_LABEL = 'Chat panel in the garage'
BATTLE_CHAT_LABEL = 'Twitch chat in battle'

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

_MODES_TOOLTIP = ('{HEADER}Whose stats, per mode{/HEADER}{BODY}Enemies only or Nobody keep the other team\'s '
                  'ratings and flags out of a mode, ranked battles for instance. It applies everywhere in battle: '
                  'players list, Tab, loading screen and above tanks.{/BODY}')

_TAB_TOOLTIP = ('{HEADER}Tab screen{/HEADER}{BODY}Press Tab first, then Alt: Alt then Tab switches windows. The '
                'random battles\' Tab screen shows no ratings either way.{/BODY}')

def linked_notice(name, twitch):
    """Tell the player, in the garage notifications, how linking ended."""
    from gui import SystemMessages
    if name is None:
        SystemMessages.pushMessage('unicum.gg: the game could not be linked. Try Connect again.',
                                   type=SystemMessages.SM_TYPE.Warning)
    else:
        SystemMessages.pushMessage('unicum.gg: linked to %s. Start a battle chat message with !t to write '
                                   'in your Twitch chat.' % name, type=SystemMessages.SM_TYPE.Information)

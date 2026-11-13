"""Every setting this mod has, with the value it starts at.

One dict, and the tables the window and the checks both read to know what a
setting may be. This is the file to open to add a setting or change what one
starts as, and nothing here does anything: no client, no disk, no behaviour.
"""
from __future__ import absolute_import

import logging
import os
import re

_logger = logging.getLogger('unicum.settings.defaults')

STORE = os.path.join('mods', 'configs', 'unicum', 'settings.json')

# The ratings a player can read, in the order the dropdowns show them.
#
# The first three are unicum.gg's own, computed from a player's per-vehicle
# records against expected values, so they exist over any window two
# snapshots bound. The last two are Wargaming's, handed over finished as one
# figure per account: PR is `global_rating` on account/info, WTR is
# account/wtr, the rating the client itself has shown since 1.21.
#
# A new entry goes at the END. The settings window sends a choice as its
# index into this tuple (settings_window/codec.py), so inserting one in the
# middle would quietly move every player's saved choice along by one.
METRICS = ('wn7', 'wn8', 'wnx', 'pr', 'wtr')

# The ratings that exist over a whole career and nothing else.
#
# Wargaming serves them as one career number per account, and the difference
# between two readings of a career number is not a rating of the battles in
# between: there is no 30-day PR to be had. So /resolve carries them under
# `total` alone and leaves `recent` null, the window a player chose is not
# applied to them, and -- the part that would otherwise lie -- not claimed
# either: their label stays "PR" where a WN rating's reads "30d WN8".
CAREER_ONLY = ('pr', 'wtr')

WINDOWS = ('recent', 'total')

# The two plain numbers that can sit beside a rating: how many battles a
# player has, and what share of them they won. Each is off, over their whole
# career, or over the last 30 days, independently of the `window` the rating
# itself uses: a rating reads as form, where "how many battles" almost always
# means the career total. That is why they are their own settings rather than
# followers of `window`.
EXTRAS = ('off', 'total', 'recent')
MAX_FLAGS = 3

SURFACES = ('contacts', 'profile', 'skirmishRoom', 'battle', 'stronghold', 'battleResults')

# Surfaces with a team or detachment to average.
AVERAGED = ('skirmishRoom', 'battle', 'battleResults')

# What a surface's rows are about, in the order the window lists them. The
# order is a contract once published: the window sends an index back, so a
# later value goes on the end and no existing one moves.
#
#   career  the player, every tank together -- what every other surface shows
#   tank    the tank they brought, in the mode being played
#   both    one of the two at rest and the other while Alt is held, where the
#           column is a column; side by side where there is room for two
FIGURE_CHOICES = ('career', 'tank', 'both')

# Surfaces that can answer "on this tank": the ones whose rows know which
# vehicle they are about. A contact row and a profile title are a whole
# account, and a stronghold page is clans. Grown one surface at a time, as
# each learns to draw it -- a dropdown over a surface that ignores it would
# be worse than no dropdown.
FIGURED = ('battle', 'battleResults')

# Where each starts. The value that leaves every screen as it is today, which
# for the battle is the career at rest with Alt showing the tank, and which
# everywhere else is the career alone: nothing new is asked of the site until
# somebody asks for it.
_FIGURES_DEFAULT = {'battle': 'both'}

# A Twitch login: what a channel name may be.
_TWITCH_CHANNEL = re.compile(r'^[a-z0-9_]{3,25}$')

# Kinds of battle, as modes.py tells them apart from the arena's bonus type.
MODES = ('random', 'ranked', 'onslaught', 'stronghold', 'frontline', 'training', 'other')

# Where a rating shows unless the player says otherwise: contact rows and the
# profile title are names first.
_RATED_BY_DEFAULT = ('skirmishRoom', 'battle', 'stronghold', 'battleResults')

def _surface(surface):
    values = {'flags': True, 'rating': surface in _RATED_BY_DEFAULT}
    if surface in AVERAGED:
        values['average'] = True
    if surface in FIGURED:
        values['figures'] = _FIGURES_DEFAULT.get(surface, 'career')
    return values

DEFAULTS = dict({
    'enabled': True,
    'metric': 'wnx',
    'window': 'recent',
    # Shown wherever a rating is shown, in the order rating, win rate,
    # battles. Deliberately not a per-surface switch: every surface already
    # chooses among four combinations of rating and flags, and folding two
    # more things in would make sixteen.
    'battles': 'total',
    'winrate': 'total',
    # A tenth of a point on a win rate is noise at a glance, and the badge is
    # two characters wider for it. Off, and there for whoever disagrees.
    'winrateDecimal': False,
    'maxFlags': MAX_FLAGS,
    'tankButton': True,
    # The entries added to the game's own right-click menus, one switch for the
    # menus about a player and one for those about a tank. Separate because
    # they are wanted separately: a player who reads ratings in battle has no
    # use for the tank ones, and the tank menus reach into the tech tree and
    # the shop where a player menu never goes.
    'contextMenu': {'players': True, 'vehicles': True},
    # Whether this client tells unicum.gg how the player has set their
    # vehicles up, which is what puts a loadout on their own player page. On
    # by default and stated in the mod's description: Wargaming publishes none
    # of this, so nothing is here that the player's own client did not send,
    # and the pages are the poorer for every client that stays quiet.
    'sendLoadouts': True,
    # The battles this client played are always sent, whether the mod is on
    # or off: there is no box for them, and `enabled` turns off what the mod
    # draws, not this. They are what the site is built on (Wargaming
    # publishes none of them, and a battle exists on unicum.gg only because
    # somebody who was in it sent it), and a player who wants them out of
    # sight has a switch that does that without taking them away from
    # everybody else: hiding the battle list on their own page, which the
    # site owns (`hideBattles` in the settings window, not a value here).
    # It was a ticked box first, and a box that turns the uploads off is a
    # box that empties the site one cautious player at a time.

    # The `.wotreplay` the client already writes, on top of the result.
    #
    # Kept apart from the battles because it is not the same promise: a
    # result is numbers those thirty players each read on their own results
    # screen, while the file is everything this client saw, the battle chat
    # included. Folding it into the battles would break what they carry: the
    # numbers alone, no chat and no replay.
    #
    # On, for the reason the battles are sent: a box nobody ticks collects
    # nothing, and one client sending is enough for all thirty. What that
    # costs in candour is paid in the tooltip, which says plainly that the
    # chat goes too.
    'sendReplays': True,
    # Off, and meant to be turned on only to answer a question. It times what
    # the mod does on the thread that draws the game and writes a table to the
    # log every few seconds, so "the mod costs me frames" can be measured
    # instead of argued about. Costs a clock read per call while it runs.
    'measurePerformance': False,
    # Off until the player turns it on: it writes in the team chat for them.
    # Never, after every shot, or only when an autoloader's magazine runs out.
    'autoReload': 'off',
    # Ratings shown only while the extended info key (Alt) is held: the battle
    # ones, and the skirmish room, which is the one outside a battle.
    'altOnly': {'markers': False, 'panel': False, 'tab': False, 'loading': False, 'results': False,
                'skirmishRoom': False, 'stronghold': False, 'minimap': False},
    # `battle` is where the Twitch chat shows in battle, a checkbox before it
    # was a choice: 'chat' is the True it used to be. `battlePosition` is
    # where the player dragged the chat window in battle, which is its own
    # place: the garage's is under the mission column, and in battle that
    # corner is the minimap's.
    # `panelText` and `battleText` are how big the chat is drawn where it is
    # read. Two settings rather than one because they are two renderers, not
    # two places: the panel is the same panel in the garage and in the window
    # over a battle, and the battle chat is the game's own.
    'twitch': {'channel': '', 'battle': 'chat', 'garage': True, 'garageCollapsed': False,
               'garagePosition': None, 'garageSize': None, 'battlePosition': None,
               'panelText': 'normal', 'battleText': 'normal'},
    'modes': dict((mode, {'allies': True, 'enemies': True}) for mode in MODES),
    # What the minimap writes beside a vehicle: the client's own choice (the
    # vehicle), the player, or both. 'vehicle' leaves the client alone.
    'minimapNames': 'vehicle',
}, **dict((surface, _surface(surface)) for surface in SURFACES))

# What is announced: nothing, every reload, or only an autoloader's.
RELOAD_CHOICES = ('off', 'all', 'magazine')

# What the minimap labels a vehicle with.
#
# `vehicle` is the client untouched: it writes the vehicle name, or nothing,
# according to the game's own minimap setting. The other two replace that label
# or add to it, and only where the client was already going to write something,
# so turning the game's labels off still turns ours off.
MINIMAP_NAME_CHOICES = ('vehicle', 'player', 'both')

# Where the Twitch chat shows in battle. 'chat' is the battle chat carrying
# the messages, which is what the checkbox this replaces did; 'window' is the
# chat window of the queue screen, kept up over the battle; 'both' puts every
# message in both places.
BATTLE_CHAT_CHOICES = ('off', 'chat', 'window', 'both')

# The steps the chat's text size offers. 'normal' is what both renderers have
# always drawn, and both are written so that it changes nothing at all: the
# panel adds no class and the battle lines carry no size of their own.
TEXT_SIZE_CHOICES = ('small', 'normal', 'large', 'larger')

# What the panel can be dragged to, in rem: wide enough for a name and a line
# of chat, and never larger than a big screen, whatever a hand-edited file says.
MIN_PANEL = (220, 120)
MAX_PANEL = (1600, 1200)

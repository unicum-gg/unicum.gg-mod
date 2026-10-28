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

METRICS = ('wn7', 'wn8', 'wnx')
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
    # Whether this client tells unicum.gg about the battles it played: the
    # map, the mode, and what each of the thirty vehicles did. On by default
    # and stated in the mod's description, for the reason the loadouts above
    # are: Wargaming publishes none of this, so a battle on the site exists
    # only because somebody who was in it shared it.
    #
    # This was off at first, on the grounds that a loadout describes the
    # player's own garage while a battle describes twenty-nine other people
    # too. That argument is real but it loses to two others. A box nobody
    # ticks collects nothing, so off is not a cautious version of this
    # feature, it is the absence of it. And a battle names all thirty players,
    # so each client that speaks covers thirty: off never lets that
    # multiplier start. What is sent is also the thinner half of the two --
    # numbers every one of those thirty already read on their own results
    # screen, no chat, no replay, nothing about what anyone owns. The replay
    # file is `sendReplays`, below, and not this.
    'sendBattles': True,
    # The `.wotreplay` the client already writes, on top of the result.
    #
    # Kept apart from `sendBattles` because it is not the same promise: a
    # result is numbers those thirty players each read on their own results
    # screen, while the file is everything this client saw, the battle chat
    # included. Folding it into the existing box would have contradicted that
    # box's own tooltip, which says "no chat, no replay" in as many words.
    #
    # On, for the reason `sendBattles` is on: a box nobody ticks collects
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
    'twitch': {'channel': '', 'battleChat': True, 'garage': True, 'garageCollapsed': False,
               'garagePosition': None, 'garageSize': None},
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

# What the panel can be dragged to, in rem: wide enough for a name and a line
# of chat, and never larger than a big screen, whatever a hand-edited file says.
MIN_PANEL = (220, 120)
MAX_PANEL = (1600, 1200)

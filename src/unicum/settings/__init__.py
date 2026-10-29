"""What the player chose to see: one rating, and where it and the flags show.

mods/configs/unicum/settings.json is the one source of truth. It is written
with the defaults on first start, can be edited by hand while the client runs
(it is checked every second), and is all the mod needs: no other mod is
required. When izeberg's modsSettingsApi is installed, settings_window/
also shows these settings in its window, and writes back here.

    {"enabled": true, "metric": "wnx", "window": "recent", "maxFlags": 3, "tankButton": true,
     "autoReload": false, "twitch": {"channel": "", "battle": "chat"},
     "contacts": {"flags": true, "rating": false},
     "battle": {"flags": true, "rating": true, "average": true}, ...,
     "modes": {"random": {"allies": true, "enemies": true}, "ranked": {...}, ...}}

One rating for the whole mod, so the same number means the same thing on
every screen. Each surface only switches its flags, its rating and, in the
skirmish room and the battle, the average on and off. tankButton is the
unicum.gg button in the hangar's vehicle menu.

In battle, `modes` says per kind of battle (see modes.py) whose ratings and
flags show at all: the allies', the enemies', both or neither, whatever the
battle surface itself shows. autoReload sends the "Reloading!" chat command
by itself after a shot (see auto_reload.py). twitch names the player's Twitch
channel, whose chat shows in the battle chat (see twitch.py); left empty, the
channel linked to their account on unicum.gg is used.

Every change reaches the surfaces through on_change(), and each surface
redraws what it has on screen, so nothing needs a restart.
"""

from __future__ import absolute_import

from unicum.settings.defaults import (AVERAGED, BATTLE_CHAT_CHOICES,
                                      DEFAULTS, EXTRAS,
                                      MAX_FLAGS, MAX_PANEL, METRICS,
                                      MIN_PANEL, MINIMAP_NAME_CHOICES,
                                      MODES, RELOAD_CHOICES, STORE,
                                      SURFACES, WINDOWS)
from unicum.settings.store import Settings
from unicum.settings.validating import (panel_size, twitch_channel,
                                        validate)

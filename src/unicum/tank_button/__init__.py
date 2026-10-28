"""A unicum.gg button in the hangar's vehicle menu, with links for the tank.

The row of hexagons above the crew is Gameface, so the button is a module of
our own (res/gui/gameface/mods/unicum/TankButton/) that openwg_gameface
injects into the hangar, the way skill4ltu adds its own button there:

  res_map   res/mods/configs/res_map/unicum.json declares the layout
            UnicumTankButton; openwg_gameface adds it to the client's
            resource map at startup and restarts the client once when the
            map changes
  view      a child of VehicleMenuPresenter, added through its
            _getChildComponents, with a model that carries the injection
            (gf_mod_inject), the onItemClick command, and the menu's code
  code      the injected TankButton.js only loads web/hangar/tank_menu.js
            and .css, which this module puts in the model and puts again
            when either changes on disk: the menu hot reloads like the rest
  click     the button opens a menu; an entry opens its link in the player's
            browser

Links go to https://unicum.gg/<region>/tanks/<intCD>[/<tab>]: the site
redirects an id to the tank's page, keeping the path and the query. Each
carries UTM parameters, since a page opened from another application has no
Referer. "Open build" adds the vehicle's setup as the site's `setup` token
(build.py); "Share build" copies that link instead of opening it, tagged
apart so a shared link's visits can be told from the player's own. The AI
entries do what the site's own "Open in" menu does
(apps/web/src/components/page-ai-actions.tsx in unicum-gg/unicum.gg): every
page has a Markdown twin at <path>.md, and the model is handed that, with the
setup too, which the twin renders.

The same loader runs the garage's Twitch chat panel and the unicum.gg
account card above it (twitch_panel.py): their scripts and styles are put in
the model after the menu's, each script wrapped in a function of its own, and
their state rides in the model's `twitch` string.

Optional: without openwg_gameface, or before the client has restarted with
the layout in its resource map, there is no button and nothing else changes.

A hangar view outlives a reload of this package, so the command's handler
holds no code of it: like mods_list.py, it is eval of a string importing the
current module at click time, with the command's arguments as its locals.
Its models are kept on VehicleMenuPresenter for the same reason: a reload
finds the buttons already on screen and gives them the current code.
"""

from __future__ import absolute_import

from unicum.tank_button.button import FEATURE, LAYOUT, TankButton
from unicum.tank_button.button import (panel_code, panel_sources,
                                        set_twitch)
from unicum.tank_button.sharing import compose, on_item
from unicum.tank_button.urls import (SITE_BASE, TABS, item_url,
                                     markdown_url, player_url,
                                     support_url, tank_url)


def install(session, settings):
    TankButton(session, settings).install()

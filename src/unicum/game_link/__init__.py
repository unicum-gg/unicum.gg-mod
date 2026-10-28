"""The link between this client and the player's unicum.gg account.

It lets the mod act for the player where that needs their account: today,
writing in their Twitch chat (see twitch_send.py). Nothing is typed.

Linking opens the player's own browser (BigWorld.wg_openWebBrowser) on
unicum.gg's /api/connect/game/<hash>#account_id=...&token=..., where the
fragment carries the game's WGNI web token. The game's built-in browser cannot
be used: it only opens the domains Wargaming's servers list (wargaming.net,
worldoftanks.eu...) and refuses any other with a 418 before a request is made.
On that page unicum.gg starts its Wargaming sign-in and sends the browser
through Wargaming's token sign-in, the one the client uses to open the shop
signed in, on to the OpenID page: signed in already, one confirmation screen
at most. It then links the account and, when Twitch is not linked with the
chat scope yet, goes on to Twitch, where the player's browser is usually
signed in too. A fragment never reaches a server, so the token goes from the
game to Wargaming without passing through unicum.gg.

The mod draws a random secret and sends only its SHA-256 along that chain.
Once the site has linked the hash, the secret is the mod's bearer token; the
mod learns that by polling GET /api/game/me with it. The secrets live in
mods/configs/unicum/account.json, one per Wargaming account the game has been
linked on, and nowhere else.
"""

from __future__ import absolute_import

from unicum.game_link.link import GameLink
from unicum.game_link.proof import (ME_PATH, STORE, TWITCH_READY, bearer,
                                    connect_url, current_account_id,
                                    new_secret, read_me, read_privacy,
                                    read_store, secret_hash)

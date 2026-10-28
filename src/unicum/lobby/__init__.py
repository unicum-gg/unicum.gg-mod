"""Marks contacts with where each player comes from.

ContactConverter.makeBaseUserProps builds the `region` field of every row in
the contacts list, and that row is drawn as htmlText -- the client injects
its own status icon into the same props through makeHtmlString.

The obvious hook was LobbyContext.getRegionCode, one function feeding every
surface that shows a region. It reached too far. That value is also spliced
into flat strings for plain text fields, and the profile window title came
out reading

    Seif_Sahbouch [YONQO] <IMG SRC="img://gui/maps/.../FR.png" .../>

Markup in a shared data accessor is a bet on every consumer rendering HTML,
and that bet loses. So the patch sits on the presentation layer instead: one
per surface, each one somewhere markup is known to be honoured.

This is also where the contacts list showed that resolving every id it knows
about is not free: it asked for 3293 players at once, which is why the API
client batches.
"""

from __future__ import absolute_import

from unicum.lobby.flags import LobbyFlags


def install(session, lookup, flags, badges, settings, alt=None):
    LobbyFlags(session, lookup, flags, badges, settings, alt).install()

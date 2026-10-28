"""How the player has set their vehicles up, sent to unicum.gg.

Wargaming publishes none of this about anyone: their API answers battles and
damage, never the equipment on a gun or the perks a commander trained. So a
loadout on a player's page exists only because that player runs this mod, and
this module is the whole of that path.

What it sends, and what proves it
---------------------------------
Only ever this account's own vehicles, and the account is PROVEN rather than
claimed. The client can mint a WGNI web token, the one the game uses for its
own shop and portal, without asking the player anything; unicum.gg hands it to
Wargaming, which answers with the account id it is bound to. A nickname in the
body would be a claim, and the value of a published loadout rests entirely on
nobody being able to invent builds under a good player's name.

Why it sends so little
----------------------
A full carousel is a few hundred vehicles and about a quarter of a megabyte,
of which almost nothing moves between two garage visits. So the mod keeps a
fingerprint per vehicle and sends only what changed, reconciled against what
the server says it already holds, which makes the steady state nearly free and
leaves the whole payload for the first upload alone.

Measured on a 209-vehicle garage: 0.15 seconds of client time to read the lot,
1231 bytes a vehicle. The reading is not the cost here, the sending is.

When it runs
------------
At the garage and nowhere else: never in battle, never while the client is
starting. A moment after the garage appears, and again whenever the player
changes something, which is the half that was missing at first. Hanging it on
the garage alone meant somebody who spent an hour rebuilding tanks sent
nothing until they next came back from a battle, so their own page kept
showing a build they had already replaced.
"""

from __future__ import absolute_import

from unicum.loadouts.uploader import Uploader


def install(session, settings, link):
    uploader = Uploader(session, settings, link)
    uploader.install()
    return uploader

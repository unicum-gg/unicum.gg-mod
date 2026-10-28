"""The garage's Twitch panel where the garage is gone: the battle queue and loading screens.

The panel lives in the hangar's Gameface view (twitch_panel.py), and queueing
for a battle replaces the hangar with the queue screen, a Scaleform view: the
panel went with it, and a streamer watching the queue for minutes lost their
chat. So while the queue screen is up, the panel is opened again in a window
of its own, the same code (web/hangar/twitch_panel.js and .css) with the same
state, at the same place and the same size, folded if it is.

The battle's loading screen is the same story, in the battle app: the window
opens as soon as the player is in the battle (onAvatarBecomePlayer), the
battle's main window loaded, and closes when the game moves from the
loading screen to the battle page (GameEvent.BATTLE_LOADING, whose isShown
says which), after which the battle chat carries the Twitch messages as
before. Opening before the screen shows matters: while the map loads, the
page takes seconds to be drawn, and a loading screen can last only four.
In battle the window sits on the OVERLAY layer, the one that stays above the
battle's interface.

The window is a Gameface view of our own, UnicumTwitchWindow
(res/gui/gameface/mods/unicum/TwitchWindow/, declared in
res/mods/configs/res_map/unicum.json, so openwg_gameface restarts the client
once to add it), in a Wulf window the panel's size: a window as large as the
screen would take every click from the queue screen under it. It sits on the
WINDOW layer, above the queue screen and under the game's own menus, and
opens without taking the keyboard.

Its model carries the panel's code (`script`, `style`, `revision`, reloaded
when the files change, as the tank button's) and state (`twitch`, the
garage's JSON), and its onItemClick brings back what the player does, handed
to the garage panel's own handler: the window sends, folds, connects and
closes the way the garage does. Where it goes is the garage panel's last
report (twitch_panel.panel_rect), in the hangar's pixels, turned into the
window system's units by the main window's size; how large, the panel's size
in rem from that report.

Moved, resized or reset, the window does what the panel does in the garage,
and saves the same settings (twitchMove, twitchResize in rem), so each finds
the other where the player left it. The page cannot follow a mouse that
leaves it, so a press on the header or the corner only starts the gesture
(twitchWindowDrag, twitchWindowResize), and Python follows the cursor every
frame until the button is up, the way the known-good Gameface overlays do:
the window moves with it, or the panel is given its new size, which the
page then gives the window. A press on the header that does not move folds
the panel, as a click does in the garage.

The chat must never seem to leave the screen, so the window opens early
and closes late, and for a moment covers the garage panel, which it draws
exactly like, pixel for pixel. It opens when the server puts the player in
a queue (onEnqueued), before the lobby even moves to the queue screen, and
stays while the lobby's visible route is a battle queue. Once the lobby
leaves it, the window stays on until the garage panel is on screen again,
which its first report of where it is says (twitch_panel.panel_reports),
up to a few seconds; the hangar's Gameface takes a second or two to come
back. A battle found (onArenaCreated) leaves it on the queue screen, which
stays a moment longer, then closes it as soon as the lobby leaves the queue,
without waiting: the battle's loading must not have a lobby window over it.
The lobby's window only in the lobby, the battle's only on its loading screen.

Two panels on top of each other would show darker than one, their veils
added. So the two hand over: once the window is drawn, the garage panel
hides under it (twitch_panel.set_covered); once out of the queue, the
garage panel shows again, and its first report closes the window at once
(twitch_panel.set_report_hook) rather than on the next tick.

A tick does the rest: the state, the code, the place, and the route again
should an event be missed.

The page tells its size once it is laid out (twitchWindowSize), which is
also the sign it is ready: until then only its first state, given at
creation, reaches it.
"""

from __future__ import absolute_import

from unicum.twitch_window.window import TwitchWindowHost


def install(session, settings, chat, link):
    TwitchWindowHost(session, settings, chat, link).install()

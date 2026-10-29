"""Messages from the player's Twitch chat, shown in the battle chat.

Read-only and anonymous: Twitch's chat is IRC over a WebSocket
(wss://irc-ws.chat.twitch.tv), where a `justinfanNNNN` nick joins a channel
without an account and receives what is said there. The connection goes
through the client's own WebSocket (the `websocket` package over the native
`_websocket`), whose callbacks come on the game's thread: nothing here blocks
or needs a thread of its own.

In battle, each message goes to the battle chat with
MessengerEntry.gui.addClientMessage, the way the client shows its own notices
there: only on this screen, never sent to anyone. Outside a battle messages
are kept, a few at a time, for a garage view to come.

A battle opens with the last of them rather than with an empty chat, so what
was said while the player sat in the garage or waited out the loading screen
is still there to read (`ChatQueue.open_battle`).

settings.json: {"twitch": {"channel": "", "battle": "chat"}}, where `battle`
says where the chat shows once a battle starts: in the battle chat, in the
window over the battle (twitch_window/), in both, or nowhere. With no
channel typed there, the one the player linked to their account on unicum.gg
(`twitchLogin` of GET /api/{region}/players/{nickname}) is followed. No
channel either way, no connection.
"""

from __future__ import absolute_import

from unicum.twitch.chat import TwitchChat


def install(session, settings, link=None):
    chat = TwitchChat(session, settings, link)
    chat.install()
    return chat

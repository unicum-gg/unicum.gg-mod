"""Sending the battle's own `.wotreplay` file, when the client kept one.

Why a file at all
-----------------
`motion.py` already samples every vehicle five times a second, and that is what
the site draws: 64 KB against this file's 1.3 MB. So the file is not how a
battle gets replayed. It is insurance for a 3D view nobody has built yet, which
would want shell trajectories, the geometry of each hit and the state of the
destructible terrain. None of that can be collected after the fact, and a
battle played today is the only chance to have it.

Why it has to be copied aside
-----------------------------
**The file is volatile.** `BattleReplay.enableAutoRecordingBattles` is 1 by
default, which calls `setResultingFileName(FIXED_REPLAY_FILENAME, True)`: every
battle is written to `replays/replay_last_battle.wotreplay` and **overwrites
the one before it**. A player who queues up again while an upload is in flight
destroys the thing being uploaded. So the file is copied into our own folder at
the garage, and the upload reads the copy.

Players who set recording to "all" get a descriptive name per battle instead,
and nothing is overwritten. Both are handled by looking the file up by the
battle id inside it rather than by trusting any name.

Why base64
----------
The body goes out through `BigWorld.fetchURL`, whose `postData` the game itself
never uses with anything but text, and whose binary safety is documented
nowhere. A replay is full of zero bytes. If that path is not binary-safe the
failure is a file truncated at the first one, which still has a valid header
and still names the right battle, and would be archived silently broken. 33% on
the wire, once per battle, buys certainty instead. The SHA-256 that rides along
catches the other half of the problem: a body cut short in transit.
"""

from __future__ import absolute_import

from unicum.replays.uploader import Uploader


def install(session, settings, link):
    uploader = Uploader(session, settings, link)
    uploader.install()
    return uploader

"""The battles this client played, sent to unicum.gg.

Wargaming's API publishes an account's running totals and nothing whatever
about a single battle: not who was in it, not what each of them did, not which
map or which cluster. So a battle on unicum.gg exists only because somebody
running this mod was in it, and this module is the whole of that path.

Where the numbers come from
---------------------------
The client's own battle results, handed to us by the game. Not a .wotreplay:
recording is a player setting, and new accounts do not get it at its highest,
so reading files would quietly collect from a subset of players and call it the
playerbase. The results arrive in every client, for every battle, whatever that
setting says.

Read by patching `BattleResultsService.postResult`, which receives the raw
dictionary the server sent. **Not `onResultPosted`**, which was the first
attempt: that event hands over a stats controller, and only the Gameface one
(`RandomBattleResultStatsCtrl`) implements `getResults`. Every Flash mode --
Ranked, CyberSport, Stronghold, Maps Training, and the fallback any bonus type
we have not met lands on -- inherits `IBattleResultStatsCtrl.getResults`, which
returns None. Those modes would have reported nothing at all, and said so in
the log as if the extractor had refused them. `postResult` is upstream of every
composer, so it is the one place that sees all of them.

The raw dictionary is the same structure a replay carries in its second block,
which is how the extractor below could be measured against 1913 real battles
before it ever ran in the client. What the dictionary does NOT carry is the
map's name, the gameplay and the client version: those live in a replay's meta
block, not in the results, so they are read from the client here and passed in.

What one battle costs
---------------------
Measured over 1913 real battles: 10.2 KB of JSON for a thirty-vehicle random
battle, 4.9 KB for a fourteen-vehicle skirmish, 20.8 KB for a sixty-vehicle
Frontline. Against a 1293 KB replay of the same battle, which is the reason
this is what gets sent rather than the file.

One battle, any sender
----------------------
A battle names all thirty of its players, so it reaches the server from
whichever participant happens to run the mod, and the id it is keyed by is a
deduplication key rather than an ownership one: the second sender of a battle
is answered "already known" rather than refused. Coverage grows by whole teams.

When it sends, and what it is allowed to forget
-----------------------------------------------
Appended to a file the moment the results land, sent from the garage. Appended
rather than rewritten because this runs on the thread that draws the game: one
battle is a 10 KB line, where rewriting a full queue was 44 ms and three
dropped frames, landing exactly on the results screen's animation.

**A battle leaves the queue only when the server names it.** The answer lists
ids, never counts, and that is load-bearing: the queue is the only copy of a
battle not yet stored, and a count cannot be acted on, so a client reading
counts had no choice but to drop the whole batch on any answer it could not
make sense of -- including an HTML error page served with a 200.
"""
# Python 2 resolves an unprefixed import inside a package by looking in the
# package FIRST, and this module imports `battle_results` from the client while
# `unicum/battle_results.py` sits right beside it. Without this line that
# import quietly found our own module, failed to find the client's constant in
# it, and `_is_battle_results` answered False to every announcement ever sent:
# a feature that shipped doing nothing at all. The client's own modules carry
# the same line for the same reason.

from __future__ import absolute_import

from unicum.battles.reporter import Reporter


def install(session, settings, link, motion=None, replays=None):
    reporter = Reporter(session, settings, link, motion, replays)
    reporter.install()
    return reporter

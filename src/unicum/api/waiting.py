"""Callers waiting for answers that are already on their way.

The lookup's `on_ready` means "everything you asked about has been answered".
Getting that right needs one distinction: what a call had to FETCH and what it
asked ABOUT are not the same set, because somebody else may be fetching the
rest of it right now.

The difference had a face. The Stronghold detachment list asked about fifteen
nicknames forty-seven milliseconds after the preview panel had asked about the
same fifteen. Nothing was left to fetch, so nothing was sent, so `on_ready`
fired at once, a hundred and fifty milliseconds before the answer landed. A
detachment of fifteen rated players was drawn as "nobody here can be rated"
and stayed that way for a minute, until a retry put it right.

In flight is not in hand.

Split out of `resolve.py` when that module went past the size this repo holds
its modules to.
"""
from __future__ import absolute_import


class Waiters(object):
    """Who is waiting on which keys, and who can be told now.

    `in_flight` is the lookup's own set, held rather than copied: it is
    mutated in place as requests go out and come back, and this reads it at
    the moment it is asked.
    """

    def __init__(self, in_flight):
        self._in_flight = in_flight
        self._waiting = []

    def wait(self, keys, on_ready):
        """Call on_ready now, or once nothing in `keys` is in the air."""
        if on_ready is None:
            return
        waiting = set(key for key in keys if key in self._in_flight)
        if not waiting:
            on_ready()
            return
        self._waiting.append((waiting, on_ready))

    def release(self):
        """Everyone whose answers have all landed, told once."""
        ready = []
        still = []
        for waiting, on_ready in self._waiting:
            if waiting & self._in_flight:
                still.append((waiting, on_ready))
            else:
                ready.append(on_ready)
        # Put back before anyone is called: an on_ready that asks for more
        # lands in the new list rather than in the one being walked.
        self._waiting = still
        for on_ready in ready:
            on_ready()

"""The captured battles waiting on disk, until a destination takes them.

A battle that fails to send cannot be played again. The client can be closed
between two battles, or be offline for a whole session, and a season's standing
is computed from counters that must have no holes. So a capture lands here
first, and sending reads from here.

Held in memory as well as on disk: a capture happens on the frame the results
arrive on, and reading a file there is work the player would feel.
"""
import json
import logging
import os

_logger = logging.getLogger('unicum.report_queue')

# Beside the other things the mod keeps per installation rather than in the
# resource tree: plain data, plain file I/O.
STORE = os.path.join('mods', 'configs', 'unicum', 'battle-reports.json')

# The contract version the reports are written in. It travels with them on
# disk, so a queue written by an older mod is recognised rather than guessed at.
SCHEMA = 1

# How many captures the queue holds. A ranked evening is a few dozen battles,
# so this covers a player offline for days. Past it the OLDEST go: a destination
# scoring this week's tournament wants this week's battles, and a queue that
# refused new ones would silently stop capturing instead.
LIMIT = 500


def trim(reports, limit=LIMIT):
    """The queue, oldest dropped first, down to the limit."""
    if len(reports) <= limit:
        return reports
    return reports[len(reports) - limit:]


def deduplicate(reports):
    """The queue with one report per arena, the first kept.

    A battle can reach the capture twice -- the client posts a battle's results
    again when an older one is opened from the notification centre -- and a
    counter that added it twice would credit score nobody earned. Destinations
    dedupe as well, by (player, arena); this only keeps the queue from carrying
    work already known to be redundant.
    """
    seen = set()
    out = []
    for report in reports:
        arena_id = report.get('arena_unique_id')
        if arena_id in seen:
            continue
        seen.add(arena_id)
        out.append(report)
    return out


class Queue(object):

    def __init__(self, store=STORE):
        self._store = store
        self._reports = self._read()

    def _read(self):
        try:
            with open(self._store, 'rb') as handle:
                payload = json.load(handle)
        except (IOError, OSError):
            return []
        except ValueError:
            # A truncated file, from a client killed mid-write. The battles in
            # it are gone either way; keeping the broken file would only stop
            # every capture after it.
            _logger.warning('the battle report queue was unreadable, starting a new one')
            return []
        if not isinstance(payload, dict) or payload.get('schema') != SCHEMA:
            return []
        reports = payload.get('reports')
        if not isinstance(reports, list):
            return []
        return [report for report in reports if isinstance(report, dict)]

    def all(self):
        return list(self._reports)

    def add(self, report):
        """Queue one report, and say whether it was new."""
        before = len(self._reports)
        self._reports = trim(deduplicate(self._reports + [report]))
        if len(self._reports) == before and before:
            return False
        self.save()
        return True

    def pending(self, key, modes):
        """The reports this destination wants and has not been given yet."""
        wanted = set(modes)
        return [report for report in self._reports
                if report.get('mode') in wanted and key not in (report.get('sent') or [])]

    def mark(self, key, arena_ids):
        """Remember that a destination has taken these, whatever its verdict.

        Accepted, duplicate and rejected are all final answers, so all three
        mean the same thing here: this destination is done with the report.
        Retrying a rejection would only ask the same question again.
        """
        taken = set(arena_ids)
        if not taken:
            return
        for report in self._reports:
            if report.get('arena_unique_id') not in taken:
                continue
            sent = report.get('sent')
            if not isinstance(sent, list):
                sent = report['sent'] = []
            if key not in sent:
                sent.append(key)
        self.save()

    def settle(self, owed):
        """Drop every report that each destination owed it has taken.

        `owed` answers, for a mode, which destinations are waiting for it. A
        report nobody is waiting for goes too: the player turned a destination
        off after the battle was captured, and keeping it would leave a copy of
        their play history on disk for no one to read.

        Deliberately not "delivered to whoever wanted it when it was captured".
        A destination that is switched off, or whose secret was revoked, would
        otherwise pin the whole queue open behind it for good.
        """
        kept = [report for report in self._reports
                if set(owed(report.get('mode'))) - set(report.get('sent') or [])]
        dropped = len(self._reports) - len(kept)
        if dropped:
            self._reports = kept
            self.save()
        return dropped

    def drop(self, arena_ids):
        """Forget these reports outright, whoever may still be waiting."""
        taken = set(arena_ids)
        if not taken:
            return
        self._reports = [report for report in self._reports
                         if report.get('arena_unique_id') not in taken]
        self.save()

    def save(self):
        try:
            directory = os.path.dirname(self._store)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            with open(self._store, 'wb') as handle:
                json.dump({'schema': SCHEMA, 'reports': self._reports}, handle)
        except (IOError, OSError):
            _logger.debug('could not write the battle report queue', exc_info=True)

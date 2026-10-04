"""Battle results captured as they arrive, for the destinations that want them.

Wargaming's public API answers lifetime and recent statistics for random
battles, and has stopped refreshing some of the other modes: ranked has been
frozen there for weeks. A site scoring a ranked season from that API reads the
same numbers every day. The results themselves are not gone, they are in the
client, which is where this reads them.

What is here, and what is not
-----------------------------
Where a battle is captured from and when. Reading one out of the results dict
is `battle_report.py`, and finding that dict on whatever the client hands over
is `results_dict.py`. The three fail for unrelated reasons: where to sit was
wrong twice on a real client while every reading was right, and once the
capture was attached it was a misread key that dropped every battle.

Waiting here is not enough, so the mod also asks
------------------------------------------------
Nothing in **this module** captures a battle whose results screen the player
never opens. That is measured rather than suspected: five ways in were tried
and timed against a real client, and the battle stayed missing quietly -- a
rating computed from nine battles out of ten looks like a rating, not like a
fault. What captures it is the ask, below.

  - `g_playerEvents.onBattleResultsReceived`, subscribed and never fired;
  - `IBattleResultsService.onResultPosted`, fires as the screen is built;
  - `postResult`, the same moment;
  - `waitForBattleResults`, never called at all;
  - `requestResults`, called with no arena because a probe read the arguments
    of its decorator rather than its own: it ran, and nothing came of it.

The results are simply not in the client until something asks the server for
them, and nothing that merely waits will do. `results_request.py` is the ask,
and it is why the last line above is a mistake rather than a dead end: that
call does take an arena, and a client told which battle it is about answers.

The ask works, and on three modes now. Measured on a 2.4.0.2 client, each time
a battle whose results screen was never opened, announced, asked for and
answered:

    2026-10-03   an "other" battle      type 160                      409ms
    2026-10-04   a random battle        type 2,   battleResults        469ms
    2026-10-04   an onslaught battle    type 157, comp7BattleResults   582ms

Two things had to be right that were not obvious -- the announcement arrives
on the mode's own message type rather than on `battleResults`, and the arena
id it carries is what the server will answer about. Both are written where
they are read, in `results_request.py`. The three numbers above are what that
first point costs to get wrong: a filter watching only `battleResults` hears
the random battle and nothing else.

The onslaught measurement also showed the three ways in racing, which is the
case worth having seen: the account hook delivered that battle 0.46s after it
was announced, the ask answered 1.6s later, and `postResult` 8s after that
when the screen was opened by hand. One report came out of it. The queue keeps
one per arena, so whichever way arrives first wins and the others cost nothing.

The three hooks here stay. They are the shortest path for a battle whose
results the player does open, they cost nothing when the ask has already
captured it -- the queue keeps one report per arena -- and if the ask ever
stops working for a mode they are what still captures something. That is also
why the player-facing instruction to open a results screen survives as a
remedy for a missing battle rather than as a requirement for every one.

What leaves the client
----------------------
Post-battle numbers only, never anything about a battle in progress. That is
what keeps this on the right side of Wargaming's fair play rules, and it is a
property of where the hook sits rather than a promise in a document: at the
moment this runs, the battle is over.

Where a capture goes
--------------------
Straight to disk, in `report_queue.py`: a battle that fails to send cannot be
played again, and the client can be closed between two battles or be offline
for a whole session. Sending reads from that queue, never from here, and lives
in `report_sender.py`: everything that can fail belongs where failing again
later is free, not on the frame the results arrive on.
"""
import logging

from unicum import service_hooks
from unicum.battle_report import missing_metrics, own_vehicles, report_of, why_not
from unicum.report_queue import Queue
from unicum.results_dict import describe, raw_results

_logger = logging.getLogger('unicum.battle_reports')


class BattleReports(object):
    """Captures a battle's results the moment the client has them."""

    def __init__(self, session, settings, queue=None, destinations=None, link=None):
        self._session = session
        self._settings = settings
        self._queue = queue if queue is not None else Queue()
        self._destinations = destinations
        self._link = link

    def install(self):
        service = self._service()
        if service is None:
            _logger.info('no battle results service in this client, nothing captured')
            return
        # Both ways in, not the first that exists. The service's own event
        # fires as the results are posted, and patching `postResult` reaches
        # the same moment; either alone can be the one that is silent on a
        # given client, and an event that exists but never fires captures
        # nothing while reporting that it is installed. That is the one failure
        # this module must not have: what is drawn may be missed, what is
        # counted may not. Arriving twice costs nothing -- the queue keeps one
        # report per arena, which it has to do anyway because the client posts
        # a battle again when it is opened from the notification centre.
        installed = []
        # First, and the only one that does not depend on the player looking:
        # a live test played a battle without opening the results screen and
        # captured nothing, then captured it the moment the screen opened. Both
        # of the service's hooks fire as that screen is built. This one fires
        # when the server sends the results.
        installed += self._follow_arrival()
        event = getattr(service, 'onResultPosted', None)
        if event is not None and hasattr(event, '__iadd__'):
            self._session.subscribe(event, self._from_event)
            installed.append('onResultPosted')
        holder = type(service)
        if hasattr(holder, 'postResult'):
            self._session.patch(holder, 'postResult', self._wrap_post)
            installed.append('%s.postResult' % holder.__name__)
        # Said once, before the verdict: what this client offers to sit on.
        # Choosing where to sit has been a guess twice, and a name in the log
        # is what makes the next choice a reading instead.
        service_hooks.describe(service)
        if not installed:
            _logger.warning('found no way to follow battle results arriving; nothing is captured')
            return
        _logger.info('capturing battle results from %s', ' and '.join(installed))

    def _follow_arrival(self):
        """Sit on the account's announcement, in whichever shape it has.

        Two shapes carry this name, and nothing short of trying tells them
        apart: an event the account holds and hands subscribers, or a method
        the client calls. The surface probe cannot say which -- it reads a name
        -- and reading it wrong is what left the capture waiting on an
        announcement that was never going to reach it.

        Says which was taken, or that neither was there. A capture that follows
        nothing has to be loud about it: the alternative is a score quietly
        computed from the battles whose results the player happened to open.
        """
        account = service_hooks.account_events()
        if account is None:
            _logger.info('this client has no account events, so the arrival cannot be followed; '
                         'only a battle whose results are opened is captured')
            return []
        arrival = service_hooks.arrival_event()
        if arrival is not None:
            self._session.subscribe(arrival, self._from_account)
            return ['the account announcing %s' % service_hooks.ARRIVAL]
        holder = type(account)
        if callable(getattr(holder, service_hooks.ARRIVAL, None)):
            self._session.patch(holder, service_hooks.ARRIVAL, self._wrap_arrival)
            return ['%s patched on %s' % (service_hooks.ARRIVAL, holder.__name__)]
        _logger.warning('the account has no %s to follow, so only a battle whose results are '
                        'opened is captured; a battle queued straight into is lost',
                        service_hooks.ARRIVAL)
        return []

    def _wrap_arrival(self, original):

        def onBattleResultsReceived(account, *args, **kwargs):
            # The client's own call first, as everywhere else here.
            outcome = original(account, *args, **kwargs)
            self._from_account(*args)
            return outcome

        return onBattleResultsReceived

    @staticmethod
    def _service():
        try:
            from helpers import dependency
            from skeletons.gui.battle_results import IBattleResultsService
            return dependency.instance(IBattleResultsService)
        except Exception:
            _logger.debug('could not reach the battle results service', exc_info=True)
            return None

    def _wrap_post(self, original):

        def postResult(service, result, *args, **kwargs):
            # The client's own call first: a capture that raised must never be
            # the reason a player does not see their results.
            outcome = original(service, result, *args, **kwargs)
            self._on_posted(result, 'postResult')
            return outcome

        return postResult

    def _from_event(self, posted=None, *args):
        self._on_posted(posted, 'onResultPosted')

    def _from_account(self, *args):
        """The account's announcement, whatever order it carries its arguments in.

        The results are picked out of the arguments rather than read off a
        position: this event carries a flag before them on some clients, and a
        signature guessed wrong would hand the capture a boolean, lose every
        battle, and report itself installed while doing it.
        """
        for value in args:
            if raw_results(value) is not None:
                self._on_posted(value, service_hooks.ARRIVAL)
                return
        # Nothing among them was readable. The last argument is the likeliest
        # to have been meant as the results, and describing the wrong one is
        # how the right one gets found.
        self._on_posted(args[-1] if args else None, service_hooks.ARRIVAL)

    def arrived(self, results, source='unknown'):
        """Take results the mod asked for, as though the client had posted them.

        `results_request.py` reaches this: it asks the server for a battle the
        player never opened and hands over the answer. Through the same door
        as the client's own hooks, so one log line covers every way a battle
        can reach the queue and the mode and account checks cannot be skipped
        by whichever way it came.
        """
        self._on_posted(results, source)

    def _on_posted(self, posted=None, source='unknown'):
        # Said out loud, once per battle: without it, a capture that never ran
        # and a battle that was never played read the same in game.log, and
        # that ambiguity has already cost an evening.
        _logger.info('battle results arrived by %s', source)
        try:
            self.capture(raw_results(posted, on_miss=describe))
        except Exception:
            _logger.exception('could not capture a battle')

    def wanted(self, mode):
        """Whether anything is waiting for a battle of this mode.

        unicum.gg takes them all while the player leaves the switch on. An extra
        destination takes only the modes it asked for, so a site scoring ranked
        never receives a random battle.
        """
        if self._settings.sends_battle_reports():
            return True
        if self._destinations is None:
            return False
        return bool(self._destinations.wanting(mode))

    def anything_wanted(self):
        """Whether any battle at all would be kept, whatever its mode.

        Asked before the server is: fetching a battle that nothing is waiting
        for would be a request on the player's behalf for numbers thrown away
        the moment they arrive. Deliberately not per mode -- see `wanted` --
        because this answer cannot disagree with what the capture then does.
        """
        if self._settings.sends_battle_reports():
            return True
        if self._destinations is None:
            return False
        return bool(self._destinations.modes())

    def account(self):
        """The Wargaming account these battles belong to, as a string, or None.

        Read from the link, which follows the account the client is logged in
        with and holds on to it through a battle, where the avatar carries no
        database id.

        Stamped on the report at capture rather than read again when it is
        sent, because the two moments are not the same one: a queue survives
        the client being closed, and a battle credited to whoever happens to be
        logged in the next evening is a battle credited to the wrong player.
        """
        return getattr(self._link, 'account', None)

    def capture(self, results, constants=None):
        """Queue a battle's results, and say whether anything was queued."""
        if results is None:
            return False
        report = report_of(results, constants=constants)
        if report is None:
            # A warning, not a debug: nothing else says a battle went
            # uncaptured, and `results_dict` can hand us a dict that merely
            # carries a `common` key rather than the results themselves. The
            # keys are what tells those two apart from one log line.
            _logger.warning('a battle arrived that could not be described, skipped: %s. Keys: %s',
                            why_not(results),
                            ', '.join(sorted(str(key) for key in results)) or 'none')
            return False
        # Asked after the report is built, because the answer depends on the
        # mode, and cheap enough: a battle nobody is waiting for is not kept.
        # Keeping it "just in case" would be a copy of the player's play history
        # sitting on their disk for no one.
        if not self.wanted(report['mode']):
            return False
        account = self.account()
        if account is None:
            # Not queued: a report naming nobody cannot be attributed by any
            # destination, so it would sit on disk until the queue dropped it.
            # In practice unreachable -- the link keeps the account through a
            # battle -- which is exactly why it must not be guessed at.
            _logger.warning('a battle arrived with no account logged in, not captured')
            return False
        report['account'] = account
        if not self._queue.add(report):
            return False
        _logger.info('captured a %s battle, %d queued', report['mode'], len(self._queue.all()))
        absent = missing_metrics(own_vehicles(results.get('personal')))
        if absent:
            # Zeroes in the report either way, so this is the only place the
            # difference survives: a mode that grants no XP and a client that
            # renamed `xp` produce the same battle otherwise.
            _logger.info('the client reported no %s for it; those count as zero',
                         ', '.join(absent))
        return True


def install(session, settings, destinations=None, link=None, queue=None):
    reports = BattleReports(session, settings, queue=queue,
                            destinations=destinations, link=link)
    reports.install()
    return reports

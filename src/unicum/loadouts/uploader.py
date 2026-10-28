"""When to read the garage, and how much of it to read at once.

At the garage and nowhere else: never in battle, never while the client is
starting. A moment after the garage appears, and again whenever the player
changes something, which is the half that was missing at first. Hanging it on
the garage alone meant somebody who spent an hour rebuilding tanks sent
nothing until they next came back from a battle.

The sweep is in steps on purpose. Two hundred vehicles is 0.15 seconds of
client time, and the garage is already the busiest moment there is, so the
carousel is read a handful of vehicles at a time between frames.
"""
from __future__ import absolute_import

import logging
import time

from unicum import config
from unicum.loadouts.reading import entry_of, fingerprint, inventory, loadout
from unicum.loadouts.sending import Sending
from unicum.loadouts.store import (changed, demounted, load_marks_hash,
                                   load_sent, load_withdraw, marks_hash,
                                   save_sent, save_withdraw, uncrewed)

_logger = logging.getLogger('unicum.loadouts.uploader')

# Vehicles per pass, so a sweep never holds the frame the garage is drawn on.
_CHUNK = 25
_CHUNK_PAUSE = 0.1

# The least time between two sweeps.
#
# Four minutes rather than the quarter of an hour this was, because that
# quarter of an hour was the whole bug: a player who sat in the garage
# rebuilding tanks saw nothing reach their page until they next left it. A
# sweep with nothing to send costs no request at all (the fingerprints settle
# it locally), so what this really bounds is how often a CHANGE is uploaded,
# and fifteen an hour sits comfortably under the twenty the endpoint allows.
_MIN_INTERVAL = 240.0

# How long after the garage appears the sweep starts. Long enough for the
# sign-in, the carousel and the rest of this mod to have drawn: none of this
# is urgent.
_START_DELAY = 8.0

# How long after the player last changed something the sweep runs.
#
# A trailing delay rather than an immediate sweep, because mounting a piece of
# equipment is three or four syncs in a row and remounting a whole tank is a
# dozen. Waiting for the flurry to stop turns all of it into one upload, and
# twenty seconds is still fast enough that a player who tabs out to their own
# page finds it changed.
_CHANGE_DELAY = 20.0


class Uploader(Sending):
    """Reads the garage at the garage, and sends what moved."""

    def __init__(self, session, settings, link):
        self._session = session
        self._settings = settings
        self._link = link
        self._sent = load_sent()
        # What the server says it holds, read once a session before the first
        # upload. None until then, which `changed` reads as "do not second
        # guess the fingerprints".
        self._held = None
        self._last_sweep = 0.0
        self._busy = False
        # When the player last touched a vehicle, for the trailing delay.
        self._changed_at = 0.0
        # What the setting said last time we looked, so that turning it OFF is
        # a moment we can act on rather than a state we merely obey.
        self._sharing = self._shares()
        # Here rather than in `install`, which returns early when the client
        # has no player events: a mod that cannot upload anything must still
        # honour a player asking to be forgotten for what an earlier session
        # uploaded.
        self._settings.on_change(self._on_setting)

    def install(self):
        try:
            from PlayerEvents import g_playerEvents
            self._session.subscribe(g_playerEvents.onAccountShowGUI, self._on_garage)
            # Joining the queue, which is the last moment the lobby still has
            # the vehicle and the first at which it is certainly equipped.
            self._session.subscribe(g_playerEvents.onEnqueued, self._on_battle)
        except ImportError:
            _logger.exception('no player events; loadouts are never swept')
            return
        self._follow_changes()
        # The garage may already be up: the event fires when it appears, and
        # a mod installed after that would otherwise say nothing until the
        # player next came back from a battle. `sweep` refuses anywhere else,
        # so this costs nothing while the client is still starting, which is
        # when it normally runs.
        self._session.callback(_START_DELAY, self.sweep)
        # A withdrawal asked for in a previous session, which the game was
        # closed before we could deliver. `_on_garage` catches the later ones.
        if load_withdraw():
            self._session.callback(_START_DELAY, self._withdraw)
        _logger.info('installed')

    def _follow_changes(self):
        """Sweep when the player rebuilds a tank, not only when they leave.

        The garage event alone was the bug this fixes: it fires when the
        garage APPEARS, so a player who spends an hour there remounting
        vehicles sent nothing until they next came back from a battle. Their
        own page kept showing a build they had already replaced, which is
        exactly the thing a page like that must not do.

        `onSyncCompleted` is the client telling us its inventory changed, and
        it is what the game's own screens listen to for the same reason. It
        fires for far more than a loadout (a purchase, a battle result), which
        costs nothing here: a sweep that finds nothing changed sends nothing.
        """
        try:
            from helpers import dependency
            from skeletons.gui.shared import IItemsCache
            self._session.subscribe(dependency.instance(IItemsCache).onSyncCompleted,
                                    self._on_change)
        except Exception:
            _logger.exception('no items cache; loadouts only sweep on the garage')

    def _on_change(self, *args):
        # Trailing: remounting a tank is a flurry of syncs, and each one
        # pushes the moment back rather than starting its own sweep.
        self._changed_at = time.time()
        self._session.callback(_CHANGE_DELAY, self._sweep_if_settled)

    def _sweep_if_settled(self):
        """Sweep once the flurry has stopped, else let the later one do it."""
        if time.time() + 0.5 < self._changed_at + _CHANGE_DELAY:
            return
        self.sweep()

    def _on_battle(self, *args):
        """Record the vehicle going to battle, whatever the garage says.

        This is what "the last loadout used" means, and it is the only moment
        the game guarantees it: a vehicle cannot enter a battle half stripped,
        so what it carries here is what its owner means to play it with. It
        therefore overrides the demount rule, which exists precisely to keep a
        half-stripped garage state off the page until this happens.

        Sent on its own rather than through a sweep: it is one vehicle, the
        moment is brief, and the player is about to leave the garage.
        """
        if self._busy or not self._wanted():
            return
        vehicle = self._selected()
        if vehicle is None:
            return
        try:
            record = loadout(vehicle)
        except Exception:
            _logger.exception('could not read the loadout of the vehicle going to battle')
            return
        previous = self._sent.get(record['tankId'])
        if previous and previous.get('f') == fingerprint(record):
            return
        _logger.info('sending the loadout of the vehicle going to battle')
        self._busy = True
        self._post([record], [])

    @staticmethod
    def _selected():
        """The vehicle the player is about to take out, or None."""
        try:
            from CurrentVehicle import g_currentVehicle
            return g_currentVehicle.item if g_currentVehicle.isPresent() else None
        except Exception:
            _logger.exception('could not read the selected vehicle')
            return None

    def _shares(self):
        """What the setting says, on its own: no garage, no account, just the box."""
        try:
            return self._settings.sends_loadouts()
        except Exception:
            _logger.exception('could not read the loadout setting')
            return False

    def _on_setting(self):
        """Unticking the box is a withdrawal, not merely a pause.

        Stopping the uploads was all this used to do, which left everything
        already sent on the player's page for good. Someone who unticks a box
        that says they share their configurations has not asked us to freeze
        their page, they have asked to be off it.

        Only the falling edge. The setting is notified on every change of any
        setting, so the previous value is what makes this a moment.
        """
        sharing = self._shares()
        if self._sharing and not sharing:
            _logger.info('loadout sharing turned off; asking the server to forget this account')
            save_withdraw(True)
            self._withdraw()
        self._sharing = sharing

    def _withdraw(self):
        """Ask the server to forget this account, and keep asking until it has.

        The pending flag outlives the attempt and the session: a refusal here
        leaves rows published that the player believes are gone, so this is
        the one request in the file that must not be allowed to fail quietly.
        """

        def answered(response):
            code = getattr(response, 'responseCode', None)
            if code != 200:
                _logger.warning('the server would not forget this account (HTTP %s); '
                                'asked again at the next garage', code)
                return
            # Both halves, or a re-tick would upload nothing: the fingerprints
            # say the server already holds a carousel it has just dropped.
            self._sent = {}
            self._held = None
            save_sent({})
            save_withdraw(False)
            _logger.info('the server forgot this account')

        self._request('%s/api/game/loadouts' % config.API_BASE.rstrip('/'), answered,
                      method='DELETE')

    def _on_garage(self, *args):
        # A withdrawal the player asked for in a previous session, or one the
        # network refused. It comes first: it is the only thing here that is
        # owed to somebody.
        if load_withdraw():
            self._session.callback(_START_DELAY, self._withdraw)
        # Not on the spot: the garage has a sign-in, a carousel and every
        # other feature of this mod to draw first, and none of this is urgent.
        self._session.callback(_START_DELAY, self.sweep)

    def sweep(self):
        """Read every owned vehicle, then send what the server does not have."""
        if self._busy or not self._wanted():
            return
        now = time.time()
        if now - self._last_sweep < _MIN_INTERVAL:
            return
        vehicles = self._vehicles()
        if not vehicles:
            return
        self._busy = True
        self._last_sweep = now
        _Sweep(self, vehicles).step()

    def _wanted(self):
        """Whether the player is at the garage and has not turned this off."""
        try:
            from helpers import isPlayerAccount
            if not isPlayerAccount():
                return False
        except ImportError:
            return False
        try:
            return self._settings.sends_loadouts()
        except Exception:
            _logger.exception('could not read the loadout setting')
            return False

    @staticmethod
    def _vehicles():
        try:
            from gui.shared.utils.requesters import REQ_CRITERIA
            from helpers import dependency
            from skeletons.gui.shared import IItemsCache
            items = dependency.instance(IItemsCache).items
            return list(items.getVehicles(REQ_CRITERIA.INVENTORY).values())
        except Exception:
            _logger.exception('could not list the vehicles')
            return []

    def later(self, delay, func):
        """Schedule the sweep's next chunk on this session's own clock."""
        self._session.callback(delay, func)

    def swept(self, records):
        """Every vehicle read. Reconcile with the server, then send."""
        if self._held is None:
            self._read_held(lambda: self._send(records))
        else:
            self._send(records)



class _Sweep(object):
    """One pass over the carousel, a chunk at a time.

    Chunked because the client draws the garage on the thread this runs on.
    A few hundred vehicles is 0.15 seconds of work measured end to end, which
    is not much and is still a dropped frame if it lands in one go.
    """

    def __init__(self, uploader, vehicles):
        self._uploader = uploader
        self._left = vehicles
        self._records = []
        self._items = inventory()

    def step(self):
        chunk, self._left = self._left[:_CHUNK], self._left[_CHUNK:]
        for vehicle in chunk:
            try:
                self._records.append(loadout(vehicle, self._items))
            except Exception:
                # One unreadable vehicle is not worth losing the carousel
                # over, and a client patch is exactly how one appears.
                _logger.exception('could not read the loadout of %s',
                                  getattr(vehicle, 'name', '?'))
        if self._left:
            self._uploader.later(_CHUNK_PAUSE, self.step)
        else:
            self._uploader.swept(self._records)

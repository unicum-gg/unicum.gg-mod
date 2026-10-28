"""What the client has to be asked, and when it may be redrawn.

The wraps and the pacing. Every one of these sits on a call the client makes
itself, because the alternative -- redrawing on a timer -- either costs
frames or shows a stale panel, and both were tried.
"""
from __future__ import absolute_import

import logging
import weakref

from gui.Scaleform.daapi.view.battle.shared.stats_exchange.stats_ctrl import BattleStatisticsDataController
from gui.Scaleform.daapi.view.battle.shared.stats_exchange.vehicle import VehicleInfoComponent
from unicum import config
from unicum.api.entry import PLAYERS
from unicum.battle.drawing import Drawing, _ORDERED

_logger = logging.getLogger('unicum.battle.flags')

# Long enough to gather a whole team's worth of ids from the render pass,
# short enough to be back before anyone finishes reading the loading screen.
_BATCH_DELAY = 0.25

# How often the battle view is given the markers: a reloaded view starts empty.
_PUBLISH_SECONDS = 0.5


class BattleFlags(Drawing):


    def __init__(self, session, lookup, flags, badges, settings):
        self._session = session
        self._lookup = lookup
        self._textures = flags
        self._badges = badges
        self._settings = settings
        self._pending = set()
        self._scheduled = False
        # Statistics controllers of the battle in progress, redrawn once the
        # ratings their averages need have landed.
        self._controllers = weakref.WeakSet()
        # Vehicles whose panel row carries an inline marker of ours, and
        # whether a pass to take those markers back is already due.
        self._inline = set()
        self._taking_back = False
        # vehicle id -> icon_markers(), and each team's vehicle ids in order.
        self._markers = {}
        self._order = {'leftItemsIDs': [], 'rightItemsIDs': []}
        # The keys of _order the client has sent this battle.
        self._received = set()
        # (the battle view published to, what it was given)
        self._published = None
        # The extended info key (Alt), set by install().
        self.alt = None

    def install(self):
        self._session.patch(VehicleInfoComponent, 'addVehicleInfo', self._wrap)
        self._session.patch(BattleStatisticsDataController, 'as_setArenaInfoS',
                            self._wrap_arena)
        for name in _ORDERED:
            self._session.patch(BattleStatisticsDataController, name, self._wrap_order)
        self._session.repeat(_PUBLISH_SECONDS, self._publish)
        self._settings.on_change(self._redraw)
        _logger.info('installed on VehicleInfoComponent.addVehicleInfo, api=%s',
                     config.API_BASE)

    def _wrap(self, original):

        def addVehicleInfo(component, vInfoVO, overrides):
            result = original(component, vInfoVO, overrides)
            try:
                self._mark(component, vInfoVO)
            except Exception:
                # A panel without flags beats a panel that fails to build.
                _logger.exception('could not mark a battle player')
            return result

        return addVehicleInfo

    def _wrap_arena(self, original):

        def as_setArenaInfoS(controller, data):
            self._controllers.add(controller)
            try:
                self._mark_teams(controller, data)
            except Exception:
                _logger.exception('could not add the team averages')
            return original(controller, data)

        return as_setArenaInfoS

    def _wrap_order(self, original):

        def ordered(controller, data, *args, **kwargs):
            try:
                self._keep_order(data)
            except Exception:
                _logger.exception('could not read the order of the teams')
            return original(controller, data, *args, **kwargs)

        return ordered

    def _keep_order(self, data):
        if not isinstance(data, dict):
            return
        for key in self._order:
            if isinstance(data.get(key), list):
                self._order[key] = list(data[key])
                self._received.add(key)

    def _take_back(self):
        """Resend the rows that were given an inline marker too early.

        The panel is told about a vehicle once. This module writes a badge
        into that row only while the battle view is not drawing the badges
        itself, and the view needs a few frames to find its surfaces. The
        player's own vehicle is announced before that happens, so that one
        row keeps an inline badge while all the others get the drawn one:
        the same rating twice on one line, and the staler of the two, since
        nothing rewrites that row afterwards. Measured, not reasoned: one
        row showing 3 995 beside 4 063 for the same player.

        One pass per burst, and the rows are resent through
        `updateVehiclesInfo`, which pushes `as_updateVehiclesInfoS`. That is
        NOT `invalidateVehiclesInfo`: that one puts a new data provider into
        the panel's lists and rebinds every renderer, which costs other mods
        the Flash fields they grafted onto them.
        """
        if not self._inline or self._taking_back:
            return
        self._taking_back = True
        self._session.callback(_BATCH_DELAY, self._resend)

    def _resend(self):
        self._taking_back = False
        wanted, self._inline = sorted(self._inline), set()
        if not wanted:
            return
        try:
            from helpers import dependency
            from skeletons.gui.battle_session import IBattleSessionProvider
            from gui.battle_control.arena_info.settings import INVALIDATE_OP
            arena_dp = dependency.instance(IBattleSessionProvider).getArenaDP()
            if arena_dp is None:
                return
            # Only the vehicles the arena still knows. `getVehicleInfo`
            # answers an EMPTY vehicle for an id it has never heard of
            # rather than None, and resending one of those would blank a
            # row instead of mending it.
            known = {}
            for info in arena_dp.getVehiclesInfoIterator():
                known[info.vehicleID] = info
            # No flags: nothing is re-sorted and no prebattle state is
            # recomputed, the rows are simply described again.
            updated = [(INVALIDATE_OP.NONE, known[vehicle_id])
                       for vehicle_id in wanted if vehicle_id in known]
            if not updated:
                return
            for controller in list(self._controllers):
                controller.updateVehiclesInfo(updated, arena_dp)
            _logger.info('took the inline marker back off %d row(s)', len(updated))
        except Exception:
            _logger.exception('could not take the inline markers back')

    def _request(self, account_id):
        """Queue an id, and resolve the whole batch shortly after.

        Every vehicle in a team is added in the same pass, so waiting a
        moment turns what would be fifteen requests into one.
        """
        self._pending.add(account_id)
        if self._scheduled:
            return
        self._scheduled = True
        self._session.callback(_BATCH_DELAY, self._flush)

    def _flush(self):
        self._scheduled = False
        if not self._pending:
            return
        batch, self._pending = sorted(self._pending), set()
        _logger.info('resolving %s players', len(batch))
        self._lookup.prefetch(players=batch,
                              on_ready=lambda: self._report(batch))

    def _report(self, batch):
        resolved = []
        for account_id in batch:
            entry = self._lookup.get(PLAYERS, account_id)
            if entry is not None and entry.countries:
                resolved.append((account_id, entry.countries[0]))
        _logger.info('resolved %s/%s: %s', len(resolved), len(batch), resolved)
        self._redraw()

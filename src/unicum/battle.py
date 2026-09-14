"""Marks battle player names with where each player comes from.

The players panel, the full stats table (Tab) and the loading screen are fed
by the stats exchange: VehicleInfoComponent.addVehicleInfo builds one dict per
vehicle, and its `region` goes to AS3, where StatsUserProps and
formatPlayerName assign it as `htmlText`. So the flags go into that dict, and
nowhere else.

They used to go in one level lower, into player_format.getRegionCode. That
reached the same panels, but getRegionCode also feeds every other consumer
of a formatted name: the damage panel shows the player's own name as plain
text, so its <IMG> markup was drawn as characters, and playerFullName carried
it into markers and messages too. The stats exchange is where the name is
known to end up in an HTML field.

`region` is empty for anyone on their home realm, so on EU the field is
essentially always empty. A genuinely roaming player does have a code, and
it is not ours to drop: ours is appended to it.

Onslaught (comp7) gets flags too, at a cost in the log. Its VO leaves
`region` at null, typed Object, and DAAPIDataClass.fromHash reports a string
assigned there as "incorrect cast value ... to field with type Object" --
then assigns it anyway, so the flags draw. A player without flags is left
untouched, so only flagged players produce that line.

addVehicleInfo is synchronous and the answer comes over the network. So it
never waits: it uses whatever is cached, and the account ids it sees are
resolved in one batch just after. A vehicle drawn before the answer lands
picks its flags up the next time the arena updates it.
"""
import logging

from gui.Scaleform.daapi.view.battle.shared.stats_exchange.vehicle import VehicleInfoComponent

from unicum import config
from unicum.api.resolve import PLAYERS

_logger = logging.getLogger('unicum.battle')

# Long enough to gather a whole team's worth of ids from the render pass,
# short enough to be back before anyone finishes reading the loading screen.
_BATCH_DELAY = 0.25


class BattleFlags(object):

    def __init__(self, session, lookup, flags):
        self._session = session
        self._lookup = lookup
        self._textures = flags
        self._pending = set()
        self._scheduled = False

    def install(self):
        self._session.patch(VehicleInfoComponent, 'addVehicleInfo', self._wrap)
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

    def _mark(self, component, vInfoVO):
        data = component.get()
        player = getattr(vInfoVO, 'player', None)
        marker = self._marker(getattr(player, 'accountDBID', None))
        # Left untouched without a marker, so a None stays None.
        if marker and isinstance(data, dict):
            data['region'] = (data.get('region') or '') + marker

    def _marker(self, account_id):
        if not account_id:
            return ''
        # An old answer is still drawn while a fresh one is fetched.
        if self._lookup.needs_fetch(PLAYERS, account_id):
            self._request(account_id)
        # Every flag, up to config.MAX_FLAGS. A long name gets cut shorter by
        # the field for it; that trade was chosen over hiding languages.
        return self._textures.markup(self._lookup.get(PLAYERS, account_id))

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


def install(session, lookup, flags):
    BattleFlags(session, lookup, flags).install()

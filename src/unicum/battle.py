"""Marks battle player names with where each player comes from.

The rating badge and the flags are drawn by each vehicle icon, lined up in a
column per team. The battle view (as3/src/unicum/VehicleMarkers.as) draws
them from the markup per vehicle and the order of each team published here:
in the players panel beside the icon, towards the middle of the screen; in a
Flash Tab screen outside each team's rows; on the loading screen beside the
icon. No row names its vehicle, so the order is taken from what the
statistics controller sends those screens (leftItemsIDs and rightItemsIDs).

Without the battle view they go after the player's name instead. The panels
are fed by the stats exchange: VehicleInfoComponent.addVehicleInfo builds one
dict per vehicle, and its `region` goes to AS3, where StatsUserProps and
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

Each team's average rating goes after its name, in the Tab screen and on the
loading screen. Those names are set as plain text (team1TF.text), so the
badge only draws when the battle view (as3/src/unicum/TeamNamesHtml.as) is
loaded to re-set them as HTML; without it the average is a bare number. In a
Flash Tab table the view then moves it into the team's badge column.
"""
import logging
import re
import weakref

from gui.Scaleform.daapi.view.battle.shared.stats_exchange.stats_ctrl import BattleStatisticsDataController
from gui.Scaleform.daapi.view.battle.shared.stats_exchange.vehicle import VehicleInfoComponent

from unicum import config, modes, views
from unicum.api.entry import PLAYERS

_logger = logging.getLogger('unicum.battle')

# Long enough to gather a whole team's worth of ids from the render pass,
# short enough to be back before anyone finishes reading the loading screen.
_BATCH_DELAY = 0.25

# How often the battle view is given the markers: a reloaded view starts empty.
_PUBLISH_SECONDS = 0.5

_IMG_WIDTH = re.compile(r'<IMG[^>]*\bwidth="(\d+)"', re.IGNORECASE)
_IMG = re.compile(r'<IMG[^>]*>', re.IGNORECASE)

# A space in markup; a bare number's digits, when a badge cannot draw.
_SPACE_WIDTH = 4
_DIGIT_WIDTH = 7

# The statistics controller's methods whose data can carry each team's order:
# every exchange it adds sort ids to (stats_ctrl.py). Frags re-sort the teams
# too, in the Tab of a mode that orders by them.
_ORDERED = ('as_setVehiclesDataS', 'as_addVehiclesInfoS', 'as_updateVehiclesInfoS',
            'as_updateVehicleStatusS', 'as_setFragsS', 'as_updateVehiclesStatsS')


def markup_width(markup):
    """Pixels the markup takes: its images' widths, and text by the character."""
    images = sum(int(width) for width in _IMG_WIDTH.findall(markup))
    text = _IMG.sub('', markup)
    return images + text.count(' ') * _SPACE_WIDTH + sum(c.isdigit() for c in text) * _DIGIT_WIDTH


def icon_markers(flags, badge):
    """[badge html, its width, flags html, their width], drawn as two columns."""
    badge, flags = badge.strip(), flags.strip()
    return [badge, markup_width(badge), flags, markup_width(flags)]


class BattleFlags(object):

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

    def _publish(self):
        """Give the battle view the markers and the teams' order, when changed.

        Both are read from the arena each time rather than kept from the
        vehicles drawn, so a hot reload mid-battle draws them at once. The
        order the client last sent is kept, since a mode may sort its own
        way; until one arrives, the client's default order stands in.
        """
        view = views.battle_view()
        arena = _arena() if view is not None else None
        if arena is None:
            # Between battles: the next one sends its own order.
            self._order = {'leftItemsIDs': [], 'rightItemsIDs': []}
            self._received = set()
            self._published = None
            return
        self._markers = {}
        shows = modes.team_filter(self._settings)
        for vInfo in arena.getVehiclesInfoIterator():
            if vInfo.isObserver() or not shows(vInfo.team):
                continue
            flags, badge = self._marker(vInfo.player.accountDBID)
            if flags or badge:
                self._markers[vInfo.vehicleID] = icon_markers(flags, badge)
        if len(self._received) < len(self._order):
            for key, ids in _default_order(arena).items():
                if key not in self._received:
                    self._order[key] = ids
        # The client's Scaleform has no JSON to parse with.
        state = ('\n'.join('%s\t%s\t%d\t%s\t%d' % ((k,) + tuple(v))
                           for k, v in sorted(self._markers.items())),
                 ','.join(str(i) for i in self._order['leftItemsIDs']),
                 ','.join(str(i) for i in self._order['rightItemsIDs']))
        panel_hidden = self._settings.alt_only('panel') and not (self.alt is not None and self.alt.down)
        state = state + (panel_hidden,)
        # By identity: a reloaded view's proxy can reuse the old one's address.
        if self._published is not None and self._published[0] is view and self._published[1] == state:
            return
        first = self._published is None
        self._published = (view, state)
        try:
            view.markersText, view.leftIds, view.rightIds = state[:3]
        except Exception:
            _logger.exception('could not give the battle view its markers')
            return
        try:
            view.panelHidden = panel_hidden
        except Exception:
            # A view whose class predates the property, until the next battle.
            _logger.debug('the battle view has no panelHidden yet', exc_info=True)
        if first:
            # Names drawn before the view loaded carry the markers after them.
            self._redraw()

    def _mark_teams(self, controller, data):
        if not self._settings.shows_average('battle'):
            return
        arena = controller._battleCtx.getArenaDP()
        teams = {'allyTeamName': [], 'enemyTeamName': []}
        # A team whose players show nothing gets no average either.
        shows = modes.team_filter(self._settings)
        for vInfo in arena.getVehiclesInfoIterator():
            if vInfo.isObserver() or not shows(vInfo.team):
                continue
            key = 'allyTeamName' if arena.isAllyTeam(vInfo.team) else 'enemyTeamName'
            teams[key].append(vInfo.player.accountDBID)
        for key, account_ids in teams.items():
            average = self._average(account_ids)
            name = data.get(key)
            if average is None or name is None:
                continue
            if isinstance(name, str):
                # A localised team name arrives as UTF-8 bytes.
                name = name.decode('utf-8', 'replace')
            # A literal average sign rather than an entity: the field shows
            # plain text until the battle view re-sets it as HTML.
            badge = self._badges.markup(self._settings.metric('battle'), average) if views.html_team_names() else None
            data[key] = u'%s  \u00d8 %s' % (name, badge or '%d' % round(average))

    def _average(self, account_ids):
        """Mean chosen rating of the players whose rating is known, or None."""
        values = []
        for account_id in account_ids:
            if not account_id:
                continue
            if self._lookup.needs_fetch(PLAYERS, account_id):
                self._request(account_id)
            entry = self._lookup.get(PLAYERS, account_id)
            value = self._settings.rating(entry, 'battle')
            if value is not None:
                values.append(value)
        return sum(values) / float(len(values)) if values else None

    def _mark(self, component, vInfoVO):
        data = component.get()
        player = getattr(vInfoVO, 'player', None)
        if not modes.team_filter(self._settings)(getattr(vInfoVO, 'team', None)):
            return
        flags, badge = self._marker(getattr(player, 'accountDBID', None))
        # Beside the vehicle icon instead, drawn by the battle view.
        if views.html_team_names():
            return
        # Left untouched without a marker, so a None stays None.
        if (flags or badge) and isinstance(data, dict):
            data['region'] = (data.get('region') or '') + flags + badge

    def _marker(self, account_id):
        """(flags markup, rating badge markup), each '' when not shown."""
        if not account_id or not self._settings.shows('battle'):
            return '', ''
        # An old answer is still drawn while a fresh one is fetched.
        if self._lookup.needs_fetch(PLAYERS, account_id):
            self._request(account_id)
        entry = self._lookup.get(PLAYERS, account_id)
        flags = ''
        if self._settings.shows_flags('battle'):
            flags = self._textures.markup(entry, self._settings['maxFlags'])
        return flags, self._badges.rating(entry, self._settings, 'battle')

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

    def _redraw(self):
        """Redraw the players' names and the team averages.

        invalidateArenaInfo resends both. After an answer it asks for nothing
        new, since every id it sees has an answer by now.
        """
        for controller in list(self._controllers):
            try:
                controller.invalidateArenaInfo()
            except Exception:
                _logger.exception('could not redraw the battle statistics')


def _arena():
    """The battle's arena data provider, or None outside a battle."""
    from helpers import dependency
    from skeletons.gui.battle_session import IBattleSessionProvider
    return dependency.instance(IBattleSessionProvider).getArenaDP()


def _default_order(arena):
    """Each team's vehicle ids as the client sorts them for its screens.

    What TeamsSortedIDsComposer sends: sorted by VehicleInfoSortKey, without
    observers. Stands in until the client sends its own, which a mode may
    sort its own way.
    """
    from gui.battle_control.arena_info import vos_collections

    def ids(collection):
        return [vehicle_id for vehicle_id in collection(sortKey=vos_collections.VehicleInfoSortKey).ids(arena)
                if not arena.getVehicleInfo(vehicle_id).vehicleType.isObserver]

    return {'leftItemsIDs': ids(vos_collections.AllyItemsCollection),
            'rightItemsIDs': ids(vos_collections.EnemyItemsCollection)}


def install(session, lookup, flags, badges, settings):
    from unicum.extended_info import ExtendedInfo
    alt = ExtendedInfo(session)
    alt.install()
    battle_flags = BattleFlags(session, lookup, flags, badges, settings)
    battle_flags.alt = alt
    battle_flags.install()
    alt.on_change(battle_flags._publish)
    try:
        from gui.Scaleform.daapi.view.battle.shared.markers2d import manager  # the client has them
    except ImportError:
        _logger.info('no vehicle markers in this client, no badge by the names above vehicles')
        return
    try:
        from unicum import name_markers
        name_markers.install(session, battle_flags)
    except Exception:
        # The rest of the battle surfaces stay.
        _logger.exception('could not install the badges by the names above vehicles')

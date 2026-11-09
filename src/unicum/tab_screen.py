"""Ratings on the battle Tab screen, drawn in its page.

The Tab screen ("Team composition") is Coherent Gameface. Its python side,
`gui.impl.battle.battle_page.tab_view.TabView`, fills a model the page binds
with `data-bind-for="index, item:{{model.playerList.allies}}"`, and three
separate attempts to put a rating in that model have now been written,
confirmed present in the model by a probe, and NOT drawn on screen:

    tab probe:  name=u'szucsmester'  clan=u'BOBHU 1491'
    tab probe:  name=u'V0MIT0'       clan=u'HVZ 1226'

Both `userName` and `clanAbbrev`, two unrelated string properties, were in
the native model and neither appeared. Whatever the reason, that model is not
the road to this screen, so this module takes the other one: it runs a script
inside the page and writes into the DOM.

WHY THIS IS NOT THE SAME GRAFT AS THE RESULTS SCREEN

`battle_results.py` patches `_getChildComponents`, which is defined on
`ViewComponent`. `TabView` extends `ViewImpl`, which has no such method and
never calls one, so the same patch here would create a method nobody
invokes: a silent no-op, and exactly the kind of failure that has already
cost hours on this screen.

The road that works is `View.setChildView`, which `ViewImpl` does inherit,
and it is not a deduction. `gravity.scheduled_personal_reserves`, installed
in this game, does it on this view, and the client's own log says so on
every battle:

    [Glow] Parent view loaded: TabView.
    [Glow] Child attached to TabView with layout ID 19.
    [Glow][Gameface] Reconcile: ... cards=5, matched=0

`cards=5` is a `document.querySelectorAll` running in the battle Tab's page.

Everything else is borrowed: the `UnicumTankButton` layout, its loader and
the model shape are the ones the hangar and the results screen already use,
so there is no new resource to declare and no client restart to ask for.
"""
import functools
import json
import logging
import weakref
import zlib

from frameworks.wulf import ViewModel
from gui.impl.pub.view_component import ViewComponent

from unicum import badges, extended_info, modes, resources
from unicum.api.entry import PLAYERS
from unicum.layouts import layout_id
from unicum.tank_button import FEATURE, LAYOUT, compose

_logger = logging.getLogger('unicum.tab_screen')

# The settings surface this screen reads. `battle` is the one the ratings and
# the flags are configured under, as the players panel reads them; `tab` is
# the one that says whether THIS screen waits for the extended info key and
# whether it carries a team average. battle.py has used the same two names
# for both of these since the Flash version of this screen.
SURFACE = 'battle'
SCREEN = 'tab'

_MODULE = 'coui://gui/gameface/mods/unicum/TankButton/TankButton.js'
_SCRIPT = 'web/battle/tab_screen.js'
_STYLE = 'web/battle/tab_screen.css'
_CHECK_SECONDS = 1.0

# Where live models are kept across reloads of this package: on the host
# class, so a reimport finds the screens already open.
_REGISTRY = '_unicumTabModels'

# Property indexes; gf_mod_inject takes 0 with ModInjectModel.
_ENABLED = 1
_REVISION = 2
_SCRIPT_TEXT = 3
_STYLE_TEXT = 4
_DATA = 5


def _report(args):
    """Where the page's `api.report` lands.

    Reached through an eval of an import, never as a bound function: a view
    outlives a reload of this package, so a handler holding today's function
    would keep running yesterday's code. `tank_button` explains the same
    trick at length.
    """
    logging.getLogger('unicum.tab_screen').info('page: %s', args)


_ON_ITEM = functools.partial(
    eval, "__import__('unicum.tab_screen', None, None, ['_report'])._report(locals())", {})


class TabModel(ViewModel):
    __slots__ = ('onItemClick', )

    def __init__(self, properties=6, commands=1):
        super(TabModel, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(TabModel, self)._initialize()
        from openwg_gameface import gf_mod_inject
        gf_mod_inject(self, FEATURE, modules=[_MODULE])
        self._addBoolProperty('enabled', True)
        self._addNumberProperty('revision', 0)
        self._addStringProperty('script', '')
        self._addStringProperty('style', '')
        self._addStringProperty('data', '')
        self.onItemClick = self._addCommand('onItemClick')


class TabScreen(object):

    def __init__(self, session, lookup, flags, badges, scales, settings, alt):
        self._session = session
        self._lookup = lookup
        self._textures = flags
        self._badges = badges
        self._scales = scales
        self._settings = settings
        self._alt = alt
        self._host = None
        self._layout = None
        self._stamps = None
        self._script = self._style = u''
        self._revision = 0
        self._published = weakref.WeakKeyDictionary()
        self._views = weakref.WeakKeyDictionary()

    # ------------------------------------------------------------- installing

    def install(self):
        try:
            import openwg_gameface  # noqa: F401 -- the injector the model needs
        except ImportError:
            _logger.info('openwg_gameface not installed, no ratings on the Tab screen')
            return
        try:
            from gui.impl.battle.battle_page.tab_view import TabView
        except ImportError:
            _logger.info('no Tab view in this client, no ratings on that screen')
            return
        self._layout = layout_id(LAYOUT, FEATURE)
        if self._layout is None:
            _logger.info('%s not in the resource map yet, no ratings on the Tab screen', FEATURE)
            return
        self._host = TabView
        self._session.patch(TabView, '_onLoaded', self._wrap_loaded)
        self._check()
        self._session.repeat(_CHECK_SECONDS, self._check)
        self._settings.on_change(self._publish_all)
        if self._alt is not None:
            self._alt.on_change(self._publish_all)
        _logger.info('installed on TabView, layout %s', self._layout)

    def _wrap_loaded(self, original):

        def _onLoaded(view, *args, **kwargs):
            result = original(view, *args, **kwargs)
            try:
                self._attach(view)
            except Exception:
                # A Tab screen without ratings beats a Tab screen that fails.
                _logger.exception('could not attach to the Tab screen')
            return result

        return _onLoaded

    def _attach(self, view):
        """Graft our page onto this screen, once.

        `getChildView` first: `_onLoaded` can run more than once over the life
        of a view, and `setSubView` refuses a child that already has a parent
        with 'child %r can not be added', which would be the only sign.
        """
        if view.getChildView(self._layout) is not None:
            _logger.info('the Tab screen already carries our page')
            return
        child = ViewComponent(layoutID=self._layout, model=TabModel)
        model = child.getViewModel()
        model.onItemClick += _ON_ITEM
        view.setChildView(self._layout, child)
        self._models()[model] = True
        self._views[model] = weakref.ref(view)
        self._load_code(model)
        self._publish(model)
        _logger.info('attached our page to the Tab screen')

    def _models(self):
        models = getattr(self._host, _REGISTRY, None)
        if models is None:
            models = weakref.WeakKeyDictionary()
            setattr(self._host, _REGISTRY, models)
        return models

    # --------------------------------------------------------------- the code

    def _check(self):
        """New code when a source changes, and the data again: a rating may have landed."""
        stamps = tuple(resources.stamp(path) for path in (_SCRIPT, _STYLE))
        if stamps != self._stamps:
            self._stamps = stamps
            self._script = compose([('tab screen', resources.read(_SCRIPT).decode('utf-8'))])
            self._style = resources.read(_STYLE).decode('utf-8')
            self._revision = zlib.crc32((self._script + self._style).encode('utf-8')) & 0x3fffffff
            for model in list(self._models().keys()):
                self._load_code(model)
        self._publish_all()

    def _load_code(self, model):
        try:
            model._setString(_SCRIPT_TEXT, self._script)
            model._setString(_STYLE_TEXT, self._style)
            model._setNumber(_REVISION, self._revision)
        except Exception:
            _logger.exception('could not give the Tab screen its code')

    # --------------------------------------------------------------- the data

    def _roster(self):
        """[(the names a row may show, account id, on our team)] for this arena.

        The arena data PROVIDER, not the Tab view's own vehicle dict. That
        dict carries `accountDBID` 0 for a third of the rows -- measured,
        `tab: sources model=0L vehicle=4177952L panel=None` -- while the
        provider the players panel reads has a real id for the same vehicle.

        Both names are listed, the real one and an anonymised player's
        made-up one, so whichever the row shows finds the right account. The
        page keys on the name it draws and nothing else: the rows carry no
        identifier at all, no `data-test-id` and no materialised vehicle id.
        """
        found = []
        try:
            from helpers import dependency
            from skeletons.gui.battle_session import IBattleSessionProvider
            arena_dp = dependency.instance(IBattleSessionProvider).getArenaDP()
            if arena_dp is None:
                return found
            for info in arena_dp.getVehiclesInfoIterator():
                player = getattr(info, 'player', None)
                account_id = getattr(player, 'accountDBID', 0)
                if not account_id:
                    continue
                names = [name for name in (getattr(player, 'name', None),
                                           getattr(player, 'fakeName', None)) if name]
                if not names:
                    continue
                found.append((names, account_id,
                              int(getattr(getattr(info, 'vehicleType', None),
                                          'compactDescr', 0) or 0),
                              bool(arena_dp.isAllyTeam(info.team))))
        except Exception:
            _logger.debug('could not read the arena roster', exc_info=True)
        return found

    def _count(self, battles):
        """{image, width, height} of a battle-count pill, or {text, color}.

        The one neutral band, like every battle count this mod draws: the
        count has no scale of its own, and inventing a colour for it would
        claim a meaning that does not exist.
        """
        text = badges.count(battles)
        found = self._badges.picture(text, badges.NEUTRAL)
        if found is not None:
            path, width, height = found
            return {'image': 'img://%s' % path, 'width': width, 'height': height}
        # `text`, not `value`: the count is already shortened and grouped
        # (844, 161k), and the page's own grouping would make "1 61k" of it.
        return {'text': text, 'color': badges.NEUTRAL}

    def _vehicle(self, metric, account_id, tank_id, mode):
        """What this player does on this vehicle, as the page draws it.

        None when there is nothing to say: an account we hold no record for,
        or a vehicle this player has never taken into this mode. That is the
        answer the whole figure exists for, so it is never dressed up as a
        zero -- never played and played badly are different things.
        """
        record = self._lookup.vehicle(account_id, tank_id, mode)
        if record is None or not record.known or not record.battles:
            return None
        shown = {'scope': record.scope or 'overall', 'battles': self._count(record.battles)}
        value = record.rating(metric) if metric else None
        if value is not None:
            shown['rating'] = self._badge(metric, value)
        return shown

    def _badge(self, metric, value):
        """{image, width, height} of a rating's badge, or {value, color}.

        The IMAGE, not a shape built in CSS. The mod draws this badge
        everywhere else -- above the vehicles, in the players panel, on the
        results screen -- from `badge_png`, on a fixed grid: 3px of padding,
        a 6px cell per digit, 2px between thousands, rounded corners, the
        band's colour, white text. Reproducing that in a stylesheet gets
        close and stays visibly not the same thing, which is what the first
        two attempts here were. `img://` resolves in this page: the language
        flags beside these badges are already drawn that way.

        The CSS pill stays as the fallback for the session where the badge
        folder was not in the client's resource index at startup, which is
        the one case `Badges.image` cannot draw for.
        """
        found = self._badges.image(metric, value) if metric else None
        if found is not None:
            path, width, height = found
            return {'image': 'img://%s' % path, 'width': width, 'height': height}
        color = self._scales.color(metric, value) if metric else None
        return {'value': int(round(value)), 'color': color or '#F2F2F7'}

    def _publish_all(self):
        for model in list(self._models().keys()):
            self._publish(model)

    def _publish(self, model):
        data = {'players': {}, 'averages': {'allies': None, 'enemies': None},
                'shown': False}
        # The same wait the players panel honours: a player who asked for
        # these numbers only while the extended info key is held gets them
        # only then, on this screen too.
        waiting = extended_info.waits(self._alt, self._settings, SCREEN)
        if self._settings.shows(SURFACE) and not waiting:
            data['shown'] = True
            metric = self._settings.metric(SURFACE)
            limit = self._settings['maxFlags'] if self._settings.shows_flags(SURFACE) else 0
            wanted = []
            pairs = []
            values = {'allies': [], 'enemies': []}
            # The mode this battle has per-vehicle statistics under, which is
            # None for the modes Wargaming publishes none for (modes.py). The
            # record then covers every mode, and says so.
            mode = modes.current_wg_mode()
            vehicle_metric = self._settings.vehicle_metric(SURFACE)
            for names, account_id, tank_id, ally in self._roster():
                # Asked for before the player is read, so a roster whose
                # ratings are already cached still fetches the pairs.
                if tank_id and self._lookup.needs_vehicle(account_id, tank_id, mode):
                    pairs.append((account_id, tank_id))
                if self._lookup.needs_fetch(PLAYERS, account_id):
                    wanted.append(account_id)
                    continue
                entry = self._lookup.get(PLAYERS, account_id)
                value = self._settings.rating(entry, SURFACE)
                shown = {}
                if value is not None:
                    shown.update(self._badge(metric, value))
                    values['allies' if ally else 'enemies'].append(value)
                if tank_id:
                    found = self._vehicle(vehicle_metric, account_id, tank_id, mode)
                    if found is not None:
                        shown['vehicle'] = found
                if limit and entry is not None:
                    sources = [self._textures.source(code) for code in entry.flags[:limit]]
                    sources = [source for source in sources if source]
                    if sources:
                        shown['flags'] = sources
                if shown:
                    for name in names:
                        data['players'][name] = shown
            if self._settings.shows_average(SURFACE):
                for side in ('allies', 'enemies'):
                    found = values[side]
                    if not found:
                        continue
                    mean = int(round(sum(found) / float(len(found))))
                    data['averages'][side] = self._badge(metric, mean)
            if wanted or pairs:
                self._lookup.prefetch(players=sorted(set(wanted)), vehicles=pairs,
                                      mode=mode, on_ready=self._publish_all)
        text = json.dumps(data, sort_keys=True)
        if self._published.get(model) == text:
            return
        try:
            model._setString(_DATA, text)
            self._published[model] = text
        except Exception:
            _logger.debug('a Tab model gone', exc_info=True)


def install(session, lookup, flags, badges, scales, settings, alt):
    TabScreen(session, lookup, flags, badges, scales, settings, alt).install()

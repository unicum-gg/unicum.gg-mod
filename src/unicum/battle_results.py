"""Ratings and language flags by the names of the post-battle results.

The results of a random battle, and of the modes that open the same kind of
screen (Onslaught among them), are Gameface: their names are React text, so
no <IMG> markup can ride in them as it does in the contacts list. The names
are decorated in the page instead, by web/results/battle_results.js, run by
the same loader as the hangar's tank menu (res/gui/gameface/mods/unicum/
TankButton/TankButton.js): a view of that layout is added to the results
view's children, the way tank_button.py adds one to the vehicle menu, and its
model carries the script, its style, and the players to decorate as JSON in
`data`:

    {"hidden": false,
     "players": {"Player_1": {"score": {"value": 1934, "color": "#4A92B7"},
                              "flags": ["img://gui/maps/icons/unicum/flags/PL.png"]}}}

keyed by the name the page shows, under `players`, with `hidden` true while
they wait for the extended info key (Alt, as in battle). The page shows the
player's own name to them and an anonymized player's made-up one to everyone
else, and the results carry both with the real account: each player is
listed under both names, so whichever the row shows gets the real account's
rating.

The key is followed through gui.InputHandler, which the client feeds every key
in the garage as in battle, against the command bound to the markers' extended
info, so a rebound key counts the same.

Ratings come from the shared lookup: the battle just played has them already,
an older one opened from the notifications asks for them, and the page is
given them again once they land. Without openwg_gameface, or before the
client has restarted with the layout in its resource map, nothing changes.
"""
import functools
import json
import logging
import weakref
import zlib

from frameworks.wulf import ViewModel
from gui.impl.gen_utils import INVALID_RES_ID
from gui.impl.pub.view_component import ViewComponent

from unicum import resources
from unicum.api.entry import PLAYERS
from unicum.tank_button import FEATURE, compose

_logger = logging.getLogger('unicum.battle_results')

SURFACE = 'battleResults'

_MODULE = 'coui://gui/gameface/mods/unicum/TankButton/TankButton.js'
_SCRIPT = 'web/results/battle_results.js'
_STYLE = 'web/results/battle_results.css'
_CHECK_SECONDS = 1.0

# Where live models are kept across reloads of this package.
_REGISTRY = '_unicumResultsModels'

# The results views, by module, that take the loader as a child: Onslaught's
# lives in its own package, absent from some clients.
_VIEWS = (
    ('gui.impl.lobby.battle_results.random_battle_results_view', 'RandomBattleResultsView'),
    ('comp7.gui.impl.lobby.battle_results.comp7_battle_results_view', 'Comp7BattleResultsView'),
)

# Property indexes; gf_mod_inject adds ModInjectModel first.
_ENABLED = 1
_REVISION = 2
_SCRIPT_TEXT = 3
_STYLE_TEXT = 4
_DATA = 5

# The loader's log lines, as the hangar's.
_ON_ITEM = functools.partial(
    eval, "__import__('unicum.tank_button', None, None, ['on_item']).on_item(locals())", {})


def players_of(results):
    """[(account id, [the names the page may show])] of a battle's results: real, then made-up."""
    players = []
    for account_id, info in results.reusable.players.getPlayerInfoIterator():
        names = [info.realName]
        if info.fakeName and info.fakeName != info.realName:
            names.append(info.fakeName)
        players.append((account_id, names))
    return players


def decorations(players, entry_of, settings, flags, scales):
    """{name shown: {score, flags}} for the players with something to show, under each of their names."""
    metric = settings.metric(SURFACE)
    limit = settings['maxFlags'] if settings.shows_flags(SURFACE) else 0
    out = {}
    for account_id, names in players:
        entry = entry_of(account_id)
        if entry is None:
            continue
        value = settings.rating(entry, SURFACE)
        color = scales.color(metric, value) if value is not None else None
        sources = [flags.source(code) for code in entry.flags[:limit]] if limit else []
        shown = {'score': {'value': int(round(value)), 'color': color} if color else None,
                 'flags': [source for source in sources if source]}
        if shown['score'] or shown['flags']:
            for name in names:
                if name:
                    out[name] = shown
    return out


class ResultsModel(ViewModel):
    __slots__ = ('onItemClick', )

    def __init__(self, properties=6, commands=1):
        super(ResultsModel, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(ResultsModel, self)._initialize()
        from openwg_gameface import gf_mod_inject
        gf_mod_inject(self, FEATURE, modules=[_MODULE])
        self._addBoolProperty('enabled', True)
        self._addNumberProperty('revision', 0)
        self._addStringProperty('script', '')
        self._addStringProperty('style', '')
        self._addStringProperty('data', '')
        self.onItemClick = self._addCommand('onItemClick')


class BattleResults(object):

    def __init__(self, session, lookup, flags, scales, settings):
        self._session = session
        self._lookup = lookup
        self._flags = flags
        self._scales = scales
        self._settings = settings
        self._stamps = None
        self._script = self._style = u''
        self._revision = 0
        self._holder = None
        self._alt = False

    def install(self):
        try:
            from openwg_gameface import res_id_by_key
        except ImportError:
            _logger.info('openwg_gameface not installed, no ratings in the battle results')
            return
        self._layout = res_id_by_key(FEATURE)
        if self._layout == INVALID_RES_ID:
            _logger.info('%s not in the resource map yet, no ratings in the battle results', FEATURE)
            return
        patched = []
        for module, name in _VIEWS:
            view_class = _import(module, name)
            if view_class is None:
                continue
            if self._holder is None:
                self._holder = view_class
            self._session.patch(view_class, '_getChildComponents', self._wrap)
            patched.append(name)
        if not patched:
            _logger.info('no battle results view in this client')
            return
        self._follow_alt()
        self._check()
        self._session.repeat(_CHECK_SECONDS, self._check)
        self._settings.on_change(self._publish_all)
        _logger.info('installed in %s', ', '.join(patched))

    def _follow_alt(self):
        try:
            from gui import InputHandler
        except ImportError:
            return
        handler = self._on_key
        InputHandler.g_instance.onKeyDown += handler
        InputHandler.g_instance.onKeyUp += handler

        def remove():
            InputHandler.g_instance.onKeyDown -= handler
            InputHandler.g_instance.onKeyUp -= handler

        self._session.on_close(remove)

    def _on_key(self, event):
        # A plain Event: a handler that raised would stop the ones after it.
        try:
            import CommandMapping
            if not CommandMapping.g_instance.isFired(CommandMapping.CMD_VEHICLE_MARKERS_SHOW_INFO, event.key):
                return
            down = bool(event.isKeyDown())
            if down != self._alt:
                self._alt = down
                if self._settings.alt_only('results'):
                    self._publish_all()
        except Exception:
            _logger.debug('could not read a key', exc_info=True)

    def _models(self):
        models = getattr(self._holder, _REGISTRY, None)
        if models is None:
            models = weakref.WeakKeyDictionary()
            setattr(self._holder, _REGISTRY, models)
        return models

    def _wrap(self, original):

        def _getChildComponents(view):
            children = dict(original(view))
            arena_id = getattr(view, 'arenaUniqueID', None)
            if arena_id is not None:
                children[self._layout] = lambda: self._make_view(arena_id)
            return children

        return _getChildComponents

    def _make_view(self, arena_id):
        view = ViewComponent(layoutID=self._layout, model=ResultsModel)
        model = view.getViewModel()
        model.onItemClick += _ON_ITEM
        self._models()[model] = (arena_id, None)
        self._load_code(model)
        players = self._players(arena_id)
        if players:
            wanted = [account_id for account_id, _ in players
                      if account_id and self._lookup.needs_fetch(PLAYERS, account_id)]
            if wanted:
                self._lookup.prefetch(players=wanted, on_ready=self._publish_all)
        self._publish(model)
        return view

    @staticmethod
    def _players(arena_id):
        from helpers import dependency
        from skeletons.gui.battle_results import IBattleResultsService
        try:
            ctrl = dependency.instance(IBattleResultsService).getStatsCtrl(arena_id)
            return players_of(ctrl.getResults()) if ctrl is not None else []
        except Exception:
            _logger.exception('could not read the players of battle %s', arena_id)
            return []

    def _check(self):
        """New code when a source changes, and the data again: a flag may have landed since."""
        stamps = tuple(resources.stamp(path) for path in (_SCRIPT, _STYLE))
        if stamps != self._stamps:
            self._stamps = stamps
            self._script = compose([('battle results', resources.read(_SCRIPT).decode('utf-8'))])
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
            _logger.exception('could not give the battle results their code')

    def _publish_all(self):
        for model in list(self._models().keys()):
            self._publish(model)

    def _publish(self, model):
        models = self._models()
        arena_id, published = models.get(model, (None, None))
        if arena_id is None:
            return
        shown = {}
        if self._settings.shows(SURFACE):
            shown = decorations(self._players(arena_id), lambda account_id: self._lookup.get(PLAYERS, account_id),
                                self._settings, self._flags, self._scales)
        hidden = self._settings.alt_only('results') and not self._alt
        text = json.dumps({'hidden': hidden, 'players': shown}, sort_keys=True)
        if text == published:
            return
        try:
            model._setString(_DATA, text)
            models[model] = (arena_id, text)
        except Exception:
            _logger.debug('a results model gone', exc_info=True)


def _import(module, name):
    try:
        return getattr(__import__(module, None, None, [name]), name)
    except (ImportError, AttributeError):
        return None


def install(session, lookup, flags, scales, settings):
    BattleResults(session, lookup, flags, scales, settings).install()

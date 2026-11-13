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
                              "flags": ["img://gui/maps/icons/unicum/flags/PL.png"]}},
     "averages": {"allies": {"value": 1612, "color": "#6D9521"}, "enemies": null}}

keyed by the name the page shows, under `players`, with `hidden` true while
they wait for the extended info key (Alt, as in battle). The page shows the
player's own name to them and an anonymized player's made-up one to everyone
else, and the results carry both with the real account: each player is
listed under both names, so whichever the row shows gets the real account's
rating. Each team's average is that of its players whose rating is known,
drawn on the team's header line.

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
from gui.impl.pub.view_component import ViewComponent

from unicum import config, resources
from unicum.api.entry import PLAYERS
from unicum.battle_results.rows import (SURFACE, averages, decorations,
                                        mode_of, players_of)
from unicum.layouts import layout_id
from unicum.tank_button import FEATURE, LAYOUT, compose

_logger = logging.getLogger('unicum.battle_results')

_MODULE = 'coui://gui/gameface/mods/unicum/TankButton/TankButton.js'
_SCRIPT = 'web/results/battle_results.js'
# The replay tab, a second script rather than more of the first: the two share
# this screen and nothing else, and `compose` already runs several parts side
# by side, each stopped on its own. One failing leaves the other standing.
_REPLAY_SCRIPT = 'web/results/replay_tab.js'
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
_REPLAY = 6

# One position a second per vehicle. See `_want_replay`.
_REPLAY_EVERY = 1
# A battle reaches the site about a minute after it ends, so the first ask
# almost always misses. Measured over ten battles: 66 to 79 seconds for most,
# a few minutes for the stragglers.
_REPLAY_RETRY = 15.0
_REPLAY_TRIES = 12

# The loader's log lines, as the hangar's.
_ON_ITEM = functools.partial(
    eval, "__import__('unicum.tank_button', None, None, ['on_item']).on_item(locals())", {})


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
        # The replay, kept apart from `data` on purpose: the notes change
        # whenever Alt moves or a rating lands, the replay arrives once and is
        # a hundred kilobytes. Sharing one property would mean pushing those
        # hundred kilobytes again every time a flag turned up.
        self._addStringProperty('replay', '')
        self.onItemClick = self._addCommand('onItemClick')


class BattleResults(object):

    def __init__(self, session, lookup, flags, badges, scales, settings):
        self._session = session
        self._lookup = lookup
        self._flags = flags
        self._badges = badges
        self._scales = scales
        self._settings = settings
        self._stamps = None
        self._script = self._style = u''
        self._revision = 0
        self._holder = None
        # Which models already have their replay, or are still asking. Weak:
        # a model dies with the screen that owns it.
        self._replays = weakref.WeakKeyDictionary()
        self._alt = False

    def install(self):
        try:
            import openwg_gameface  # the injector the results model needs
        except ImportError:
            _logger.info('openwg_gameface not installed, no ratings in the battle results')
            return
        self._layout = layout_id(LAYOUT, FEATURE)
        if self._layout is None:
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
        self._want_replay(model, arena_id)
        players, _ = self._roster(arena_id)
        if players:
            wanted = [account_id for account_id, _, _, _ in players
                      if account_id and self._lookup.needs_fetch(PLAYERS, account_id)]
            if wanted:
                self._lookup.prefetch(players=wanted, on_ready=self._publish_all)
        self._publish(model)
        return view

    @staticmethod
    def _roster(arena_id):
        """([players], the per-vehicle mode key) of a battle, or ([], None).

        The two together because they come from one object that costs a
        service lookup to reach, and because a roster without its mode
        cannot be asked about tanks.
        """
        from helpers import dependency
        from skeletons.gui.battle_results import IBattleResultsService
        try:
            ctrl = dependency.instance(IBattleResultsService).getStatsCtrl(arena_id)
            if ctrl is None:
                return ([], None)
            results = ctrl.getResults()
            return (players_of(results), mode_of(results))
        except Exception:
            _logger.exception('could not read the players of battle %s', arena_id)
            return ([], None)

    def _check(self):
        """New code when a source changes, and the data again: a flag may have landed since."""
        stamps = tuple(resources.stamp(path) for path in (_SCRIPT, _REPLAY_SCRIPT, _STYLE))
        if stamps != self._stamps:
            self._stamps = stamps
            self._script = compose([
                ('battle results', resources.read(_SCRIPT).decode('utf-8')),
                ('replay tab', resources.read(_REPLAY_SCRIPT).decode('utf-8')),
            ])
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

    def _want_replay(self, model, arena_id):
        """Ask the site for this battle's replay, once, and hand it over.

        **Through Python and not from the page.** The results screen is
        Coherent Gameface, which hands a script the body of a same-origin
        response and an empty string for anything else -- measured, not
        assumed: a local file came back with its 526 characters while our own
        API came back 200 and nothing, with and without CORS. Python has no
        such limit.

        **Thinned on the way out.** `every=1` asks for one position a second
        per vehicle instead of four, which is 100 KB rather than 730. A map
        this size cannot show the difference, and the full answer is still
        what the site's own viewer gets.

        **A battle takes about a minute to reach the site**, so the first ask
        usually finds nothing. That is why this retries a few times rather
        than giving up: the screen is open for longer than that, and a tab
        that fills itself while the player reads their credits is the whole
        point. It stops asking once it has an answer, or after the last try.
        """
        state = self._replays.get(model)
        if state is not None and (state['done'] or state['tries'] >= _REPLAY_TRIES):
            return
        if state is None:
            state = {'tries': 0, 'done': False}
            self._replays[model] = state
        state['tries'] += 1
        url = '%s/api/%s/battles/%s/replay?every=%d' % (
            config.API_BASE.rstrip('/'), config.REGION, arena_id, _REPLAY_EVERY)

        def answered(response):
            code = getattr(response, 'responseCode', None)
            body = getattr(response, 'body', '') or ''
            if code != 200 or not body:
                # 404 is the ordinary case for the first minute: the battle is
                # on its way up. Anything else is worth a line, once.
                if code not in (200, 404):
                    _logger.info('replay for %s: HTTP %s', arena_id, code)
                self._session.callback(_REPLAY_RETRY, lambda: self._want_replay(model, arena_id))
                return
            state['done'] = True
            try:
                model._setString(_REPLAY, body)
            except Exception:
                _logger.debug('a results model gone before its replay', exc_info=True)

        try:
            self._session.fetch(url, answered, timeout=config.API_TIMEOUT)
        except Exception:
            _logger.exception('could not ask for the replay of %s', arena_id)

    def _want_vehicles(self, players, mode):
        """Ask for the records of the tanks on screen, once each.

        Only what is missing, and only when the reader asked for tanks at
        all: this read goes at the heaviest tables the site has, and a
        player who left the choice on the career must never pay for it.
        """
        if not self._settings.wants_vehicle(SURFACE):
            return
        pairs = [(account_id, tank_id) for account_id, _, _, tank_id in players
                 if account_id and tank_id
                 and self._lookup.needs_vehicle(account_id, tank_id, mode)]
        if pairs:
            self._lookup.prefetch(vehicles=pairs, mode=mode, on_ready=self._publish_all)

    def _publish_all(self):
        for model in list(self._models().keys()):
            self._publish(model)

    def _publish(self, model):
        models = self._models()
        arena_id, published = models.get(model, (None, None))
        if arena_id is None:
            return
        shown, means = {}, {'allies': None, 'enemies': None}
        if self._settings.shows(SURFACE):
            players, mode = self._roster(arena_id)
            entry_of = lambda account_id: self._lookup.get(PLAYERS, account_id)
            vehicle_of = lambda account_id, tank_id: self._lookup.vehicle(account_id, tank_id, mode)
            shown = decorations(players, entry_of, self._settings, self._flags,
                                self._scales, self._badges, vehicle_of)
            means = averages(players, entry_of, self._settings, self._scales)
            self._want_vehicles(players, mode)
        hidden = self._settings.alt_only('results') and not self._alt
        text = json.dumps({'hidden': hidden, 'players': shown, 'averages': means}, sort_keys=True)
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


def install(session, lookup, flags, badges, scales, settings):
    BattleResults(session, lookup, flags, badges, scales, settings).install()

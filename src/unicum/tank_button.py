"""A unicum.gg button in the hangar's vehicle menu, with links for the tank.

The row of hexagons above the crew is Gameface, so the button is a module of
our own (res/gui/gameface/mods/unicum/TankButton/) that openwg_gameface
injects into the hangar, the way skill4ltu adds its own button there:

  res_map   res/mods/configs/res_map/unicum.json declares the layout
            UnicumTankButton; openwg_gameface adds it to the client's
            resource map at startup and restarts the client once when the
            map changes
  view      a child of VehicleMenuPresenter, added through its
            _getChildComponents, with a model that carries the injection
            (gf_mod_inject), the onItemClick command, and the menu's code
  code      the injected TankButton.js only loads web/hangar/tank_menu.js
            and .css, which this module puts in the model and puts again
            when either changes on disk: the menu hot reloads like the rest
  click     the button opens a menu; an entry opens its link in the player's
            browser

Links go to https://unicum.gg/<region>/tanks/<intCD>[/<tab>]: the site
redirects an id to the tank's page, keeping the path and the query. Each
carries UTM parameters, since a page opened from another application has no
Referer. "Open build" adds the vehicle's setup as the site's `setup` token
(build.py); "Share build" copies that link instead of opening it, tagged
apart so a shared link's visits can be told from the player's own. The AI
entries do what the site's own "Open in" menu does
(apps/web/src/components/page-ai-actions.tsx in unicum-gg/unicum.gg): every
page has a Markdown twin at <path>.md, and the model is handed that, with the
setup too, which the twin renders.

Optional: without openwg_gameface, or before the client has restarted with
the layout in its resource map, there is no button and nothing else changes.

A hangar view outlives a reload of this package, so the command's handler
holds no code of it: like mods_list.py, it is eval of a string importing the
current module at click time, with the command's arguments as its locals.
Its models are kept on VehicleMenuPresenter for the same reason: a reload
finds the buttons already on screen and gives them the current code.
"""
import base64
import functools
import json
import logging
import os
import urllib
import weakref
import zlib

import BigWorld
from CurrentVehicle import g_currentVehicle
from frameworks.wulf import ViewModel
from gui.impl.gen_utils import INVALID_RES_ID
from gui.impl.lobby.hangar.presenters.vehicle_menu_presenter import VehicleMenuPresenter
from gui.impl.pub.view_component import ViewComponent

from unicum import build, config

_logger = logging.getLogger('unicum.tank_button')

FEATURE = 'UnicumTankButton'
_MODULE = 'coui://gui/gameface/mods/unicum/TankButton/TankButton.js'

_SOURCES = os.path.join(os.path.dirname(__file__), 'web', 'hangar')
_SCRIPT = os.path.join(_SOURCES, 'tank_menu.js')
_STYLE = os.path.join(_SOURCES, 'tank_menu.css')
_ICONS = os.path.join(_SOURCES, 'icons')
_ICONS_MARK = '__MENU_ICONS__'
_CHECK_SECONDS = 1.0

# Where live button models are kept across reloads of this package.
_REGISTRY = '_unicumTankButtonModels'

SITE_BASE = 'https://unicum.gg'

# Tab ids, as TankButton.js sends them, and their path on the tank's page.
TABS = {
    'specifications': '',
    'performances': '/performances',
    'marks': '/marks',
    'history': '/history',
    'videos': '/videos',
    'community': '/community',
}

# As the site builds them: the base URL and the query, with the prompt under `q`.
AI = {
    'chatgpt': ('https://chatgpt.com/', lambda q: [('hints', 'search'), ('prompt', q)]),
    'claude': ('https://claude.ai/new', lambda q: [('q', q)]),
    'scira': ('https://scira.ai/', lambda q: [('q', q)]),
}

_PROMPT = 'Read this World of Tanks stats page and help me analyze it: %s'

# The command's arguments are the eval's locals: {'item': ..., 'text': ...}.
_ON_ITEM = functools.partial(
    eval, "__import__('unicum.tank_button', None, None, ['on_item']).on_item(locals())", {})

# Property indexes; gf_mod_inject adds ModInjectModel first.
_ENABLED = 1
_REVISION = 2
_SCRIPT_TEXT = 3
_STYLE_TEXT = 4


def _utm(content):
    return 'utm_source=wot-mod&utm_medium=hangar&utm_campaign=tank-menu&utm_content=%s' % content


def tank_url(int_cd, tab='specifications', setup=None, content=None, region=config.REGION):
    """A tank page on unicum.gg, by the tank's id."""
    query = ('setup=%s&' % setup if setup else '') + _client() + _utm(content or ('build' if setup else tab))
    return '%s/%s/tanks/%d%s?%s' % (SITE_BASE, region, int_cd, TABS[tab], query)


def _client():
    """`client=ct&` on the Common Test client, whose vehicles the site keeps apart."""
    try:
        from constants import IS_CT
    except ImportError:
        return ''
    return 'client=ct&' if IS_CT else ''


def item_url(item, vehicle):
    """The link a menu entry opens for this gui Vehicle, or None for an unknown entry."""
    if item in TABS:
        return tank_url(vehicle.intCD, item)
    if item in ('build', 'share'):
        content = 'share-build' if item == 'share' else 'build'
        return tank_url(vehicle.intCD, setup=build.setup_token(vehicle), content=content)
    if item in AI:
        base, query = AI[item]
        page = markdown_url(vehicle.intCD, build.setup_token(vehicle))
        return '%s?%s' % (base, urllib.urlencode(query(_PROMPT % page)))
    return None


def markdown_url(int_cd, setup=None, region=config.REGION):
    """The tank page's Markdown twin, which the site serves for an id as for a slug."""
    return '%s/%s/tanks/%d.md%s' % (SITE_BASE, region, int_cd, '?setup=%s' % setup if setup else '')


def on_item(args):
    """A message from the menu: an entry picked, or a line for the log."""
    item = args.get('item') if isinstance(args, dict) else None
    if item == 'log':
        _logger.info('menu: %s', args.get('text'))
        return
    open_item(item)


def open_item(item):
    """What a menu entry does: its link for the selected tank, in the browser."""
    if not g_currentVehicle.isPresent():
        _logger.info('no tank selected, nothing to open')
        return
    url = item_url(item, g_currentVehicle.item)
    if url is None:
        _logger.warning('unknown tank menu entry %r', item)
        return
    if item == 'share':
        _share(url)
        return
    _logger.info('opening %s', url)
    BigWorld.wg_openWebBrowser(url)


def _share(url):
    """The build link in the clipboard, and a system message saying so."""
    from gui import SystemMessages
    from gui.shared.notifications import NotificationPriorityLevel
    from gui.shared.utils import copyToClipboard
    copyToClipboard(url)
    _logger.info('copied %s', url)
    # Medium, as the game's own information messages: without a priority the
    # message only lands in the notification centre, with no popup.
    SystemMessages.pushMessage(u'unicum.gg: build link copied to the clipboard.',
                               type=SystemMessages.SM_TYPE.Information,
                               priority=NotificationPriorityLevel.MEDIUM)


class TankButtonModel(ViewModel):
    __slots__ = ('onItemClick', )

    def __init__(self, properties=5, commands=1):
        super(TankButtonModel, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(TankButtonModel, self)._initialize()
        from openwg_gameface import gf_mod_inject
        gf_mod_inject(self, FEATURE, modules=[_MODULE])
        self._addBoolProperty('enabled', True)
        self._addNumberProperty('revision', 0)
        self._addStringProperty('script', '')
        self._addStringProperty('style', '')
        self.onItemClick = self._addCommand('onItemClick')


class TankButton(object):

    def __init__(self, session, settings):
        self._session = session
        self._settings = settings
        self._stamps = None
        self._revision = 0
        self._script = self._style = ''

    def install(self):
        try:
            from openwg_gameface import res_id_by_key
        except ImportError:
            _logger.info('openwg_gameface not installed, no tank page button')
            return
        self._layout = res_id_by_key(FEATURE)
        if self._layout == INVALID_RES_ID:
            _logger.info('%s not in the resource map yet; there is a button after the next client start',
                         FEATURE)
            return
        self._session.patch(VehicleMenuPresenter, '_getChildComponents', self._wrap)
        self._settings.on_change(self._on_settings)
        self._check_sources()
        self._session.repeat(_CHECK_SECONDS, self._check_sources)
        _logger.info('installed in the hangar vehicle menu')

    @staticmethod
    def _models():
        models = getattr(VehicleMenuPresenter, _REGISTRY, None)
        if models is None:
            models = weakref.WeakSet()
            setattr(VehicleMenuPresenter, _REGISTRY, models)
        return models

    def _check_sources(self):
        """Put the menu's code in every button when it or its icons change on disk."""
        icons = sorted(os.path.join(_ICONS, name) for name in os.listdir(_ICONS)
                       if name.endswith('.png')) if os.path.isdir(_ICONS) else []
        paths = [_SCRIPT, _STYLE] + icons
        stamps = tuple((path, os.path.getmtime(path)) for path in paths if os.path.isfile(path))
        if stamps == self._stamps:
            return
        self._stamps = stamps
        with open(_SCRIPT, 'rb') as handle:
            self._script = handle.read().decode('utf-8').replace(_ICONS_MARK, json.dumps(_data_uris(icons)))
        with open(_STYLE, 'rb') as handle:
            self._style = handle.read().decode('utf-8')
        # From the content, not the files' times: the icons can change what
        # the script says while its own file stays untouched.
        self._revision = zlib.crc32((self._script + self._style).encode('utf-8')) & 0x3fffffff
        for model in list(self._models()):
            self._load_code(model)

    def _load_code(self, model):
        try:
            model._setString(_SCRIPT_TEXT, self._script)
            model._setString(_STYLE_TEXT, self._style)
            model._setNumber(_REVISION, self._revision)
        except Exception:
            _logger.exception('could not update a tank menu button')

    def _wrap(self, original):

        def _getChildComponents(presenter):
            children = dict(original(presenter))
            children[self._layout] = self._make_view
            return children

        return _getChildComponents

    def _make_view(self):
        view = ViewComponent(layoutID=self._layout, model=TankButtonModel)
        model = view.getViewModel()
        model._setBool(_ENABLED, self._settings.shows_tank_button())
        self._load_code(model)
        model.onItemClick += _ON_ITEM
        self._models().add(model)
        return view

    def _on_settings(self):
        shown = self._settings.shows_tank_button()
        for model in list(self._models()):
            try:
                model._setBool(_ENABLED, shown)
            except Exception:
                _logger.exception('could not update a tank page button')


def _data_uris(paths):
    """{name: data URI} for the menu's own icons, inlined in its script."""
    uris = {}
    for path in paths:
        with open(path, 'rb') as handle:
            uris[os.path.splitext(os.path.basename(path))[0]] = 'data:image/png;base64,' + base64.b64encode(handle.read())
    return uris


def install(session, settings):
    TankButton(session, settings).install()

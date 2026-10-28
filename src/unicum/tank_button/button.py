"""The button itself, where the client draws it.

A Gameface view and its model, plus the icons, which travel as data URIs
because a file added to a folder the client did not have at startup is not
served.
"""
from __future__ import absolute_import

import base64
import functools
import json
import logging
import os
import weakref
import zlib

from frameworks.wulf import ViewModel
from gui.impl.lobby.hangar.presenters.vehicle_menu_presenter import VehicleMenuPresenter
from gui.impl.pub.view_component import ViewComponent
from unicum import config, resources
from unicum.layouts import layout_id
from unicum.tank_button.sharing import compose, on_item

_logger = logging.getLogger('unicum.tank_button.button')

FEATURE = 'UnicumTankButton'
# Where client 2.4.1.0 publishes the same layout, from
# res/gui/gen_resources/unicum.json. See unicum/layouts.py.
LAYOUT = 'R.mods.unicum.TankButton.views.UnicumTankButton'
_MODULE = 'coui://gui/gameface/mods/unicum/TankButton/TankButton.js'

# Package resources (resources.py): beside the code in development, inside the .wotmod once released.
_SOURCES = 'web/hangar'
_SCRIPT = _SOURCES + '/tank_menu.js'
_STYLE = _SOURCES + '/tank_menu.css'
_PANEL_SCRIPT = _SOURCES + '/twitch_panel.js'
_PANEL_STYLE = _SOURCES + '/twitch_panel.css'
_CARD_SCRIPT = _SOURCES + '/account_card.js'
_CARD_STYLE = _SOURCES + '/account_card.css'
_ICONS = _SOURCES + '/icons'
_ICONS_MARK = '__MENU_ICONS__'
_PANEL_ICONS = _SOURCES + '/panel_icons'
_PANEL_ICONS_MARK = '__PANEL_ICONS__'
_CHECK_SECONDS = 1.0

# Where live button models are kept across reloads of this package.
_REGISTRY = '_unicumTankButtonModels'

# The command's arguments are the eval's locals: {'item': ..., 'text': ...}.
_ON_ITEM = functools.partial(
    eval, "__import__('unicum.tank_button', None, None, ['on_item']).on_item(locals())", {})

# Property indexes; gf_mod_inject adds ModInjectModel first.
_ENABLED = 1
_REVISION = 2
_SCRIPT_TEXT = 3
_STYLE_TEXT = 4
_TWITCH = 5

def set_twitch(model, text):
    """Hand the Twitch panel its state; False on a model older than the property."""
    try:
        model._setString(_TWITCH, text)
        return True
    except Exception:
        _logger.debug('a loader model without the twitch property', exc_info=True)
        return False

def live_models():
    """The loader models on screen, including those made by an earlier load of this package."""
    models = getattr(VehicleMenuPresenter, _REGISTRY, None)
    return list(models) if models is not None else []

def panel_sources():
    """The files the Twitch panel is made of, to tell when it changed."""
    return [_PANEL_SCRIPT, _PANEL_STYLE] + _pngs(_PANEL_ICONS)

def panel_code():
    """The Twitch panel alone, as a loader runs it: (script, style)."""
    panel = _read(_PANEL_SCRIPT).replace(_PANEL_ICONS_MARK, json.dumps(_data_uris(_pngs(_PANEL_ICONS))))
    return compose([('twitch panel', panel)]), _read(_PANEL_STYLE)

class TankButtonModel(ViewModel):
    __slots__ = ('onItemClick', )

    def __init__(self, properties=6, commands=1):
        super(TankButtonModel, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(TankButtonModel, self)._initialize()
        from openwg_gameface import gf_mod_inject
        gf_mod_inject(self, FEATURE, modules=[_MODULE])
        self._addBoolProperty('enabled', True)
        self._addNumberProperty('revision', 0)
        self._addStringProperty('script', '')
        self._addStringProperty('style', '')
        self._addStringProperty('twitch', '')
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
            import openwg_gameface  # the injector TankButtonModel needs
        except ImportError:
            _logger.info('openwg_gameface not installed, no tank page button')
            return
        self._layout = layout_id(LAYOUT, FEATURE)
        if self._layout is None:
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
        icons = _pngs(_ICONS)
        panel_icons = _pngs(_PANEL_ICONS)
        paths = [_SCRIPT, _STYLE, _PANEL_SCRIPT, _PANEL_STYLE, _CARD_SCRIPT, _CARD_STYLE] + icons + panel_icons
        # Inside a release every stamp is None, and the code is read once.
        stamps = tuple((path, resources.stamp(path)) for path in paths)
        if stamps == self._stamps:
            return
        self._stamps = stamps
        menu = _read(_SCRIPT).replace(_ICONS_MARK, json.dumps(_data_uris(icons)))
        uris = json.dumps(_data_uris(panel_icons))
        panel = _read(_PANEL_SCRIPT).replace(_PANEL_ICONS_MARK, uris)
        card = _read(_CARD_SCRIPT).replace(_PANEL_ICONS_MARK, uris)
        self._script = compose([('tank menu', menu)] + [(name, script) for name, script in
                                                        (('account card', card), ('twitch panel', panel)) if script])
        self._style = u'\n'.join((_read(_STYLE), _read(_CARD_STYLE), _read(_PANEL_STYLE)))
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
            children = original(presenter)
            try:
                children = dict(children)
                children[self._layout] = self._make_view
            except Exception:
                _logger.exception('could not add the tank menu button')
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

def _pngs(folder):
    return ['%s/%s' % (folder, name) for name in resources.listdir(folder) if name.endswith('.png')]

def _read(path):
    data = resources.read(path)
    return data.decode('utf-8') if data is not None else u''

def _data_uris(paths):
    """{name: data URI} for the menu's own icons, inlined in its script."""
    uris = {}
    for path in paths:
        data = resources.read(path)
        if data is not None:
            uris[path.rsplit('/', 1)[-1][:-len('.png')]] = 'data:image/png;base64,' + base64.b64encode(data)
    return uris

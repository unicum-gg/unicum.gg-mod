"""HTML window titles, by way of a small AS3 view loaded into the lobby.

The profile window's title is plain text, and the switch that makes a Window
render HTML is on the AS3 Window object, which the GFx proxy does not hand to
Python (see lobby.LobbyFlags._wrap_profile). as3/src/unicum/TitleHtml.as
flips that switch for every profile window; this module gets it loaded.

The view is registered under the game's own View class and lives in the
global scope, so it survives reloads of this package without holding any of
its code: a reload finds it already registered and already loaded, and does
nothing. It is only gone when the lobby app is, and the next lobby app
initialization loads it again.

Whether titles may carry markup is decided here too, because the two halves
must agree: a flag sent to a title that is still plain text shows its <IMG>
tag as text.
"""
import logging

import ResMgr
from frameworks.wulf import WindowLayer
from gui.app_loader.settings import APP_NAME_SPACE
from gui.Scaleform.framework import ScopeTemplates, ViewSettings, g_entitiesFactories
from gui.Scaleform.framework.entities.View import View, ViewKey
from gui.Scaleform.framework.managers.loaders import SFViewLoadParams
from gui.shared import EVENT_BUS_SCOPE, events, g_eventBus
from helpers import dependency
from skeletons.gui.app_loader import IAppLoader
from skeletons.gui.impl import IGuiLoader

_logger = logging.getLogger('unicum.titles')

ALIAS = 'unicumTitleHtml'
SWF = 'unicum.titles.swf'
SWF_RES_PATH = 'gui/flash/' + SWF


def html_titles():
    """Whether the profile title renders markup.

    True when the SWF is in the resource tree and registered. A title can
    still be drawn in the moment before the view finishes loading at login,
    but no profile window is open that early.
    """
    return ResMgr.isFile(SWF_RES_PATH) and g_entitiesFactories.getSettings(ALIAS) is not None


class TitleHtml(object):

    def __init__(self, session):
        self._session = session

    def install(self):
        if not ResMgr.isFile(SWF_RES_PATH):
            _logger.warning('%s not in the resource tree; profile titles keep '
                            'a language code (build with tools/build_as3.py)',
                            SWF_RES_PATH)
            return
        if g_entitiesFactories.getSettings(ALIAS) is None:
            g_entitiesFactories.addSettings(ViewSettings(
                ALIAS, View, SWF, WindowLayer.SERVICE_LAYOUT, None,
                ScopeTemplates.GLOBAL_SCOPE))
        g_eventBus.addListener(events.AppLifeCycleEvent.INITIALIZED,
                               self._on_app_initialized, EVENT_BUS_SCOPE.GLOBAL)
        self._session.on_close(self._remove_listener)
        self._load(dependency.instance(IAppLoader).getApp(APP_NAME_SPACE.SF_LOBBY))
        _logger.info('installed, html titles=%s', html_titles())

    def _remove_listener(self):
        g_eventBus.removeListener(events.AppLifeCycleEvent.INITIALIZED,
                                  self._on_app_initialized, EVENT_BUS_SCOPE.GLOBAL)

    def _on_app_initialized(self, event):
        if event.ns != APP_NAME_SPACE.SF_LOBBY:
            return
        self._load(dependency.instance(IAppLoader).getApp(event.ns))

    def _load(self, app):
        manager = getattr(app, 'containerManager', None) if app is not None else None
        if manager is None:
            return
        if manager.getViewByKey(ViewKey(ALIAS)) is not None:
            return
        loader = dependency.instance(IGuiLoader)
        windows = getattr(loader, 'windowsManager', None)
        parent = windows.getMainWindow() if windows is not None else None
        app.loadView(SFViewLoadParams(ALIAS, parent=parent))
        _logger.info('title view loading into the lobby')


def install(session):
    TitleHtml(session).install()

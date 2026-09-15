"""Small AS3 views loaded into the lobby and the battle, where Python cannot reach.

What they do lives on AS3 objects the GFx proxy does not hand to Python:

  LobbyView.as      into the lobby, made of
    TitleHtml.as    the profile window title renders HTML
                    (Window.titleUseHtml), see lobby.LobbyFlags._wrap_profile
    RoomTools.as    the skirmish room's members sort dropdown and average
                    WNX, see room_sort.py and lobby.py
  TeamNamesHtml.as  into the battle: team names set with TextField.text
                    render HTML, see battle.BattleFlags._mark_teams
    VehicleMarkers.as  ratings and flags by the vehicle icons, see
                    battle.BattleFlags._publish

One view per app: they load into the app's service layer, a single-view
container where loading a second view destroys the first.

Each view is registered under the game's own View class and lives in the
global scope, so it survives reloads of this package without holding any of
its code: a reload finds it registered and loaded, and does nothing. It is
gone with its app, and the next initialisation of that app loads it again.

Whether a field may carry markup is decided here too, because both halves
must agree: an <IMG> sent to a field still in plain text shows as written.

AS3 hot reload: a view whose SWF changes on disk is destroyed and loaded
again, which picks up the new code without a client restart. Only for a SWF
that existed when the client started: ResMgr indexes the resource tree then,
and a file added later stays invisible until the next start.
"""
import logging
import os

import ResMgr
from frameworks.wulf import WindowLayer, WindowStatus
from gui.app_loader.settings import APP_NAME_SPACE
from gui.Scaleform.framework import ScopeTemplates, ViewSettings, g_entitiesFactories
from gui.Scaleform.framework.entities.View import View
from gui.Scaleform.framework.entities.sf_window import SFWindow
from gui.Scaleform.framework.managers.loaders import SFViewLoadParams
from gui.shared import EVENT_BUS_SCOPE, events, g_eventBus
from helpers import dependency
from skeletons.gui.app_loader import IAppLoader
from skeletons.gui.impl import IGuiLoader

from unicum import config

_logger = logging.getLogger('unicum.views')


_GONE = (WindowStatus.DESTROYING, WindowStatus.DESTROYED)


class SwfView(object):

    def __init__(self, alias, swf, app_ns, lacking):
        self.alias = alias
        self.swf = swf
        self.app_ns = app_ns
        self._lacking = lacking   # what the user loses without it, for the log

    @property
    def res_path(self):
        return 'gui/flash/' + self.swf

    def available(self):
        """In the resource tree and registered: loadable this session."""
        return ResMgr.isFile(self.res_path) and g_entitiesFactories.getSettings(self.alias) is not None

    def windows(self):
        """This view's live windows.

        Asked of the windows manager, not the container manager: a service
        view opens as an SFWindow, and getViewByKey only sees it while it is
        still loading.
        """
        windows = getattr(dependency.instance(IGuiLoader), 'windowsManager', None)
        if windows is None:
            return []
        return windows.findWindows(lambda w: isinstance(w, SFWindow) and
                                   w.loadParams.viewKey.alias == self.alias and
                                   w.windowStatus not in _GONE)

    def loaded(self):
        """Loaded into its app right now."""
        return bool(self.windows())

    def register(self):
        if not ResMgr.isFile(self.res_path):
            _logger.warning('%s not in the resource tree; %s (build with tools/build_as3.py)',
                            self.res_path, self._lacking)
            return False
        if g_entitiesFactories.getSettings(self.alias) is None:
            g_entitiesFactories.addSettings(ViewSettings(
                self.alias, View, self.swf, WindowLayer.SERVICE_LAYOUT, None,
                ScopeTemplates.GLOBAL_SCOPE))
        return True

    def stamp(self):
        """The SWF's modification time on disk, or None."""
        path = config.res_mods_file(self.res_path)
        try:
            return os.path.getmtime(path) if path else None
        except OSError:
            return None

    def unload(self):
        """Destroy every live window of this view; True if there was one."""
        found = self.windows()
        for window in found:
            window.destroy()
        return bool(found)

    def load(self, app):
        manager = getattr(app, 'containerManager', None) if app is not None else None
        if manager is None or self.loaded():
            return
        parent = None
        if self.app_ns == APP_NAME_SPACE.SF_LOBBY:
            windows = getattr(dependency.instance(IGuiLoader), 'windowsManager', None)
            parent = windows.getMainWindow() if windows is not None else None
        app.loadView(SFViewLoadParams(self.alias, parent=parent))
        _logger.info('%s loading', self.alias)


LOBBY = SwfView('unicumLobby', 'unicum.lobby.swf', APP_NAME_SPACE.SF_LOBBY,
                'profile titles keep a language code, no members sort nor detachment average')
BATTLE = SwfView('unicumBattle', 'unicum.battle.swf', APP_NAME_SPACE.SF_BATTLE,
                 'no ratings by the vehicle icons, team averages stay plain numbers')


def html_titles():
    """Whether the profile title renders markup.

    A title can be drawn in the moment before the view finishes loading at
    login, but no profile window is open that early.
    """
    return LOBBY.available()


def lobby_view():
    """The loaded lobby view's flash object, or None."""
    if not LOBBY.available():
        return None
    for window in LOBBY.windows():
        view = getattr(window, 'content', None)
        if getattr(view, 'flashObject', None) is not None:
            return view.flashObject
    return None


def battle_view():
    """The loaded battle view's flash object, or None."""
    if not BATTLE.available():
        return None
    for window in BATTLE.windows():
        view = getattr(window, 'content', None)
        if getattr(view, 'flashObject', None) is not None:
            return view.flashObject
    return None


def html_team_names():
    """Whether this battle's team names render markup: its view is loaded."""
    return BATTLE.available() and BATTLE.loaded()


_WATCH_SECONDS = 1.0

# A destroyed view leaves its container over the next frames; loading again
# before that finds it still there and does nothing.
_RELOAD_DELAY = 0.5


class Views(object):

    def __init__(self, session):
        self._session = session
        self._views = [view for view in (LOBBY, BATTLE) if view.register()]
        self._stamps = dict((view.alias, view.stamp()) for view in self._views)

    def install(self):
        if not self._views:
            return
        g_eventBus.addListener(events.AppLifeCycleEvent.INITIALIZED,
                               self._on_app_initialized, EVENT_BUS_SCOPE.GLOBAL)
        self._session.on_close(self._remove_listener)
        loader = dependency.instance(IAppLoader)
        for view in self._views:
            view.load(loader.getApp(view.app_ns))
        self._session.repeat(_WATCH_SECONDS, self._watch)
        _logger.info('installed %s', [view.alias for view in self._views])

    def _watch(self):
        loader = dependency.instance(IAppLoader)
        for view in self._views:
            stamp = view.stamp()
            if stamp != self._stamps.get(view.alias):
                self._stamps[view.alias] = stamp
                if view.unload():
                    _logger.info('%s changed on disk, reloading its view', view.swf)
                    self._session.callback(_RELOAD_DELAY, lambda v=view: v.load(
                        dependency.instance(IAppLoader).getApp(v.app_ns)))

    def _remove_listener(self):
        g_eventBus.removeListener(events.AppLifeCycleEvent.INITIALIZED,
                                  self._on_app_initialized, EVENT_BUS_SCOPE.GLOBAL)

    def _on_app_initialized(self, event):
        for view in self._views:
            if event.ns == view.app_ns:
                view.load(dependency.instance(IAppLoader).getApp(event.ns))


def install(session):
    Views(session).install()

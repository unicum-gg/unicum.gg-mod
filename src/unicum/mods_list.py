"""An entry for the mod in poliroid's modsListApi menu ("Open settings").

Optional, like the settings window: without gui.modsListApi this does nothing.
modsSettingsApi lists itself there, not the mods whose pages it holds, so a
mod with settings only shows in that menu if it adds itself.

Clicking it opens the settings window on the mod's page, with whichever
window is installed, tried in this order:

  Aslain's Mod Menu   selects the page (setWindowSelectedMod) and loads its
                      window in settings mode (view.loadView). Not through
                      button._openMenuDirect: that reopens the last entry
                      clicked in the menu, which is this one, so the two
                      called each other.
  izeberg's window    opens it (view.loadView); it has no page to select,
                      every mod is on one scrolling page
  anything else       calls modsSettingsApi's own entry in the menu

The icon is a resource file (config.ICON_RES_PATH), indexed when the client
starts; modsListApi draws its default icon when the file is not there.

The entry is removed when the session closes and added again by the next
one, but the menu does not always let go of a callback: after a reload, a
click reached the previous generation's method, whose module globals were
already None. So the callback holds no code of this package. It is eval, a
builtin, with a source string that imports the current module at click time.
"""
import functools
import logging
import time

import BigWorld

from unicum import config
from unicum.settings_window import LINKAGE

_logger = logging.getLogger('unicum.mods_list')

# Not the settings page's linkage: the Mod Menu keeps menu entries and
# settings pages in step by id, and an entry that opens its own page under
# the same id is one more way for the two to trigger each other.
MOD_ID = 'gg.unicum.menu'

# Opening again this soon after the last time is ignored, so no chain of
# callbacks, whatever starts it, can reopen the window in a loop.
_REOPEN_SECONDS = 2.0
_last_open = [0.0]

# modsSettingsApi's id for its own entry.
_SETTINGS_ENTRY = 'modsSettingsApi'

# Its own empty globals: BigWorld runs callbacks without a frame, and eval
# has none to borrow then. __import__ still comes from the builtins.
_CALLBACK = functools.partial(
    eval, "__import__('unicum.mods_list', None, None, ['open_settings']).open_settings()", {})
_OPEN_NOW = functools.partial(
    eval, "__import__('unicum.mods_list', None, None, ['open_now']).open_now()", {})

# The menu the entry sits in is itself one of the Mod Menu's windows, still
# open when the click arrives, and the Mod Menu ignores an open request while
# it has a window up. So the window opens a moment later, once it has closed.
_OPEN_DELAY = 0.5


class ModsListEntry(object):

    def __init__(self, session):
        self._session = session
        self._api = None

    def install(self):
        try:
            from gui.modsListApi import g_modsListApi
        except ImportError:
            _logger.info('modsListApi not installed, no menu entry')
            return
        self._api = g_modsListApi
        g_modsListApi.addModification(
            id=MOD_ID, name='unicum.gg',
            description='Language flags and ratings from unicum.gg',
            icon=config.ICON_RES_PATH, enabled=True, login=False, lobby=True,
            callback=_CALLBACK)
        self._session.on_close(self._remove)
        _logger.info('added to modsListApi as %s', MOD_ID)

    def _remove(self):
        try:
            self._api.removeModification(MOD_ID)
        except Exception:
            _logger.exception('could not remove the modsListApi entry')


def open_settings():
    """What the entry does: open the settings window, once its menu has closed."""
    now = time.time()
    if now - _last_open[0] < _REOPEN_SECONDS:
        return
    _last_open[0] = now
    BigWorld.callback(_OPEN_DELAY, _OPEN_NOW)


def open_now():
    """Open the settings window on the mod's page."""
    for opener in (_open_aslain, _open_izeberg, _open_settings_entry):
        try:
            if opener():
                _logger.info('settings window opened with %s', opener.__name__)
                return
        except Exception:
            _logger.exception('could not open the settings window with %s', opener.__name__)
    _logger.warning('no settings window to open')


def _open_aslain():
    try:
        from gui import aslainMenu
        from gui.aslainMenu import view
    except ImportError:
        return False
    api = getattr(aslainMenu, 'g_modsSettingsApi', None)
    load_view = getattr(view, 'loadView', None)
    if api is None or load_view is None:
        return False
    if hasattr(api, 'canOpenWindow') and not api.canOpenWindow():
        _logger.info('Mod Menu says it cannot open now')
        return False
    if hasattr(api, 'setWindowSelectedMod'):
        api.setWindowSelectedMod(LINKAGE)
    load_view(api, picker=False)
    return True


def _open_izeberg():
    try:
        from gui.modsSettingsApi import g_modsSettingsApi
        from gui.modsSettingsApi.view import loadView
    except ImportError:
        return False
    # The public object wraps the one loadView takes.
    internal = getattr(g_modsSettingsApi, '_ModsSettingsApi__instance', None)
    if internal is None:
        return False
    loadView(internal)
    return True


def _open_settings_entry():
    try:
        from gui.modsListApi.controller import g_controller
    except ImportError:
        return False
    entry = g_controller.modifications.get(_SETTINGS_ENTRY)
    callback = getattr(entry, '_ModificationItem__callback', None)
    if callback is None:
        return False
    callback()
    return True


def install(session):
    ModsListEntry(session).install()

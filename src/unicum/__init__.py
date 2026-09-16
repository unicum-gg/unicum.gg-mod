"""Entry point for the reloadable half of the mod.

The client only ever loads `mod_unicum_dev.py` from its res_mods folder.
That stub calls start() and stop() here and reimports this package whenever
a source file under src/ changes, which is what lets the game stay running
across edits.

Both functions must be safe to call at any time and in any order: a reload
is nothing more than stop() followed by a fresh start().
"""
import logging

from unicum import (auto_reload, battle, browser, config, lobby, mods_list, room_sort, settings_window, tank_button,
                    twitch, views)
from unicum.badges import Badges
from unicum.api.resolve import Lookup
from unicum.api.scales import RatingScales
from unicum.runtime.session import Session
from unicum.settings import Settings
from unicum.textures import FlagCache

VERSION = '0.1.0-dev'

_logger = logging.getLogger('unicum')

_session = None


def start(generation=0):
    """Install everything the mod owns. Idempotent by way of stop()."""
    global _session
    if _session is not None:
        stop()
    _session = Session(generation)
    _logger.info('start: version=%s generation=%s', VERSION, generation)
    try:
        # One of each, shared by every surface. Each feature used to build
        # its own lookup, and every one of them loaded languages.json and
        # wrote it back: whichever saved last dropped what the others had
        # learned that session.
        settings = Settings(_session)
        settings.install()
        settings_window.install(_session, settings)
        mods_list.install(_session)
        lookup = Lookup(_session, config.REGION)
        scales = RatingScales(_session)
        flags = FlagCache(_session)
        badges = Badges()
        browser.install(_session, lookup, flags, scales, settings)
        battle.install(_session, lookup, flags, badges, settings)
        views.install(_session)
        lobby.install(_session, lookup, flags, badges, settings)
        room_sort.install(_session, settings)
        tank_button.install(_session, settings)
        auto_reload.install(_session, settings)
        twitch.install(_session, settings)
    except Exception:
        # A feature that fails halfway leaves the ones before it installed.
        # Without this the session is orphaned: the loader sees start() fail
        # and forgets the module, so the next reload has nothing to call
        # stop() on, the package is purged, and the surviving patches are
        # left pointing at torn-down module globals. Undo, then report.
        _logger.exception('start failed, rolling back')
        stop()
        raise


def stop():
    """Release everything the current session owns."""
    global _session
    if _session is None:
        return
    _logger.info('stop: generation=%s', _session.generation)
    try:
        _session.close()
    finally:
        _session = None

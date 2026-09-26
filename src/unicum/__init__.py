"""Entry point for the reloadable half of the mod.

The client only ever loads `mod_unicum_dev.py` from its res_mods folder.
That stub calls start() and stop() here and reimports this package whenever
a source file under src/ changes, which is what lets the game stay running
across edits.

Both functions must be safe to call at any time and in any order: a reload
is nothing more than stop() followed by a fresh start().
"""
import logging

from unicum import (auto_reload, battle, battle_results, browser, config, context_menu, first_run, loadouts, lobby,
                    mods_list, reporting, room_sort, settings_tab, settings_window, tank_button, twitch,
                    twitch_panel, twitch_send, twitch_window, views)
from unicum.badges import Badges
from unicum.game_link import GameLink
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
    # Before anything else installs: a feature that fails on the way up is
    # exactly what an author never hears about otherwise.
    reporting.install(_session, VERSION)
    # Before any feature that draws: a folder made now is not in the client's
    # index, so nothing written into it can be drawn until the client starts
    # again. Asking for that restart is the whole point.
    _restart_after_first_run(first_run.prepare())
    try:
        # One of each, shared by every surface. Each feature used to build
        # its own lookup, and every one of them loaded languages.json and
        # wrote it back: whichever saved last dropped what the others had
        # learned that session.
        settings = Settings(_session)
        settings.install()
        link = GameLink(_session)
        link.install()
        window = settings_window.install(_session, settings, link)
        tab = settings_tab.install(_session, settings, link)
        mods_list.install(_session)
        lookup = Lookup(_session, config.REGION)
        scales = RatingScales(_session)
        flags = FlagCache(_session)
        badges = Badges(scales)
        # One reader of the extended info key for every surface that can wait
        # for it: the battle screens, the skirmish room and the stronghold.
        from unicum.extended_info import ExtendedInfo
        alt = ExtendedInfo(_session)
        alt.install()
        browser.install(_session, lookup, flags, scales, settings, alt)
        battle.install(_session, lookup, flags, badges, settings, alt)
        battle_results.install(_session, lookup, flags, scales, settings)
        views.install(_session)
        lobby.install(_session, lookup, flags, badges, settings, alt)
        room_sort.install(_session, settings)
        tank_button.install(_session, settings)
        context_menu.install(_session, settings)
        loadouts.install(_session, settings, link)
        auto_reload.install(_session, settings)
        chat = twitch.install(_session, settings, link)
        window.follow_twitch(chat)
        tab.follow_twitch(chat)
        sender = twitch_send.install(_session, link, chat)
        twitch_panel.install(_session, settings, chat, link, sender)
        twitch_window.install(_session, settings, chat, link)
    except Exception:
        # A feature that fails halfway leaves the ones before it installed.
        # Without this the session is orphaned: the loader sees start() fail
        # and forgets the module, so the next reload has nothing to call
        # stop() on, the package is purged, and the surviving patches are
        # left pointing at torn-down module globals. Undo, then report.
        _logger.exception('start failed, rolling back')
        stop()
        raise


def _restart_after_first_run(made):
    """Restart straight away when a folder was just created.

    Here rather than at the garage, which is where this waited first: the mod
    loads while the client is still starting, so restarting now throws away a
    few seconds, where waiting for `onAccountShowGUI` throws away a sign-in
    and a full garage load as well. `restart_if_idle` is what keeps that safe,
    by refusing whenever the client already has a player.
    """
    if not made:
        return
    _logger.info('image folders created; restarting so the client indexes them')
    first_run.restart_if_idle()


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

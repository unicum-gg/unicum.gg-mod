"""Entry point for the reloadable half of the mod.

The client only ever loads `mod_unicum_dev.py` from its res_mods folder.
That stub calls start() and stop() here and reimports this package whenever
a source file under src/ changes, which is what lets the game stay running
across edits.

Both functions must be safe to call at any time and in any order: a reload
is nothing more than stop() followed by a fresh start().
"""
import logging

from unicum import battle, browser, lobby
from unicum.runtime.session import Session

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
        browser.install(_session)
        battle.install(_session)
        lobby.install(_session)
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

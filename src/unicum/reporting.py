"""Hand the mod's own errors to an error reporter, when the player has one.

The mod logs what it catches (`_logger.exception`) and carries on, which keeps
the game running but leaves the author with nothing: a player who never opens
python.log never reports anything either. Wargaming's mod hub has a reporter for
that, `gui.mods.mod_error_reporter` (Gravity's), which sends a mod's exceptions
to a dashboard its author is given access to.

It finds the mod at fault by walking the traceback for a module named
`gui.mods.mod_*`, so it sees nothing of ours: every error of this mod is raised
inside the `unicum` package, and only the entry point (`mod_unicum`) lives under
gui/mods. So the reporter is told directly instead, through the public
`report_exception` it offers other mods, by listening to this package's own
logger: every ERROR record carrying an exception is handed over, named after the
entry module the client loaded, with this package's version.

Nothing is bundled and nothing is required: without that reporter installed,
this module finds nothing and the mod behaves exactly as before. What leaves is
what the reporter publishes (api.wot-tools.dev/error_logs/privacy.php): the
mod's name and version, the client's, the exception and its traceback, and an
anonymous install id of the reporter's own. Since a traceback is sent as it is,
nothing in this mod may log a secret: the account link's key is never written to
the log, and must not be.
"""
import logging

_logger = logging.getLogger('unicum.reporting')

# The reporter, installed by the player or not.
_REPORTER = 'gui.mods.mod_error_reporter'

# Our own entry points: the released one, and the development bootstrap.
_ENTRIES = ('gui.mods.mod_unicum', 'gui.mods.mod_unicum_dev')

# What the reporter is told the error came from, for its dashboard.
_SOURCE = 'unicum-logger'


def reporter():
    """The reporter's module when the player has it, else None."""
    import sys
    return sys.modules.get(_REPORTER)


def entry_name():
    """The name of this mod as the reporter knows it, or '' before it is loaded."""
    import sys
    for name in _ENTRIES:
        if name in sys.modules:
            return name
    return ''


class _Handler(logging.Handler):
    """Every error of this mod's loggers that carries an exception."""

    def __init__(self, version):
        logging.Handler.__init__(self, logging.ERROR)
        self._version = version

    def emit(self, record):
        try:
            if not record.exc_info:
                return
            module = reporter()
            name = entry_name()
            if module is None or not name:
                return
            module.report_exception(name, self._version, record.exc_info,
                                    {'logger': record.name, 'message': record.getMessage()[:500]},
                                    _SOURCE)
        except Exception:
            # Reporting must never be what breaks a session; and never log
            # through this handler's own logger, which would loop.
            self.handleError(record)


def install(session, version):
    """Report this package's logged exceptions for as long as the session lives."""
    handler = _Handler(version)
    package = logging.getLogger('unicum')
    package.addHandler(handler)
    session.on_close(lambda: package.removeHandler(handler))
    _logger.info('errors are reported when %s is installed', _REPORTER)

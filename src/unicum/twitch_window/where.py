"""Whether the chat window is wanted, and what the client is doing.

The window mostly follows the player rather than a setting: it belongs in the
garage and in the queue, and on the loading screen that follows them, because
there it stands in for the garage panel the queue screen took away. Whether it
also stays over the battle itself is the one part the player chooses
(settings twitch.battle, 'window' or 'both'), and it is a separate question
from the garage panel, so the two gates are asked separately below.

The client says where the player is in half a dozen ways, none of them a
single flag, so this is the file that turns those into one question with one
answer.

A mixin, for the reason the battles package gives: the window handle and the
last state are shared with the half that draws it.
"""
from __future__ import absolute_import

import logging
import time

_logger = logging.getLogger('unicum.twitch_window.where')

# The lobby state every battle queue sits under (gui/Scaleform/daapi/view/
# lobby/battle_queue/states.py): the common queue, the strongholds' and the
# map training's.
_QUEUE_CONTAINER = 'battleQueue'

# How long the window may wait, once in a queue was asked for, for the lobby
# to show the queue screen; once the queue is left, for the garage panel to
# be back.
_ENTER_SECONDS = 3.0
_LEAVE_SECONDS = 5.0

def _in_lobby():
    """Whether the player is in the lobby, not in a battle nor on the way to one."""
    import BigWorld
    from Account import PlayerAccount
    return isinstance(BigWorld.player(), PlayerAccount)

def _in_battle():
    """Whether the player is in a battle, its loading screen included."""
    import BigWorld
    from Avatar import PlayerAvatar
    return isinstance(BigWorld.player(), PlayerAvatar)

def is_queue_route(state_id):
    """Whether a lobby state, by its id ("subScope/subLayer/battleQueue/battleQueue"), is a battle queue."""
    return _QUEUE_CONTAINER in (state_id or '').split('/')[:-1]

def _state_machine():
    from gui.Scaleform.lobby_entry import getLobbyStateMachine
    return getLobbyStateMachine()

def queue_open():
    """Whether the lobby shows a battle queue."""
    machine = _state_machine()
    info = getattr(machine, 'visibleRouteInfo', None)
    state = getattr(info, 'state', None)
    return state is not None and is_queue_route(state.getStateID())

def _language():
    try:
        from helpers import getClientLanguage
        return getClientLanguage()
    except Exception:
        return 'en'


class Watching(object):
    """Whether the window is wanted right now."""

    def _on_panel_report(self):
        if self._leaving is not None:
            self._tick()

    def _on_enqueued(self, *args):
        self._entering_until = time.time() + _ENTER_SECONDS
        self._tick()

    def _on_dequeued(self, *args):
        self._entering_until = 0
        self._tick()

    def _on_battle(self, *args):
        # Kept on the queue screen, closed when the lobby leaves it.
        self._entering_until = 0
        self._to_battle = True

    def _on_avatar(self, *args):
        # The loading screen is next: the window is opened as soon as the
        # battle's main window allows, for its page to be drawn by the time
        # the screen shows, and not seconds into a loading that may be short.
        self._loading = True
        self._tick()

    def _on_loading(self, event):
        self._loading = bool(getattr(event, 'ctx', {}).get('isShown'))
        _logger.info('battle loading screen %s', 'shown' if self._loading else 'gone')
        self._tick()

    def _on_route(self, *args):
        self._tick()

    def _follow(self, machine):
        """Listen to this lobby state machine's route changes, and no longer to the last one's.

        The lobby app, and its state machine with it, is built again after
        every battle.
        """
        if machine is self._machine:
            return
        if self._machine is not None:
            try:
                self._machine.onVisibleRouteChanged -= self._on_route
            except Exception:
                _logger.debug('could not stop following the lobby routes', exc_info=True)
        self._machine = machine
        if machine is not None:
            machine.onVisibleRouteChanged += self._on_route

    def _tick(self):
        try:
            self._follow(_state_machine())
            # _wanted asks the setting that goes with where the player is:
            # the garage panel's in the lobby and on a loading screen, the
            # battle one over a battle.
            wanted = self._wanted()
        except Exception:
            _logger.exception('could not tell whether a battle queue is up')
            wanted = False
        if not wanted:
            self._leaving = None
            self._destroy()
            return
        try:
            self._check_code()
            if self._window is not None and self._stale():
                _logger.info('the Twitch window outlived its main window, opening it again')
                self._destroy()
            if self._window is None:
                self._create()
            elif self._ready:
                self._publish()
                self._place()
        except Exception:
            _logger.exception('could not keep the Twitch window up to date')

    def _wanted(self):
        """Whether the window should be up: over a battle, in a queue, about to be, or just out of one."""
        from unicum.twitch_panel import panel_reports
        now = time.time()
        if not _in_lobby():
            self._entering_until = 0
            self._leaving = None
            self._to_battle = False
            if not _in_battle():
                return False
            # The loading screen is the garage panel's own continuity: it
            # stands in for the panel the queue screen took away, so the
            # garage's setting is the one that asks for it, as it always
            # has. The battle itself is the player's separate choice, and
            # they may well want one without the other.
            if self._loading:
                return self._settings.shows_twitch_in_garage()
            return self._settings.shows_twitch_window_in_battle()
        self._loading = False
        if not self._settings.shows_twitch_in_garage():
            return False
        if queue_open():
            self._entering_until = 0
            self._leaving = None
            return True
        if self._to_battle:
            # Out of the queue for a battle: no garage panel to wait for.
            self._to_battle = False
            return False
        if now < self._entering_until:
            return True
        if self._window is None:
            return False
        if self._leaving is None:
            self._leaving = (now + _LEAVE_SECONDS, panel_reports())
            # The garage panel back, to say when it is on screen.
            self._cover(False)
        until, reports = self._leaving
        return now < until and panel_reports() == reports

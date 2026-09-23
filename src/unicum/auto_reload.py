"""Sends the "Reloading!" chat command by itself, the way F8 does.

After a shot that starts a reload: every shot of a single-shot gun, the last
shell of a magazine or autoloader. Which of the two is announced is a
setting: a gun firing one shell at a time reloads after every shot, an
autoloader only when its magazine runs out. The message is the client's own: the
battle's chat commands controller builds it from the reload time and shells
left (sendReloadingCommand), special reloads included. This only chooses when.

The server lets the same command through once every 5 seconds
(messenger_common_chat2._SAME_BATTLE_CHAT_CMD_COOLDOWN_DURATION). A reload
shorter than that would have the next one refused, so it is not announced,
and neither is anything within that time of the last one.

Fair play: this announces the player's own reload to their team, as F8
would. Nothing about other vehicles is read.
"""
import logging

_logger = logging.getLogger('unicum.auto_reload')

# The server's cooldown on the same battle chat command, in seconds.
COOLDOWN = 5.0

# Longest a shot and the reload it starts are apart: the client learns of
# each from a different message.
_PAIRING = 1.0

# How long after a shot the decision waits. The client can report the end of
# the previous reload about when the shot lands, and the new reload a moment
# later: of what came in by then, the longest reload is the one the shot
# started.
_SETTLE = 0.5

_ATTACH_SECONDS = 0.5

_TICK_SECONDS = 0.1


class ReloadAnnouncer(object):
    """When to announce: pairs a shot with the reload it starts.

    No client code here, so it can be tested: `clock` gives seconds, `send`
    announces, and tick() is called often to decide on a settled shot.
    """

    def __init__(self, clock, send, skipped=None, allows=None):
        self._clock = clock
        self._send = send
        # skipped(reason): a shot that is not announced, and why.
        self._skipped = skipped or (lambda reason: None)
        # allows(magazine): whether this kind of reload is announced at all.
        self._allows = allows or (lambda magazine: True)
        self._quantities = {}
        self._shot = None
        self._reloads = []
        self._last_sent = None

    def shells(self, shell, quantity, in_clip):
        """The current shell's count changed: one fewer is a shot."""
        previous = self._quantities.get(shell)
        self._quantities[shell] = quantity
        if previous is not None and quantity < previous:
            self._shot = (self._clock(), in_clip)

    def reload(self, time_left, magazine):
        """A reload was reported, `time_left` seconds to go; `magazine` for a clip or autoloader."""
        if time_left > 0:
            now = self._clock()
            self._reloads = [r for r in self._reloads if now - r[0] <= 2 * _PAIRING]
            self._reloads.append((now, time_left, magazine))

    def tick(self):
        if self._shot is None:
            return
        shot_at, in_clip = self._shot
        now = self._clock()
        if now - shot_at < _SETTLE:
            return
        self._shot = None
        paired = [r for r in self._reloads if abs(r[0] - shot_at) <= _PAIRING]
        if not paired:
            self._skipped('no reload came with the shot')
            return
        _, time_left, magazine = max(paired, key=lambda r: r[1])
        self._reloads = []
        if magazine and in_clip > 0:
            self._skipped('%d shells still in the magazine' % in_clip)
            return
        if not self._allows(magazine):
            self._skipped('this gun is not announced by the settings')
            return
        if time_left < COOLDOWN:
            self._skipped('a %.1fs reload, under the chat cooldown' % time_left)
            return
        if self._last_sent is not None and now - self._last_sent < COOLDOWN:
            self._skipped('%.1fs after the last announcement' % (now - self._last_sent))
            return
        self._last_sent = now
        self._send()


class AutoReload(object):
    """Follows the battle's ammo controller and announces through the client."""

    def __init__(self, session, settings):
        self._session = session
        self._settings = settings
        self._ammo = None
        self._announcer = None

    def install(self):
        self._session.repeat(_ATTACH_SECONDS, self._follow)
        self._session.repeat(_TICK_SECONDS, self._tick)
        self._session.on_close(self._detach)
        _logger.info('installed')

    def _follow(self):
        """Attach to the battle in progress, and let go of the last one."""
        ammo = _ammo()
        if ammo is self._ammo:
            return
        self._detach()
        if ammo is None:
            return
        import BigWorld
        self._ammo = ammo
        self._announcer = ReloadAnnouncer(BigWorld.time, self._send, self._on_skipped,
                                          self._settings.announces_reload)
        ammo.onShellsUpdated += self._on_shells
        ammo.onGunReloadTimeSet += self._on_reload
        _logger.info('following the reloads of this battle, announcing %s',
                     'on' if self._settings.shows_auto_reload() else 'off')

    def _tick(self):
        try:
            if self._announcer is not None:
                self._announcer.tick()
        except Exception:
            _logger.exception('could not decide on a shot')

    def _detach(self):
        if self._ammo is not None:
            try:
                self._ammo.onShellsUpdated -= self._on_shells
                self._ammo.onGunReloadTimeSet -= self._on_reload
            except Exception:
                _logger.exception('could not let go of the ammo controller')
        self._ammo = None
        self._announcer = None

    def _on_shells(self, shell, quantity, in_clip, result):
        try:
            if self._announcer is not None and shell == self._ammo.getCurrentShellCD():
                self._announcer.shells(shell, quantity, in_clip)
        except Exception:
            _logger.exception('could not follow the shells')

    def _on_reload(self, shell, state, *args):
        try:
            if self._announcer is None:
                return
            gun = self._ammo.getGunSettings()
            magazine = bool(gun.isCassetteClip) or gun.hasAutoReload()
            self._announcer.reload(state.getTimeLeft(), magazine)
        except Exception:
            _logger.exception('could not follow the reload')

    def _on_skipped(self, reason):
        _logger.debug('reload not announced: %s', reason)

    def _send(self):
        if not self._settings.shows_auto_reload():
            _logger.debug('reload not announced: switched off in the settings')
            return
        import BattleReplay
        from gui.battle_control import avatar_getter
        if BattleReplay.g_replayCtrl.isPlaying or not avatar_getter.isVehicleAlive():
            return
        commands = _session_provider().shared.chatCommands
        if commands is None:
            _logger.warning('reload not announced: no chat commands in this battle')
            return
        commands.sendReloadingCommand()
        _logger.debug('reload announced')


def _session_provider():
    from helpers import dependency
    from skeletons.gui.battle_session import IBattleSessionProvider
    return dependency.instance(IBattleSessionProvider)


def _ammo():
    """The battle's ammo controller, or None outside a battle."""
    try:
        from helpers import isPlayerAvatar
        if not isPlayerAvatar():
            return None
        return _session_provider().shared.ammo
    except Exception:
        return None


def install(session, settings):
    AutoReload(session, settings).install()

"""Sends the "Reloading!" chat command by itself, the way F8 does.

After a shot that starts a reload: every shot of a single-shot gun, the last
shell of a magazine or autoloader. Which of the two is announced is a
setting: a gun firing one shell at a time reloads after every shot, an
autoloader only when its magazine runs out. The message is the client's own: the
battle's chat commands controller builds it from the reload time and shells
left (sendReloadingCommand), special reloads included. This only chooses when.

And after either of the two presses that reload the gun on purpose, neither of
which left anything to announce at all: the decision only ever armed on a
shot, and a press fires nothing, so the reload arrived, paired with nothing
and was dropped.

    change of shell    `ammo.changeSetting`, from the keys or the panel
    reload the clip    `ammo.reloadClip`, the C key (CMD_RELOAD_PARTIAL_CLIP)

Neither is gated on the magazine/all setting the way a shot is. That setting
is there to keep a single-shot gun from announcing every shot, and these are
deliberate acts a player performs a handful of times. The C key is a magazine
gun's alone: the client drops the press on an autoloader and on a single-shot
gun, which is left to the client rather than predicted here.

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

# How long after a shot the decision waits, when no report has settled it on
# its own. The client can report the end of the previous reload about when the
# shot lands, and the new reload a moment later: of what came in by then, the
# longest reload is the one the shot started.
#
# A fallback, not the usual path: a report at or over the cooldown is acted on
# as it arrives (see `reload`), because nothing arriving later could change
# the answer. What waits here is the ambiguous case, which ends in silence
# anyway, so the wait costs nobody anything.
_SETTLE = 0.5

_ATTACH_SECONDS = 0.5

_TICK_SECONDS = 0.1

# What armed the decision. Kept apart because one rule applies to a shot and
# not to a swap, and because the reason a skipped reload gives should name
# what the player actually did.
_SHOT = 'shot'
_SWAP = 'change of shell'
_CLIP = 'manual reload'

# The two deliberate presses, as against a shot. Both reload the gun on
# purpose and with shells still in the magazine, which is the whole point of
# either, so neither is judged by the rule that sends a shot away when the
# magazine is not empty.
_PRESSES = (_SWAP, _CLIP)


class ReloadAnnouncer(object):
    """When to announce: pairs a shot with the reload it starts.

    No client code here, so it can be tested: `clock` gives seconds, `send`
    announces, and tick() is called often to decide on a settled shot.
    """

    def __init__(self, clock, send, skipped=None, allows=None, allows_press=None):
        self._clock = clock
        self._send = send
        # skipped(reason): a shot that is not announced, and why.
        self._skipped = skipped or (lambda reason: None)
        # allows(magazine): whether this kind of reload is announced at all.
        self._allows = allows or (lambda magazine: True)
        # allows_press(): whether a deliberate press is announced, meaning a
        # change of shell or a manual clip reload. See the module docstring
        # for why neither asks `allows`.
        self._allows_press = allows_press or (lambda: True)
        self._quantities = {}
        self._pending = None
        self._reloads = []
        self._last_sent = None

    def shells(self, shell, quantity, in_clip):
        """The current shell's count changed: one fewer is a shot."""
        previous = self._quantities.get(shell)
        self._quantities[shell] = quantity
        if previous is not None and quantity < previous:
            self._pending = (self._clock(), _SHOT, in_clip)

    def swapped(self):
        """The player changed shell, which reloads the gun with the new one.

        Not over a shot already waiting: that shot started a reload of its
        own, and a swap pressed in the same half second would take its place
        and then be judged by the rule for a swap. The shot came first and
        its reload is the one on the way.
        """
        if self._pending is None:
            self._pending = (self._clock(), _SWAP, 0)

    def reloaded(self):
        """The player asked for the clip to be reloaded, which is the C key.

        A magazine gun only, and deliberately: the client refuses the press
        outright on an autoloader and on a single-shot gun
        (`ammo_ctrl.reloadClip` requires `isMagazineClip` and not
        `hasAutoReload`), and refuses it on a clip that is already full. None
        of that is predicted here. Whether a reload actually followed is
        observed, exactly as it is for a swap, so a press that did nothing
        pairs with nothing and is never announced.

        Not over a shot already waiting, for the reason given in `swapped`.
        """
        if self._pending is None:
            self._pending = (self._clock(), _CLIP, 0)

    def reload(self, time_left, magazine):
        """A reload was reported, `time_left` seconds to go; `magazine` for a clip or autoloader."""
        if time_left <= 0:
            return
        now = self._clock()
        self._reloads = [r for r in self._reloads if now - r[0] <= 2 * _PAIRING]
        self._reloads.append((now, time_left, magazine))
        # Decided here, rather than at the next settled tick, when this one
        # report already settles it.
        #
        # The waiting is there to tell the tail of the previous reload -- a
        # fraction of a second left, reported about when the shot lands --
        # from the reload the shot started, by taking the longest of what
        # arrives. A report already at or over the cooldown cannot lose that
        # comparison: the longest can only be longer. And nothing else in
        # the decision varies between reports, since `magazine` is a
        # property of the gun, `in_clip` was read when the shot was, and the
        # rest is settings.
        #
        # So the half second bought nothing in the one case that ends in an
        # announcement, and was heard as lag.
        if time_left < COOLDOWN or self._pending is None:
            return
        armed_at, kind, in_clip = self._pending
        if now - armed_at > _PAIRING:
            return
        self._pending = None
        self._decide(now, kind, in_clip, time_left, magazine)

    def tick(self):
        if self._pending is None:
            return
        armed_at, kind, in_clip = self._pending
        now = self._clock()
        if now - armed_at < _SETTLE:
            return
        self._pending = None
        # Whether a reload followed is never predicted, only observed. For a
        # swap that matters: a press the client refuses, or one that only
        # queues the shell for after the reload already running, brings no
        # reload of its own and so pairs with nothing and ends here.
        paired = [r for r in self._reloads if abs(r[0] - armed_at) <= _PAIRING]
        if not paired:
            self._skipped('no reload came with the %s' % kind)
            return
        _, time_left, magazine = max(paired, key=lambda r: r[1])
        self._decide(now, kind, in_clip, time_left, magazine)

    def _decide(self, now, kind, in_clip, time_left, magazine):
        """Announce this reload or say why not; the reloads seen are spent."""
        self._reloads = []
        if kind in _PRESSES:
            if not self._allows_press():
                self._skipped('a %s is not announced by the settings' % kind)
                return
        else:
            # A magazine with shells left starts no reload of its own, so the
            # reload that came with the shot belongs to something else. A
            # press is the exception and is handled above: it reloads whatever
            # is still in the magazine, which is the point of announcing it.
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
        # {name: wrapper} for each controller call we put our own over, so
        # _detach can take each back off again. Empty when nothing is
        # wrapped.
        self._wrapped = {}

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
                                          self._settings.announces_reload,
                                          self._settings.shows_auto_reload)
        ammo.onShellsUpdated += self._on_shells
        ammo.onGunReloadTimeSet += self._on_reload
        self._watch_presses(ammo)
        _logger.info('following the reloads of this battle, announcing %s',
                     'on' if self._settings.shows_auto_reload() else 'off')

    def _tick(self):
        try:
            if self._announcer is not None:
                self._announcer.tick()
        except Exception:
            _logger.exception('could not decide on a shot')

    def _watch_presses(self, ammo):
        """Hear the two deliberate presses, by wrapping the calls they make.

        `changeSetting` is where a change of shell ends up, from the keys and
        from the panel alike (`handleAmmoChoice` reaches it through the view
        component, `_handleAmmoPressed` calls it outright), and it answers
        True only when the change was really dispatched to the server.

        `reloadClip` is the C key, straight from `Avatar.handleKey` on
        `CMD_RELOAD_PARTIAL_CLIP`. It answers nothing at all, so unlike a swap
        there is no telling from the call whether anything happened: the
        client drops the press on an autoloader, on a single-shot gun and on a
        full clip. That costs nothing, because an announcement waits on a
        reload being reported either way, and a press that started none pairs
        with nothing.

        Wrapping these rather than reading keys: the key is rebindable, and
        the reload event they lead to also fires at the start of a battle and
        whenever the panel refreshes, so neither the key nor the event says
        what the player did.

        Instance attributes rather than `session.patch`: the controller is
        built fresh for every battle, so a patch per battle would pile up
        undos for objects long gone. These come off in `_detach`, with the
        subscriptions, for the same reason and at the same time.
        """
        self._wrapped = {}
        self._wrap(ammo, 'changeSetting', lambda answer: bool(answer),
                   lambda announcer: announcer.swapped())
        # Answered by nothing, so every press arms the decision and the
        # pairing decides. See above.
        self._wrap(ammo, 'reloadClip', lambda answer: True,
                   lambda announcer: announcer.reloaded())

    def _wrap(self, ammo, name, happened, tell):
        """Put our own `name` over the controller's, remembering it to undo."""
        try:
            original = getattr(ammo, name)

            def wrapper(*args, **kwargs):
                answer = original(*args, **kwargs)
                try:
                    if self._announcer is not None and happened(answer):
                        tell(self._announcer)
                except Exception:
                    _logger.exception('could not follow %s', name)
                return answer

            setattr(ammo, name, wrapper)
            self._wrapped[name] = wrapper
        except Exception:
            # A client that will not take one wrapper keeps every other
            # announcement: only that one press goes unheard.
            _logger.exception('could not follow %s', name)

    def _detach(self):
        if self._ammo is not None:
            try:
                self._ammo.onShellsUpdated -= self._on_shells
                self._ammo.onGunReloadTimeSet -= self._on_reload
            except Exception:
                _logger.exception('could not let go of the ammo controller')
            for name, wrapper in self._wrapped.items():
                try:
                    # Only our own wrapper is removed. Another mod may have
                    # wrapped ours since, and deleting the attribute then
                    # would throw that one away with it.
                    if self._ammo.__dict__.get(name) is wrapper:
                        delattr(self._ammo, name)
                except Exception:
                    _logger.exception('could not unwrap %s', name)
        self._wrapped = {}
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

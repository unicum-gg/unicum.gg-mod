"""Where everybody was, sampled while the battle runs.

What this is for
----------------
A battle replayed on its own minimap: thirty vehicles moving, turrets turning,
shots leaving guns. The site can draw that from positions over time, and this
is where the positions come from.

Why not the .wotreplay file
---------------------------
Measured on ten real battles: a replay is 811 KB and the positions inside it
are 9 KB a second apart, 64 KB five times a second with the three angles a 3D
view would want. So the file is between nine and ninety times the thing we
actually need, and storing files would be a decision with no way back.

It would also collect from the wrong half of the playerbase. A replay exists
only when the player left recording on, and new accounts do not get it at its
highest. This runs in every client, for every battle, exactly like the results
do.

**And it loses nothing by not reading the file.** A replay is the packet stream
this client received, so it holds what this client could see and no more; a
viewer built on one shows the same fog of war. Sampling here sees precisely the
same vehicles, because it is the same client looking.

What it costs
-------------
Thirty entity reads five times a second, on the thread that draws the game, for
the length of a battle. Each read is three attribute lookups and two matrix
reads, which is what the minimap already does every frame for the same
vehicles. The samples are kept as plain numbers and handed to the battle
upload, which sends them with the results.
"""
import logging

from unicum import config

_logger = logging.getLogger('unicum.motion')

# Samples a second.
#
# Five rather than one: one is enough to watch a battle unfold on a minimap,
# and far too coarse for a turret, which swings a quarter turn in that time.
# Measured, five costs 64 KB a battle against 20 KB at one, and the difference
# is what decides whether a 3D view ever becomes possible without going back
# to collect it all again. Ten gained little and cost half as much again.
_HZ = 5.0
_PERIOD = 1.0 / _HZ

# Hundredths of a radian, and whole metres.
#
# A map is a kilometre across drawn five hundred pixels wide, so half a metre
# is already under a pixel; and a hundredth of a radian is a third of a degree,
# past what a drawn tank shows. Rounding here rather than on the server is most
# of why the samples compress: a vehicle sitting still writes the same numbers,
# and the same numbers deflate to nothing.
_ANGLE = 100.0


def _round(value):
    try:
        return int(round(value))
    except (TypeError, ValueError):
        return 0


class Motion(object):
    """One battle's samples, taken until it ends."""

    def __init__(self, session):
        self._session = session
        # {vehicle id: [t, x, z, hull, turret, gun, ...]} flat, not tuples: a
        # list of small ints is what json.dumps writes most compactly, and this
        # is held for the length of a battle.
        self._samples = {}
        self._started = None
        self._arena_id = None
        self._running = False

    def install(self):
        try:
            from PlayerEvents import g_playerEvents
            self._session.subscribe(g_playerEvents.onAvatarBecomePlayer, self._on_battle)
            self._session.subscribe(g_playerEvents.onAvatarBecomeNonPlayer, self._on_leave)
        except ImportError:
            _logger.exception('no player events; battles are not sampled')
            return
        _logger.info('installed')

    def _on_battle(self, *args):
        """A battle has started: begin sampling, and forget the one before."""
        try:
            import BigWorld
            player = BigWorld.player()
            self._arena_id = str(getattr(player, 'arenaUniqueID', '') or '')
            self._samples = {}
            self._started = None
            if not self._running:
                self._running = True
                self._session.repeat(_PERIOD, self._tick)
            _logger.info('sampling battle %s', self._arena_id or '?')
        except Exception:
            _logger.exception('could not start sampling')

    def _on_leave(self, *args):
        self._running = False

    def _tick(self):
        """One sample of every vehicle this client can currently see.

        Guarded whole and silent on failure: this runs five times a second on
        the thread that draws the game, and a battle that logs a traceback
        twenty times a second would cost more than the feature is worth.
        """
        if not self._running:
            return
        try:
            import BigWorld
            import Math
            player = BigWorld.player()
            if player is None:
                return
            arena = getattr(player, 'arena', None)
            if arena is None:
                return
            now = BigWorld.serverTime()
            if self._started is None:
                self._started = now
            at = _round((now - self._started) * 10)
            for vehicle_id in arena.vehicles:
                vehicle = BigWorld.entity(vehicle_id)
                # Out of this client's area of interest: unspotted, or too far.
                # Nothing is written rather than a last known position, so a
                # gap in a track is an honest "we could not see them".
                if vehicle is None or not getattr(vehicle, 'isStarted', True):
                    continue
                try:
                    position = vehicle.position
                    hull = Math.Matrix(vehicle.matrix).yaw
                    appearance = getattr(vehicle, 'appearance', None)
                    turret = gun = 0.0
                    if appearance is not None:
                        turret = Math.Matrix(appearance.turretMatrix).yaw
                        gun = Math.Matrix(appearance.gunMatrix).pitch
                except Exception:
                    continue
                self._samples.setdefault(vehicle_id, []).extend((
                    at,
                    _round(position.x),
                    _round(position.z),
                    _round(hull * _ANGLE),
                    _round(turret * _ANGLE),
                    _round(gun * _ANGLE),
                ))
        except Exception:
            # Once, not five times a second: the flag stops the sampling rather
            # than letting a broken client write a traceback for seven minutes.
            self._running = False
            _logger.exception('sampling stopped')

    def take(self, arena_id):
        """The samples for this battle, and forget them. None if they are not its.

        Checked against the arena id rather than handed over blindly: results
        can arrive for a battle other than the one just played (an old one
        reopened from the notification centre), and attaching the wrong tracks
        to it would be a drawing of the wrong battle with the right names.
        """
        if not self._samples or str(arena_id) != self._arena_id:
            return None
        out = {
            'hz': int(_HZ),
            # What the numbers mean, so a reader never has to guess the units:
            # tenths of a second, whole metres, hundredths of a radian.
            'vehicles': dict((str(key), value)
                             for key, value in self._samples.items() if value),
        }
        self._samples = {}
        return out if out['vehicles'] else None


def install(session):
    motion = Motion(session)
    motion.install()
    return motion

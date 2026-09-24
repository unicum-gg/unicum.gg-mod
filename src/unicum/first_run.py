"""The folders the mod draws its own images from, and the one restart they cost.

The client indexes its resource tree as it starts. A file written into a
folder that was in that index draws at once; a folder that appears later is
not in it, and nothing written there can be drawn until the client starts
again. That is not a cache to be flushed: `ResMgr.purge` drops a cached
section so the next read hits the disk, but the index itself is built once,
and purging a folder it never saw changes nothing (measured in the client:
still not drawable afterwards).

So a fresh install has a choice to make on its first run, and only three ways
to go:

  ship the folders    The archive carried them, which worked and is what made
                      the install instruction name res_mods at all, on top of
                      mods/ and mods/net.openwg/. Three trees to explain for
                      two empty folders.
  declare them in
  the .wotmod         Tried, and worse than doing nothing. ResMgr does index a
                      folder a .wotmod carries, so the mod's own check said
                      "yes, draw" -- but the badges are written to res_mods,
                      which was still unindexed, so every one of them came
                      back `Cannot load protocol image` and the ratings showed
                      nothing at all. Bare numbers are better than that.
  make them and
  restart             What this module does, and what openwg_gameface already
                      does beside us for its resource map.

The restart cannot loop: it is asked for only when a folder was created, and
a folder is created only once. The second start finds them and says nothing.
"""
import logging
import os

from unicum import config

_logger = logging.getLogger('unicum.first_run')

# Written into a folder the moment it is made, so the folder is never empty:
# `badges.py` reads the same name back to ask whether the client indexed it.
MARKER = 'ready.png'

# A 1x1 transparent PNG. Never drawn, only indexed.
MARKER_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06'
    b'\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\xdac\xfc\xff\x1f\x00\x03'
    b'\x03\x02\x000\x81\xd0/\x00\x00\x00\x00IEND\xaeB`\x82')

# Everything the mod writes images into during a session. Both are drawn from
# by name, so both have to be in the index before the first one is written.
IMAGE_DIRS = ('gui/maps/icons/unicum/badges',
              'gui/maps/icons/unicum/twitch/badges')


def prepare():
    """Create the image folders that are missing. True when one was made.

    True means this client cannot draw those images for the rest of the
    session, whatever is written into them, which is what makes a restart
    worth asking for.
    """
    made = False
    for res_path in IMAGE_DIRS:
        directory = config.res_mods_file(res_path)
        if not directory:
            _logger.warning('no res_mods folder: %s cannot be prepared', res_path)
            continue
        if os.path.isdir(directory):
            continue
        try:
            os.makedirs(directory)
            with open(os.path.join(directory, MARKER), 'wb') as handle:
                handle.write(MARKER_PNG)
            _logger.info('created %s', directory)
            made = True
        except (IOError, OSError):
            _logger.exception('could not create %s', directory)
    return made


def restart_if_idle():
    """Restart now, as long as the client has not entered a world yet.

    `BigWorld.player()` is None while the client is still coming up, and is
    something the moment it has an account or an avatar. That single question
    covers both cases worth refusing:

      in a battle   a player dropped mid-match is not merely interrupted,
                    they are penalised for leaving
      hot reload    a developer reloading the package is not a fresh install
                    and must not have their client restarted under them

    Restarting here rather than waiting for the garage is worth the care: the
    mod loads while the client is still starting, so the restart costs the few
    seconds already spent, instead of a sign-in and a full garage load that
    are about to be thrown away anyway.
    """
    try:
        import BigWorld
        if BigWorld.player() is not None:
            _logger.info('a restart is needed but the client is in a session; leaving it')
            return False
    except Exception:
        _logger.exception('could not tell whether the client is in a session')
        return False
    return _restart()


def _restart():
    """Ask the client to restart, the way its own settings window does."""
    try:
        import BigWorld
        BigWorld.savePreferences()
        try:
            # The launcher is told first, as the client's own settings window
            # does, so it does not read the exit as a crash.
            import WGC
            WGC.notifyRestart()
        except Exception:
            _logger.info('no WGC to notify; restarting anyway')
        BigWorld.worldDrawEnabled(False)
        BigWorld.restartGame()
        return True
    except Exception:
        _logger.exception('could not restart the client')
        return False

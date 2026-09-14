"""Settings that differ between a dev machine and a released mod."""
import os

REGION = 'eu'

_DEFAULT_API_BASE = 'https://unicum.gg'

# Overridden two ways, neither of which puts a LAN address in the repository.
#
# The environment variable is read once when the client starts, which is no
# use for a mod that is meant to be edited while the game runs. So a
# gitignored local_settings.py wins over it: dropping one in redirects the
# API on the next reload, without restarting anything.
try:
    from unicum import local_settings
except ImportError:
    local_settings = None

API_BASE = (
    getattr(local_settings, 'API_BASE', None)
    or os.environ.get('UNICUM_API_BASE')
    or _DEFAULT_API_BASE
).rstrip('/')

# Seconds a language answer stays good for, matching the `max-age` the
# resolve endpoint sends. Nothing here is worth being cleverer about: clan
# languages barely move, and the server already fronts a much longer CDN
# window.
CACHE_SECONDS = 300

API_TIMEOUT = 10.0

# Downloaded images, kept between sessions, inside the resource tree.
#
# They were briefly held outside it, in mods/configs, and handed to the
# engine with wg_addScaleformTexture so they would need no restart. That
# does not scale: with 252 flags registered before anything drew, a contacts
# list still rendered one. Memory textures are built for the single image
# the client uses them for -- a clan emblem, an achievement icon -- not for
# a list. Paths into the resource tree have no such ceiling.
#
# The cost is that ResMgr indexes at startup, so a flag downloaded now first
# appears next session. In practice the same handful of languages recur, so
# the cache is warm after a couple of sessions and nothing ships in the
# package.
FLAGS_RES_PATH = 'gui/maps/icons/unicum/flags'


def _flags_dir():
    """Where flag PNGs are written, relative to the client's directory.

    The res_mods folder is version-named and the mod has no business
    hardcoding a client version, so the one that is there is the one used.
    """
    root = 'res_mods'
    try:
        versions = sorted(name for name in os.listdir(root)
                          if os.path.isdir(os.path.join(root, name)))
    except OSError:
        versions = []
    if not versions:
        return None
    return os.path.join(root, versions[-1], *FLAGS_RES_PATH.split('/'))


CACHE_DIR = _flags_dir()

# Resolved languages, kept between sessions. Plain data read with plain file
# I/O, so unlike the flags it has no business being in the resource tree.
#
# Its job is the first paint: lookups are answered over the network but
# consumed synchronously, so without it every game start draws one unmarked
# contacts list before the answers arrive.
LANGUAGE_STORE = os.path.join('mods', 'configs', 'unicum', 'languages.json')

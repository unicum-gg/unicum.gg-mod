"""Files that ship beside the package's code: scripts, styles, images, data.

In development the package is a directory on disk (the bootstrap imports it
from the working copy), and these files are read from beside the code, again
whenever they change. A released mod ships the package inside a .wotmod, at
scripts/client/unicum/, where open() finds nothing: the files are in the
client's virtual resource tree, read through ResMgr, and never change.

Paths are relative to the package, with forward slashes: 'web/hangar/tank_menu.js'.
"""
import logging
import os

_logger = logging.getLogger('unicum.resources')

# Where the release puts the package in the resource tree.
PACKAGE_RES = 'scripts/client/unicum'

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _disk(rel):
    return os.path.join(_ROOT, *rel.split('/'))


def _section(rel):
    try:
        import ResMgr
    except ImportError:
        return None
    return ResMgr.openSection('%s/%s' % (PACKAGE_RES, rel))


def read(rel):
    """The file's bytes, or None when it is nowhere."""
    path = _disk(rel)
    if os.path.isfile(path):
        with open(path, 'rb') as handle:
            return handle.read()
    section = _section(rel)
    return section.asBinary if section is not None else None


def listdir(rel):
    """The names in a folder, sorted, or [] when it is nowhere."""
    path = _disk(rel)
    if os.path.isdir(path):
        return sorted(os.listdir(path))
    section = _section(rel)
    return sorted(section.keys()) if section is not None else []


def stamp(rel):
    """What changes when the file does, on disk; None inside a release, where nothing changes."""
    path = _disk(rel)
    try:
        return os.path.getmtime(path) if os.path.isfile(path) else None
    except OSError:
        return None

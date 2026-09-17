"""Load a built .wotmod the way the client does, outside the game.

    python2.7 tools/release_check.py dist/gg.unicum_1.0.0.wotmod

The selftest drives the mod from its sources. A release is something else:
compiled modules only, imported from scripts/client/, and resources that exist
nowhere on disk, only in the client's virtual tree. This extracts the package,
imports it from its .pyc files with the fake client of tools/checks, answers
ResMgr from the package's res/ tree, and checks that the entry point starts
the mod and that every resource the mod reads through resources.py is there.

Python 2.7, same as the client.
"""
import imp
import logging
import os
import shutil
import sys
import tempfile
import zipfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)

from checks.client import install_fake_client
from checks.common import check
from checks.engine import FakeBigWorld


class Section(object):

    def __init__(self, path):
        self._path = path

    @property
    def asBinary(self):
        with open(self._path, 'rb') as handle:
            return handle.read()

    def keys(self):
        return os.listdir(self._path)


class FakeEventBus(object):
    """The selftest never needs one: its client has no SWFs, so views.py never installs."""

    def addListener(self, *args, **kwargs):
        pass

    def removeListener(self, *args, **kwargs):
        pass


class PackageResMgr(object):
    """ResMgr answering from the package's res/ tree, as the client merges it."""

    root = None
    # Paths answered as absent: the SWFs, as in the selftest, whose fake client
    # cannot host views.py; they are checked for in the package on their own.
    hidden = ('gui/flash/',)

    @classmethod
    def _path(cls, path):
        return os.path.join(cls.root, *path.split('/'))

    @classmethod
    def isFile(cls, path):
        return not path.startswith(cls.hidden) and os.path.isfile(cls._path(path))

    @classmethod
    def openSection(cls, path):
        full = cls._path(path)
        return Section(full) if os.path.exists(full) else None


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    logging.basicConfig(level=logging.INFO, format='       %(name)s: %(message)s')
    workdir = tempfile.mkdtemp(prefix='unicum-release-')
    try:
        with zipfile.ZipFile(sys.argv[1]) as archive:
            names = archive.namelist()
            archive.extractall(workdir)
        res = os.path.join(workdir, 'res')
        check('no source file ships', not [n for n in names if n.endswith('.py')])
        check('the entry point is where the client loads mods from',
              'res/scripts/client/gui/mods/mod_unicum.pyc' in names)
        check('the views and the patched markers app ship',
              all('res/gui/flash/%s' % swf in names for swf in
                  ('unicum.lobby.swf', 'unicum.battle.swf', 'unicum.markers.swf', 'unicum.markers.classes.swf',
                   'battleVehicleMarkersApp.swf')))

        game = os.path.join(workdir, 'game')
        os.makedirs(os.path.join(game, 'res_mods', '2.4.0.0'))
        os.chdir(game)
        install_fake_client(FakeBigWorld())
        sys.modules['gui.shared'].g_eventBus = FakeEventBus()
        PackageResMgr.root = res
        sys.modules['ResMgr'] = PackageResMgr
        sys.path.insert(0, os.path.join(res, 'scripts', 'client'))

        entry = imp.load_compiled('mod_unicum', os.path.join(res, 'scripts', 'client', 'gui', 'mods', 'mod_unicum.pyc'))
        entry.init()
        import unicum
        check('the package is the compiled one from the package',
              os.path.dirname(unicum.__file__) == os.path.join(res, 'scripts', 'client', 'unicum'))
        check('the entry point started the mod', entry._loaded is unicum and unicum._session is not None)

        from unicum import badge_png, resources
        # As in the client, where the package is no directory on disk.
        resources._ROOT = os.path.join(workdir, 'nowhere')
        del badge_png._masks[:]
        for rel in ('web/hangar/tank_menu.js', 'web/hangar/tank_menu.css', 'web/hangar/twitch_panel.js',
                    'web/hangar/twitch_panel.css', 'web/hangar/account_card.js', 'web/hangar/account_card.css',
                    'web/stronghold/core.js', 'web/results/battle_results.js', 'web/results/battle_results.css',
                    'badge_glyphs.json'):
            check('the package holds %s, read through ResMgr' % rel, bool(resources.read(rel)))
        check('the hangar icons are listed through ResMgr',
              'settings.png' in resources.listdir('web/hangar/panel_icons')
              and resources.listdir('web/hangar/icons'))
        check('a badge is drawn from the packaged masks', badge_png.png(3323, '#7A4FB2')[1:4] == b'PNG')
        from unicum.runtime.session import Session
        from unicum.textures import FlagCache
        flags = FlagCache(Session(generation=0))
        check('a packaged flag is drawn though the disk holds none',
              flags.source('FR') == 'img://gui/maps/icons/unicum/flags/FR.png'
              and flags.data_uri('FR').startswith('data:image/png;base64,'))
        check('the hangar module and its res_map entry ship',
              PackageResMgr.isFile('gui/gameface/mods/unicum/TankButton/TankButton.js')
              and PackageResMgr.isFile('mods/configs/res_map/unicum.json'))

        entry.fini()
        check('the entry point stops the mod', entry._loaded is None)
    finally:
        os.chdir(TOOLS)
        shutil.rmtree(workdir, ignore_errors=True)
    # check() exits on the first failure.
    print('\nrelease check passed')


if __name__ == '__main__':
    main()

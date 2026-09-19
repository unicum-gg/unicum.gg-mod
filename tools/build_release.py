"""Build the released mod: what a player unzips into the game, with nothing else to install.

    python tools/build_release.py --version 1.0.0

Writes dist/gg.unicum_<version>.wotmod, and dist/unicum.gg_<version>.zip laid
out as the game folder, which is what is published:

  mods/<game version>/gg.unicum_<version>.wotmod
  mods/<game version>/net.openwg/net.openwg.gameface_<its version>.wotmod

openwg_gameface is what the garage features need. It is bundled from
vendor/openwg/ (MIT, its license beside it) under net.openwg/, the folder every
mod that ships it uses, so a copy from another mod is overwritten rather than
loaded twice. Update it by replacing that file.

The .wotmod holds:

  res/scripts/client/gui/mods/mod_unicum.pyc   the entry point (dev/mod_unicum.py.in)
  res/scripts/client/unicum/...                the package, compiled with the client's
                                               Python 2.7, and its resources (web/,
                                               badge_glyphs.json), read through ResMgr
                                               there (src/unicum/resources.py)
  res/gui/flash/*.swf                          the AS3 views and the patched markers app
  res/gui/maps/icons/unicum/...                flags, the mod's icons
  res/gui/gameface/..., res/mods/configs/...   res/ as it is: the Gameface modules (the hangar
                                               button, the Twitch window) and their res_map entries

Build its inputs first, as for development:

    cd tools/flags && npm install && npm run build && cd ../..
    cd tools/badges && npm install && npm run icon && cd ../..
    python tools/build_as3.py --game "C:/Games/World_of_Tanks_EU"

Stored, never deflated, like the dev bootstrap's package: the client rejected
deflated members in 2.3.1.3. The rating badges are not in it: the client
draws them (src/unicum/badge_png.py).

Runs on Python 3; compiling needs the client's Python 2.7 (--python27).
"""
from __future__ import annotations

import argparse
import base64
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from install_dev import AS3_BUILD, FLAGS_BUILD, ICON_BUILD, PYTHON27_CANDIDATES, RES

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / 'src' / 'unicum'
ENTRY = REPO / 'dev' / 'mod_unicum.py.in'
DIST = REPO / 'dist'

MOD_ID = 'gg.unicum'

# The client the package is built for: its mods/ folder in the zip.
GAME_VERSION = '2.4.0.1'
GAMEFACE = REPO / 'vendor' / 'openwg'
NAME = 'unicum.gg'
DESCRIPTION = ('Player ratings and language flags across the game, the unicum.gg tank menu in the '
               'garage, and your Twitch chat in battle and in the garage.')

# Never shipped: a developer's own settings, compiled leftovers.
EXCLUDED = {'local_settings.py'}

# The client indexes its resource folders as it starts: an image written into a
# folder it knew draws at once, one in a folder created later draws only from
# the next start on. The mod draws its rating badges and keeps the Twitch chat's
# badges as it goes, so a first run in a fresh install had neither -- ratings
# came out as bare numbers (src/unicum/badges.py). The installer creates those
# folders instead, so they are there before the client ever runs.
RUNTIME_IMAGE_DIRS = ('gui/maps/icons/unicum/badges',
                      'gui/maps/icons/unicum/twitch/badges')

# What makes each folder exist: a 1x1 transparent PNG, never drawn. badges.py
# writes and reads the same name to ask whether the folder was indexed.
MARKER = 'ready.png'
MARKER_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=')

VERSION = re.compile(r'^\d+\.\d+\.\d+$')


def python27(given: str | None) -> list[str]:
    candidates = [Path(given)] if given else PYTHON27_CANDIDATES
    for candidate in candidates:
        if candidate.is_file():
            return [str(candidate)]
    raise SystemExit('Python 2.7 not found; pass --python27')


def stage_package(stage: Path, version: str) -> Path:
    """The package's sources in a scratch tree, with the release's version in it."""
    package = stage / 'unicum'
    shutil.copytree(SRC, package, ignore=shutil.ignore_patterns('*.pyc', '*.pyo', '__pycache__', *EXCLUDED))
    init = package / '__init__.py'
    text = init.read_text(encoding='utf-8')
    text, count = re.subn(r"^VERSION = '[^']*'$", f"VERSION = '{version}'", text, flags=re.M)
    if count != 1:
        raise SystemExit('VERSION not found in src/unicum/__init__.py')
    init.write_text(text, encoding='utf-8')
    entry = stage / 'mod_unicum.py'
    shutil.copy2(ENTRY, entry)
    text, count = re.subn(r"^__version__ = '[^']*'$", f"__version__ = '{version}'",
                          entry.read_text(encoding='utf-8'), flags=re.M)
    if count != 1:
        raise SystemExit('__version__ not found in dev/mod_unicum.py.in')
    entry.write_text(text, encoding='utf-8')
    return package


def compile_all(py27: list[str], stage: Path) -> None:
    """Every .py to .pyc with the client's Python, so the magic matches; the sources are not shipped."""
    result = subprocess.run(
        py27 + ['-c',
                'import compileall, sys; sys.exit(0 if compileall.compile_dir(sys.argv[1], quiet=1, force=1) '
                'else 1)', str(stage)],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'compiling failed:\n{result.stdout}\n{result.stderr}')


def members(stage: Path) -> list[tuple[Path, str]]:
    """(file on disk, path inside the .wotmod), in a stable order."""
    out: list[tuple[Path, str]] = []
    out.append((stage / 'mod_unicum.pyc', 'res/scripts/client/gui/mods/mod_unicum.pyc'))
    package = stage / 'unicum'
    for path in sorted(package.rglob('*')):
        if not path.is_file() or path.suffix == '.py':
            continue
        out.append((path, 'res/scripts/client/unicum/' + path.relative_to(package).as_posix()))

    swfs = [swf for swf in AS3_BUILD.glob('unicum.*.swf') if not swf.name.endswith('.boot.swf')]
    swfs += list(AS3_BUILD.glob('battleVehicleMarkersApp.swf'))
    if not swfs:
        raise SystemExit('no SWFs in build/as3: run tools/build_as3.py first')
    out += [(swf, f'res/gui/flash/{swf.name}') for swf in sorted(swfs)]

    flags = sorted(FLAGS_BUILD.glob('*.png'))
    if not flags:
        raise SystemExit('no flags in build/flags: run npm run build in tools/flags first')
    out += [(flag, f'res/gui/maps/icons/unicum/flags/{flag.name}') for flag in flags]

    icons = {'unicum.png': 'icon.png', 'twitch.png': 'twitch.png'}
    for name, inside in icons.items():
        if not (ICON_BUILD / name).is_file():
            raise SystemExit(f'no build/icon/{name}: run npm run icon in tools/badges first')
        out.append((ICON_BUILD / name, f'res/gui/maps/icons/unicum/{inside}'))
    out += [(icon, f'res/gui/maps/icons/unicum/tankButton/{icon.name}')
            for icon in sorted((ICON_BUILD / 'tankButton').glob('*.png'))]

    out += [(path, 'res/' + path.relative_to(RES).as_posix()) for path in sorted(RES.rglob('*')) if path.is_file()]
    return out


def meta(version: str) -> str:
    return ('<root>\n'
            f'    <id>{MOD_ID}</id>\n'
            f'    <version>{version}</version>\n'
            f'    <name>{NAME}</name>\n'
            f'    <description>{DESCRIPTION}</description>\n'
            '</root>\n')


def main() -> None:
    parser = argparse.ArgumentParser(description='Build the released unicum.gg .wotmod.')
    parser.add_argument('--version', required=True, help='x.y.z')
    parser.add_argument('--python27', help='path to Python 2.7 (the client\'s version)')
    args = parser.parse_args()
    if not VERSION.match(args.version):
        raise SystemExit('--version must be x.y.z')

    py27 = python27(args.python27)
    DIST.mkdir(exist_ok=True)
    target = DIST / f'{MOD_ID}_{args.version}.wotmod'
    with tempfile.TemporaryDirectory() as scratch:
        stage = Path(scratch)
        stage_package(stage, args.version)
        compile_all(py27, stage)
        files = members(stage)
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
            archive.writestr('meta.xml', meta(args.version))
            for path, inside in files:
                archive.write(path, inside)
    size = target.stat().st_size
    print(f'wrote {target} ({len(files)} files, {size / 1024:.0f} KB)')
    bundle(target, args.version)


def bundle(package: Path, version: str) -> None:
    """The zip a player unzips into the game folder: the mod and openwg_gameface."""
    gameface = sorted(GAMEFACE.glob('net.openwg.gameface_*.wotmod'))
    if len(gameface) != 1:
        raise SystemExit(f'expected one net.openwg.gameface_*.wotmod in {GAMEFACE}, found {len(gameface)}')
    target = DIST / f'{NAME}_{version}.zip'
    folder = f'mods/{GAME_VERSION}'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(package, f'{folder}/{package.name}')
        archive.write(gameface[0], f'{folder}/net.openwg/{gameface[0].name}')
        for directory in RUNTIME_IMAGE_DIRS:
            archive.writestr(f'res_mods/{GAME_VERSION}/{directory}/{MARKER}', MARKER_PNG)
    print(f'wrote {target} ({target.stat().st_size / 1024:.0f} KB, with {gameface[0].name})')


if __name__ == '__main__':
    main()

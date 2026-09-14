"""Install the dev bootstrap into a World of Tanks client.

Renders dev/mod_unicum_dev.py.in with this checkout's src/ path and installs
it, so the client loads a stub that watches src/ and reloads it in place.
Run once per client, or again after moving the checkout.

    python tools/install_dev.py --game "C:/Games/World_of_Tanks_EU"

Two install shapes, because which one a client accepts is not a given:

  wotmod  a .wotmod package in mods/<version>/, the format every installed
          mod here uses, and the only one observed to load on a client
          running Aslain's script loader
  loose   a plain .py in res_mods/<version>/scripts/client/gui/mods/, which
          the loader's source says it accepts but which was not picked up

Both are installed by default; the game log says which one won. The stub is
static either way, so packaging costs nothing at edit time.

Runs on Python 3. The stub itself has to be Python 2.7, as the client is.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / 'dev' / 'mod_unicum_dev.py.in'
SRC = REPO / 'src'
STUB_NAME = 'mod_unicum_dev.py'
MOD_ID = 'gg.unicum.dev'
MOD_VERSION = '0.1.0'

# The client's loader only picks up files named mod_*.py or mod_*.pyc, and
# only from this path inside a res_mods version folder or a .wotmod root.
MODS_SUBPATH = Path('scripts') / 'client' / 'gui' / 'mods'

# Where flag PNGs live inside the resource tree, and therefore what the
# <IMG SRC="img://..."> paths in the mod resolve against.
FLAGS_SUBPATH = Path('gui') / 'maps' / 'icons' / 'unicum' / 'flags'
FLAGS_BUILD = REPO / 'build' / 'flags'

PYTHON27_CANDIDATES = [
    Path(os.path.expanduser('~/scoop/apps/python27/current/python.exe')),
    Path('C:/Python27/python.exe'),
]


def find_version(game: Path) -> str:
    """Pick the version folder matching the installed client."""
    res_mods = game / 'res_mods'
    if not res_mods.is_dir():
        raise SystemExit(f'no res_mods folder in {game}')

    versions = sorted(p.name for p in res_mods.iterdir() if p.is_dir())
    if not versions:
        raise SystemExit(f'no version folder under {res_mods}')

    # version.xml is the authority; fall back to the only folder present.
    version_xml = game / 'version.xml'
    if version_xml.is_file():
        text = version_xml.read_text(encoding='utf-8', errors='replace')
        match = re.search(r'v\.([\d.]+)', text)
        if match and match.group(1) in versions:
            return match.group(1)

    if len(versions) == 1:
        return versions[0]
    raise SystemExit(
        f'cannot tell which version to use, pass --version: {versions}')


def find_python27(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise SystemExit(f'no such interpreter: {path}')
        return path
    for candidate in PYTHON27_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which('py')
    if found:
        return Path(found)
    raise SystemExit('no Python 2.7 found, pass --python27')


def render_stub() -> str:
    # A raw string holds the path in the stub, so a trailing backslash would
    # escape the closing quote. Forward slashes work fine on Windows here.
    return TEMPLATE.read_text(encoding='utf-8').replace(
        '__SRC_ROOT__', SRC.as_posix())


def compile_stub(python27: Path, stub: Path) -> Path:
    """Byte-compile with the client's own Python, so the magic matches."""
    pyc = stub.with_suffix('.pyc')
    if pyc.exists():
        pyc.unlink()
    result = subprocess.run(
        [str(python27), '-c',
         'import py_compile, sys; py_compile.compile(sys.argv[1], '
         'cfile=sys.argv[2], doraise=True)',
         str(stub), str(pyc)],
        capture_output=True, text=True)
    if result.returncode != 0 or not pyc.is_file():
        raise SystemExit(f'compiling the stub failed:\n{result.stderr}')
    return pyc


def build_wotmod(pyc: Path, target: Path) -> None:
    """Package the compiled stub as a .wotmod.

    Stored, never deflated: the client rejected deflated members outright in
    2.3.1.3, before the entry point was even imported.
    """
    meta = (
        '<root>\n'
        f'    <id>{MOD_ID}</id>\n'
        f'    <version>{MOD_VERSION}</version>\n'
        '    <name>unicum.gg (dev bootstrap)</name>\n'
        '    <description>Loads the unicum.gg mod from a working copy and '
        'reloads it when its sources change.</description>\n'
        '</root>\n'
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr('meta.xml', meta)
        archive.write(pyc, str(Path('res') / MODS_SUBPATH / pyc.name).replace('\\', '/'))
        for flag in sorted(FLAGS_BUILD.glob('*.png')):
            inside = Path('res') / FLAGS_SUBPATH / flag.name
            archive.write(flag, str(inside).replace('\\', '/'))


def install_flags(game: Path, version: str) -> int:
    """Copy the rasterised flags into the client's resource tree.

    Loose files rather than a package, because that is enough for the client
    to find them and it keeps flag changes out of the .wotmod rebuild. They
    are only indexed at startup though: a flag added while the client runs is
    reported as `Cannot load protocol image` and never appears.
    """
    if not FLAGS_BUILD.is_dir():
        return 0
    target_dir = game / 'res_mods' / version / FLAGS_SUBPATH
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for flag in sorted(FLAGS_BUILD.glob('*.png')):
        shutil.copy2(flag, target_dir / flag.name)
        count += 1
    return count


TITLES_SWF = REPO / 'build' / 'as3' / 'unicum.titles.swf'
BADGES_BUILD = REPO / 'build' / 'badges'
BADGES_SUBPATH = Path('gui') / 'maps' / 'icons' / 'unicum' / 'badges'


def install_badges(game: Path, version: str) -> int:
    """Copy the rating badges, one folder of images per metric.

    Indexed at startup like the flags: a new or rebuilt set needs a client
    restart, and until then ratings draw as bare numbers.
    """
    if not BADGES_BUILD.is_dir():
        return 0
    target = game / 'res_mods' / version / BADGES_SUBPATH
    if target.is_dir():
        shutil.rmtree(target)
    shutil.copytree(BADGES_BUILD, target, ignore=shutil.ignore_patterns('*.json'))
    return sum(1 for p in target.iterdir() if p.is_dir())


def install_swf(game: Path, version: str) -> Path | None:
    """Copy the AS3 title view where the lobby loads SWFs from.

    Indexed at startup like the flags, so a new or rebuilt SWF needs a
    client restart. Without it, profile titles keep a language code.
    """
    if not TITLES_SWF.is_file():
        return None
    target = game / 'res_mods' / version / 'gui' / 'flash' / TITLES_SWF.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TITLES_SWF, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', required=True, type=Path,
                        help='World of Tanks install directory')
    parser.add_argument('--version',
                        help='version folder to target (autodetected)')
    parser.add_argument('--python27',
                        help='Python 2.7 interpreter used to compile the stub')
    parser.add_argument('--shape', choices=('both', 'wotmod', 'loose'),
                        default='both', help='how to install (default: both)')
    args = parser.parse_args()

    game = args.game.resolve()
    if not game.is_dir():
        raise SystemExit(f'not a directory: {game}')

    version = args.version or find_version(game)
    stub_source = render_stub()
    print(f'sources  {SRC.as_posix()}')
    print(f'client   {version}')

    if args.shape in ('both', 'loose'):
        target_dir = game / 'res_mods' / version / MODS_SUBPATH
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / STUB_NAME).write_text(stub_source, encoding='utf-8')
        print(f'loose    {target_dir / STUB_NAME}')

        flags = install_flags(game, version)
        if flags:
            print(f'flags    {flags} PNGs -> res_mods/{version}/{FLAGS_SUBPATH}')
        else:
            print('flags    none built yet (cd tools/flags && npm install && npm run build)')

        bands = install_badges(game, version)
        if bands:
            print(f'badges   {bands} metrics -> res_mods/{version}/{BADGES_SUBPATH}')
        else:
            print('badges   none built yet (cd tools/badges && npm install && npm run build)')

        swf = install_swf(game, version)
        if swf:
            print(f'swf      {swf}')
        else:
            print('swf      none built yet (python tools/build_as3.py --game ...)')

    if args.shape in ('both', 'wotmod'):
        python27 = find_python27(args.python27)
        staging = REPO / 'build'
        staging.mkdir(exist_ok=True)
        stub = staging / STUB_NAME
        stub.write_text(stub_source, encoding='utf-8')
        pyc = compile_stub(python27, stub)
        package = game / 'mods' / version / f'{MOD_ID}_{MOD_VERSION}.wotmod'
        build_wotmod(pyc, package)
        print(f'wotmod   {package}')

    print('\nRestart the client once. After that, saving a file under src/ is enough.')


if __name__ == '__main__':
    sys.exit(main())

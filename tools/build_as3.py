"""Build the AS3 half of the mod into build/as3/unicum.titles.swf.

    python tools/build_as3.py --game "C:/Games/World_of_Tanks_EU"

Fetches what the compile needs into build/as3 on first run, then compiles:

  royale/     Apache Royale (JS/SWF distribution), whose mxmlc targets SWF.
              Needs Java 11 or later on PATH.
  libs/       playerglobal.swc for Flash Player 17, and the client's own
              .swc files, taken from its gui packages. Linked externally:
              the lobby has those classes loaded already, so the SWF carries
              only our code.

The client's .swc files are re-extracted on every run, so a client update is
picked up by rebuilding.

Runs on Python 3.
"""
import argparse
import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AS3 = REPO / 'as3'
WORK = REPO / 'build' / 'as3'
LIBS = WORK / 'libs'
ROYALE = WORK / 'royale'
OUTPUT = WORK / 'unicum.titles.swf'
ENTRY = Path('src') / 'unicum' / 'TitleHtml.as'

ROYALE_URL = ('https://archive.apache.org/dist/royale/0.9.12/binaries/'
              'apache-royale-0.9.12-bin-js-swf.zip')
PLAYERGLOBAL_URL = ('https://raw.githubusercontent.com/nexussays/playerglobal/'
                    'master/17.0/playerglobal.swc')
MXMLC_JAR = ROYALE / 'royale-asjs' / 'js' / 'lib' / 'mxmlc.jar'


def fetch_royale() -> None:
    if MXMLC_JAR.is_file():
        return
    print(f'royale   downloading {ROYALE_URL} (about 200 MB)')
    with urllib.request.urlopen(ROYALE_URL) as response:
        data = response.read()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        archive.extractall(ROYALE)
    if not MXMLC_JAR.is_file():
        raise SystemExit(f'no mxmlc.jar after extracting to {ROYALE}')


def fetch_libs(game: Path) -> None:
    LIBS.mkdir(parents=True, exist_ok=True)
    playerglobal = LIBS / 'playerglobal.swc'
    if not playerglobal.is_file():
        print('libs     downloading playerglobal.swc')
        with urllib.request.urlopen(PLAYERGLOBAL_URL) as response:
            playerglobal.write_bytes(response.read())

    # .pkg files are zip archives.
    found = 0
    for package in sorted((game / 'res' / 'packages').glob('gui-part*.pkg')):
        with zipfile.ZipFile(package) as archive:
            for name in archive.namelist():
                if name.startswith('gui/flash/swc/') and name.endswith('.swc'):
                    (LIBS / Path(name).name).write_bytes(archive.read(name))
                    found += 1
    if not found:
        raise SystemExit(f'no .swc found in {game / "res" / "packages"}')
    print(f'libs     {found} client .swc files')


def compile_swf() -> None:
    java = shutil.which('java')
    if java is None:
        raise SystemExit('java not found on PATH (Java 11 or later)')
    frameworks = ROYALE / 'royale-asjs' / 'frameworks'
    # Called directly rather than through mxmlc.bat: cmd splits arguments on
    # '=', which mangles -output=... before the compiler sees it.
    result = subprocess.run(
        [java, '-Dsun.io.useCanonCaches=false', '-Xmx512m',
         f'-Droyalelib={frameworks}', '-jar', str(MXMLC_JAR),
         '--targets=SWF', '-load-config+=build-config.xml',
         f'-output={OUTPUT}', str(ENTRY)],
        cwd=AS3, capture_output=True, text=True, errors='replace')
    if result.returncode != 0 or not OUTPUT.is_file():
        raise SystemExit(f'compile failed:\n{result.stdout}\n{result.stderr}')
    print(f'swf      {OUTPUT} ({OUTPUT.stat().st_size} bytes)')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', required=True, type=Path,
                        help='World of Tanks install directory, for its .swc files')
    args = parser.parse_args()
    fetch_royale()
    fetch_libs(args.game.resolve())
    if OUTPUT.exists():
        OUTPUT.unlink()
    compile_swf()


if __name__ == '__main__':
    sys.exit(main())

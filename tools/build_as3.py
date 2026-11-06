"""Build the AS3 half of the mod into build/as3.

    python tools/build_as3.py --game "C:/Games/World_of_Tanks_EU" [--install]
    python tools/build_as3.py --client-files DIR   the live client's, off the CDN
    python tools/build_as3.py --from-mirror   no game installed: see below

Fetches what the compile needs into build/as3 on first run, then compiles:

  royale/     Apache Royale (JS/SWF distribution), whose mxmlc targets SWF.
              Needs Java 11 or later on PATH.
  libs/       playerglobal.swc for Flash Player 17, and the client's own
              .swc files. Linked externally: the lobby has those classes
              loaded already, so the SWF carries only our code.

Two things here come out of the client itself: those .swc, and the markers app
this script patches. --game reads them from an install. --client-files reads
them from a directory written by unicum-gg/wot.build's `npm run client-files`,
which rebuilds the live client's gui packages off the update CDN and records a
sha256 per file in its manifest.json: that is what the release workflow uses,
and it is as good as an install because it IS the install's bytes, at the
build players are running. --from-mirror reads
them from unicum-gg/wot.assets (see MIRROR), which publishes the client's `gui`
tree off the update CDN, and which lets this run on a machine that has never
had World of Tanks installed.

**--from-mirror never builds a release.** The mirror carries whichever build it
last extracted, and that is routinely not the live one: on 2026-10-14 its
battleVehicleMarkersApp.swf was 300743 bytes against the live client's 303622,
the whole 2879-byte difference inside the DoABC tag. That file is patched here
and ships inside the .wotmod, where it REPLACES the client's own, so a package
built from the mirror hands every player the vehicle markers of a build they
are not running. Neither flag is the default, because the difference is
invisible in the output and only shows up in somebody's game.

With --game the .swc are re-extracted on every run, so a client update is
picked up by rebuilding. From the mirror they are fetched once and kept;
delete build/as3/libs to take a newer client's.

It builds the unicum.*.swf views, and a copy of the client's own
battleVehicleMarkersApp.swf with our code added for the vehicle markers (see
patch_markers_app); unicum.markers.boot.swf is only an input to that copy.

With --install, they are copied into the client's newest res_mods folder. A
running client with the mod loaded picks a view up without a restart -- as
long as that SWF already existed when the client started (see
src/unicum/views.py). The markers app copy and unicum.markers.classes.swf
take effect at the next client start.

Runs on Python 3.
"""
import argparse
import hashlib
import io
import json
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AS3 = REPO / 'as3'
WORK = REPO / 'build' / 'as3'
LIBS = WORK / 'libs'
ROYALE = WORK / 'royale'
# One SWF per app: a view loaded into an app's service layer replaces the
# one already there.
VIEWS = (
    (Path('src') / 'unicum' / 'LobbyView.as', WORK / 'unicum.lobby.swf'),
    (Path('src') / 'unicum' / 'TeamNamesHtml.as', WORK / 'unicum.battle.swf'),
    (Path('src') / 'unicum' / 'MarkersLibrary.as', WORK / 'unicum.markers.swf'),
    # What the settings window's unicum.gg tab shows, loaded by its shell
    # (unicum.SettingsTab) into a domain of its own: a new build shows the
    # next time the window opens.
    (Path('src') / 'unicum' / 'settings' / 'SettingsLibrary.as', WORK / 'unicum.settings.swf'),
)

# Ratings by the names above vehicles (see as3/src/unicum/markers/MarkersBoot.as):
# boot code compiled on its own and added to the client's markers app, and our
# marker classes in a SWF of their own, which that boot code loads.
MARKERS_BOOT = (Path('src') / 'unicum' / 'markers' / 'UnicumMarkersApp.as', WORK / 'unicum.markers.boot.swf')
MARKERS_APP_CLASS = 'net.wg.app.impl.BattleVehicleMarkersApp'
MARKERS_ROOT_CLASS = 'unicum.markers.UnicumMarkersApp'
MARKERS_CLASSES = (Path('src') / 'unicum' / 'markers' / 'MarkersClasses.as', WORK / 'unicum.markers.classes.swf')
MARKERS_APP_RES = 'gui/flash/battleVehicleMarkersApp.swf'
MARKERS_APP = WORK / 'battleVehicleMarkersApp.swf'
# Classes the marker classes use but must not carry: the client's marker
# symbol classes they extend, compiled against stand-ins in as3/stubs, and the
# boot code, already in the app.
MARKERS_EXTERNS = ('VehicleMarker', 'Comp7VehicleMarkerUI', 'unicum.markers.MarkersBoot')

ROYALE_URL = ('https://archive.apache.org/dist/royale/0.9.12/binaries/'
              'apache-royale-0.9.12-bin-js-swf.zip')
PLAYERGLOBAL_URL = ('https://raw.githubusercontent.com/nexussays/playerglobal/'
                    'master/17.0/playerglobal.swc')
MXMLC_JAR = ROYALE / 'royale-asjs' / 'js' / 'lib' / 'mxmlc.jar'

# Where the client's own build inputs come from without a game installed.
#
# unicum-gg/wot.assets mirrors the client's `gui` tree out of the update CDN,
# one branch per client build, rebuilt daily. It carries both things this
# script takes from the client, at the same paths the packages use inside
# themselves, so reading from here and reading from an install agree.
MIRROR = 'https://raw.githubusercontent.com/unicum-gg/wot.assets/WG/'

# Inside a gui package, and inside the mirror, the client's libraries.
SWC_DIR = 'gui/flash/swc/'

# The client .swc the compiler links against: the six in as3/build-config.xml
# minus playerglobal, plus gui_battle, which only the markers classes link
# (see main). Named rather than globbed the way an install is read, because
# the mirror *accumulates*: it also keeps libraries that retired clients had,
# and linking against those would make a build depend on the day it ran.
CLIENT_LIBS = (
    'base_app-1.0-SNAPSHOT.swc',
    'common-1.0-SNAPSHOT.swc',
    'common_i18n_library-1.0-SNAPSHOT.swc',
    'gui_base-1.0-SNAPSHOT.swc',
    'gui_battle-1.0-SNAPSHOT.swc',
    'gui_lobby-1.0-SNAPSHOT.swc',
    'lobby.swc',
)


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


def fetch(url: str, what: str) -> bytes:
    """One file off the network, failing with the URL rather than a traceback."""
    try:
        with urllib.request.urlopen(url) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise SystemExit(f'{what}: HTTP {error.code} from {url}')
    except urllib.error.URLError as error:
        raise SystemExit(f'{what}: {error.reason} for {url}')


def read_client_file(client_files: Path, name: str) -> bytes:
    """One file of a client-files directory, refused unless its manifest vouches for it.

    The manifest is written in the same run as the files, from the same chain,
    so a file that does not match it was swapped or truncated afterwards.
    """
    manifest = json.loads((client_files / 'manifest.json').read_text(encoding='utf-8'))
    expected = manifest['files'].get(name)
    if expected is None:
        raise SystemExit(f'{name} is not in {client_files / "manifest.json"}')
    data = (client_files / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise SystemExit(f'{client_files / name} does not match its manifest')
    return data


def fetch_libs(game: Path | None, client_files: Path | None = None) -> None:
    LIBS.mkdir(parents=True, exist_ok=True)
    playerglobal = LIBS / 'playerglobal.swc'
    if not playerglobal.is_file():
        print('libs     downloading playerglobal.swc')
        playerglobal.write_bytes(fetch(PLAYERGLOBAL_URL, 'playerglobal.swc'))

    if client_files is not None:
        # Overwritten every run, unlike the mirror's: these are the build being
        # released, and a library kept from an earlier run is another build's.
        for name in CLIENT_LIBS:
            (LIBS / name).write_bytes(read_client_file(client_files, SWC_DIR + name))
        print(f'libs     {len(CLIENT_LIBS)} client .swc from {client_files}')
        return

    if game is None:
        missing = [name for name in CLIENT_LIBS if not (LIBS / name).is_file()]
        for name in missing:
            (LIBS / name).write_bytes(fetch(MIRROR + SWC_DIR + name, name))
        print(f'libs     {len(CLIENT_LIBS)} client .swc from the mirror'
              f' ({len(missing)} fetched)')
        return

    # .pkg files are zip archives.
    found = 0
    for package in sorted((game / 'res' / 'packages').glob('gui-part*.pkg')):
        with zipfile.ZipFile(package) as archive:
            for name in archive.namelist():
                if name.startswith(SWC_DIR) and name.endswith('.swc'):
                    (LIBS / Path(name).name).write_bytes(archive.read(name))
                    found += 1
    if not found:
        raise SystemExit(f'no .swc found in {game / "res" / "packages"}')
    print(f'libs     {found} client .swc files')


def compile_swf(entry: Path, output: Path, extra=()) -> None:
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
         f'-output={output}', *extra, str(entry)],
        cwd=AS3, capture_output=True, text=True, errors='replace')
    if result.returncode != 0 or not output.is_file():
        raise SystemExit(f'compile failed:\n{result.stdout}\n{result.stderr}')
    print(f'swf      {output} ({output.stat().st_size} bytes)')


def _tags(body: bytes, start: int):
    pos = start
    while pos < len(body):
        header, = struct.unpack_from('<H', body, pos)
        code, length, head = header >> 6, header & 0x3f, 2
        if length == 0x3f:
            length, = struct.unpack_from('<I', body, pos + 2)
            head = 6
        yield code, pos, pos + head + length
        pos += head + length


def _tag(code: int, payload: bytes) -> bytes:
    return struct.pack('<HI', code << 6 | 0x3f, len(payload)) + payload


def _swf_body(data: bytes, name: str):
    """(signature to write back, SWF version, uncompressed body after the 8-byte header)."""
    import zlib
    signature, version = data[:3], data[3]
    if signature == b'CWS':
        return b'FWS', version, zlib.decompress(data[8:])
    if signature == b'FWS':
        return b'FWS', version, data[8:]
    if signature == b'ZWS':
        import lzma
        # After the header and the compressed length: 5 bytes of LZMA1
        # properties, then a raw stream with no end marker.
        size = struct.unpack_from('<I', data, 4)[0] - 8
        filters = [lzma._decode_filter_properties(lzma.FILTER_LZMA1, data[12:17])]
        body = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=filters).decompress(data[17:], size)
        return b'FWS', version, body
    raise SystemExit(f'{name}: not a SWF ({signature!r})')


def _first_tag(body: bytes) -> int:
    return (5 + 4 * (body[0] >> 3) + 7) // 8 + 4


def _payload(body: bytes, tag_start: int, tag_end: int) -> bytes:
    header, = struct.unpack_from('<H', body, tag_start)
    return body[tag_start + (6 if header & 0x3f == 0x3f else 2):tag_end]


def read_markers_app(game: Path | None, client_files: Path | None = None) -> bytes:
    """The client's own battleVehicleMarkersApp.swf, from an install, the CDN or the mirror."""
    if client_files is not None:
        return read_client_file(client_files, MARKERS_APP_RES)
    if game is None:
        return fetch(MIRROR + MARKERS_APP_RES, MARKERS_APP_RES)
    for package in sorted((game / 'res' / 'packages').glob('gui-part*.pkg')):
        with zipfile.ZipFile(package) as archive:
            if MARKERS_APP_RES in archive.namelist():
                return archive.read(MARKERS_APP_RES)
    raise SystemExit(f'no {MARKERS_APP_RES} in {game / "res" / "packages"}')


def patch_markers_app(source: bytes, boot: Path, output: Path) -> None:
    """The client's battleVehicleMarkersApp.swf, which also runs our boot code.

    The engine's markers canvas only makes markers from classes defined in
    that movie, so the code that brings ours in has to be in it
    (as3/src/unicum/markers). Its own bytecode is left as it is: our DoABC
    tag is added next to it, and its SymbolClass tag names our subclass of
    its app as the root. src/unicum/name_markers.py then has the markers
    manager make our marker classes, found by name, in place of the
    client's. The client's file is read at build time (read_markers_app) and
    never kept in the repository.
    """
    signature, version, body = _swf_body(source, MARKERS_APP_RES)
    _, boot_version, boot_body = _swf_body(boot.read_bytes(), boot.name)

    abc = b''
    for code, tag_start, tag_end in _tags(boot_body, _first_tag(boot_body)):
        if code == 82:
            payload = _payload(boot_body, tag_start, tag_end)
            # As compiled: lazily initialised, like the client's own code.
            abc += _tag(82, payload)
    if not abc:
        raise SystemExit(f'{boot}: no DoABC tag')

    # Right after the app's own code, and the root named as our subclass of
    # the app, so the movie starts with it.
    symbol_class = next((t for t in _tags(body, _first_tag(body)) if t[0] == 76), None)
    if symbol_class is None:
        raise SystemExit(f'{MARKERS_APP_RES}: no SymbolClass tag')
    _, tag_start, tag_end = symbol_class
    payload = _payload(body, tag_start, tag_end)
    old = struct.pack('<H', 0) + MARKERS_APP_CLASS.encode('ascii') + b'\0'
    if payload.count(old) != 1:
        raise SystemExit(f'{MARKERS_APP_RES}: its root is not {MARKERS_APP_CLASS}')
    payload = payload.replace(old, struct.pack('<H', 0) + MARKERS_ROOT_CLASS.encode('ascii') + b'\0')
    body = body[:tag_start] + abc + _tag(76, payload) + body[tag_end:]
    output.write_bytes(signature + bytes([max(version, boot_version)]) + struct.pack('<I', 8 + len(body)) + body)
    print(f'patch    {output} ({output.stat().st_size} bytes)')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path,
                        help='World of Tanks install directory, which is where the client '
                             'files this needs have to come from for a release')
    parser.add_argument('--client-files', type=Path,
                        help="a directory written by wot.build's `npm run client-files`: "
                             "the live client's files off the update CDN, good for a release")
    parser.add_argument('--from-mirror', action='store_true',
                        help='read the client .swc and the markers app from the mirror '
                             'instead: for trying the compile without a game installed, '
                             'never for a package anybody will install')
    parser.add_argument('--install', action='store_true',
                        help="copy the SWFs into the client's res_mods too")
    args = parser.parse_args()
    game = args.game.resolve() if args.game else None
    client_files = args.client_files.resolve() if args.client_files else None
    if game is not None and client_files is not None:
        raise SystemExit('--game and --client-files both name the client; pass one')
    if args.install and game is None:
        raise SystemExit('--install writes into the client, so it needs --game')
    # The mirror is opt-in, and says so, because the difference is invisible in
    # the output and fatal in the game. battleVehicleMarkersApp.swf is PATCHED
    # here and then ships inside the .wotmod, where it REPLACES the client's
    # own. Measured on 2026-10-14: the live client's app was 303622 bytes, the
    # mirror's 300743, the whole 2879-byte difference inside the DoABC tag --
    # two different builds of the same file. Shipping the mirror's copy hands
    # every player the vehicle markers of a build they are not running.
    if game is None and client_files is None and not args.from_mirror:
        raise SystemExit(
            'the client .swc and battleVehicleMarkersApp.swf have to come off the\n'
            'live client: pass --game or --client-files. The mirror holds a different build of\n'
            'both, and the markers app ships inside the package and replaces the\n'
            "client's own, so a release built from it is a release that breaks the\n"
            'markers. Pass --from-mirror to compile anyway, without publishing.')
    fetch_royale()
    fetch_libs(game, client_files)
    for entry, output in VIEWS + (MARKERS_BOOT, MARKERS_CLASSES):
        if output.exists():
            output.unlink()
    for entry, output in VIEWS:
        compile_swf(entry, output)
    compile_swf(*MARKERS_BOOT, extra=('-source-path+=stubs', '-externs', MARKERS_APP_CLASS, '--'))
    compile_swf(*MARKERS_CLASSES, extra=(
        '-source-path+=stubs',
        '-external-library-path+=../build/as3/libs/gui_battle-1.0-SNAPSHOT.swc',
        '-externs', *MARKERS_EXTERNS, '--'))
    patch_markers_app(read_markers_app(game, client_files), MARKERS_BOOT[1], MARKERS_APP)
    if args.install:
        # 2.10.0.0 after 2.9.0.0, which a plain string sort gets backwards.
        folders = [folder for folder in (game / 'res_mods').iterdir() if folder.is_dir()]
        newest = max(folders, key=lambda folder: [int(part) if part.isdigit() else part
                                                  for part in folder.name.split('.')])
        target = newest / 'gui' / 'flash'
        target.mkdir(parents=True, exist_ok=True)
        for output in [output for _, output in VIEWS] + [MARKERS_CLASSES[1], MARKERS_APP]:
            shutil.copy2(output, target / output.name)
            print(f'install  {target / output.name}')


if __name__ == '__main__':
    sys.exit(main())

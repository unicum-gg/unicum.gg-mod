"""The mod's listing visuals (wgmods.net): a cover and five screenshots.

    python tools/visuals/build.py pages --game "C:/Games/World_of_Tanks_EU"
    python tools/visuals/build.py export

`pages` writes build/visuals/, one HTML page per visual (pages.py), with the
assets they draw from:

  from the game's res/packages   two maps' loading art, vehicle contours
  from tools/flags               the flags (react-flagpack, as in the mod)
  from assets/                   the unicum.gg and Twitch logos
  from unicum.gg                 Twitch's global chat badges, full size
  from captures/garage.jpg       a garage capture, cropped and dimmed

None of the game's files or Twitch's images are kept in the repository.

Each page is then captured in Chrome at its viewport and a device pixel ratio
of 2 (pages.PAGES gives the sizes; DevTools' device toolbar, or a DevTools
automation, does it), saved as build/visuals/shots/<name>.png. A headless
browser run from here would do it too, where one works.

`export` turns those captures, and captures/garage.jpg itself as the first
screenshot, into build/visuals/wgmods/*.jpg: the files to upload.

captures/garage.jpg is a capture of the client (PrintWindow on its window)
cropped to 1920x1080 at (640, 70) of a 2560x1440 garage, the Twitch panel
unfolded with sample messages from invented viewers. Replace it the same way to
show a newer garage.

Python 3 with Pillow (DDS maps need it).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / 'build' / 'visuals'
FLAGS = REPO / 'tools' / 'flags' / 'node_modules' / 'react-flagpack' / 'dist' / 'flags' / 'm'
GARAGE = HERE / 'captures' / 'garage.jpg'
# The flag pack's name where it is not the code: the United Kingdom's as a whole.
FLAG_FILES = {'GB': 'GB-UKM'}

sys.path.insert(0, str(HERE))
import pages  # noqa: E402

MAPS = {'himmelsdorf': 'gui/maps/icons/map/screen/04_himmelsdorf.dds',
        'ruinberg': 'gui/maps/icons/map/screen/08_ruinberg.dds'}
CONTOUR = 'gui/maps/icons/vehicle/contour/%s.png'
BADGES_URL = 'https://unicum.gg/api/twitch/%s/badges'
# Any channel answers with Twitch's global badges, which are all the pages use.
BADGES_CHANNEL = 'twitch'

# Where the garage cards sit in captures/garage.jpg, and the size they are shown at.
CARDS_BOX = (1520, 490, 1900, 1010)
CARDS_SIZE = (760, 1040)


def read_packaged(game: Path, names: list[str]) -> dict[str, bytes]:
    """The files of the game's res/packages/gui-part*.pkg asked for, by name."""
    found: dict[str, bytes] = {}
    for package in sorted((game / 'res' / 'packages').glob('gui-part*.pkg')):
        with zipfile.ZipFile(package) as archive:
            for name in set(names) & set(archive.namelist()):
                found[name] = archive.read(name)
    missing = set(names) - set(found)
    if missing:
        raise SystemExit('not in the game packages: %s' % ', '.join(sorted(missing)))
    return found


def game_assets(game: Path, assets: Path) -> None:
    from io import BytesIO

    from PIL import Image, ImageFilter
    contours = [CONTOUR % contour for _, contour in pages.TANKS]
    files = read_packaged(game, list(MAPS.values()) + contours)
    for name, path in MAPS.items():
        # A little blur hides the banding of the compressed texture once enlarged.
        art = Image.open(BytesIO(files[path])).convert('RGB').filter(ImageFilter.GaussianBlur(2.2))
        art.resize((1920, 1200), Image.LANCZOS).crop((0, 60, 1920, 1140)).save(assets / f'{name}.jpg', quality=94)
    (assets / 'contour').mkdir(exist_ok=True)
    for path in contours:
        (assets / 'contour' / Path(path).name).write_bytes(files[path])


def fetch(url: str) -> bytes:
    # Python's default user agent is refused in front of unicum.gg.
    request = urllib.request.Request(url, headers={'User-Agent': 'unicum.gg-mod visuals'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def twitch_badges(assets: Path) -> None:
    payload = json.loads(fetch(BADGES_URL % BADGES_CHANNEL))
    badges = {'%s.%s' % (item['set'], item['version']): item for item in payload if not item.get('channel')}
    (assets / 'tw').mkdir(exist_ok=True)
    for name in pages.TWITCH_BADGES:
        if name not in badges:
            raise SystemExit(f'Twitch has no global badge {name} any more: change pages.TWITCH_BADGES')
        (assets / 'tw' / f'{name}.png').write_bytes(fetch(badges[name]['image4x']))


def garage_assets(assets: Path) -> None:
    from PIL import Image, ImageEnhance, ImageFilter
    garage = Image.open(GARAGE).convert('RGB')
    garage.crop(CARDS_BOX).resize(CARDS_SIZE, Image.LANCZOS).save(assets / 'garage_cards.png')
    dim = garage.resize((1200, 675), Image.LANCZOS).filter(ImageFilter.GaussianBlur(3))
    ImageEnhance.Brightness(dim).enhance(0.55).save(assets / 'garage_dim.jpg', quality=92)


def build_pages(game: Path) -> None:
    if not FLAGS.is_dir():
        raise SystemExit('no flags: run npm install in tools/flags first')
    assets = OUT / 'assets'
    (assets / 'flags').mkdir(parents=True, exist_ok=True)
    for code in pages.FLAG_CODES:
        shutil.copy2(FLAGS / f'{FLAG_FILES.get(code, code)}.svg', assets / 'flags' / f'{code}.svg')
    shutil.copy2(REPO / 'assets' / 'icon.svg', assets / 'icon.svg')
    shutil.copy2(REPO / 'assets' / 'brands' / 'twitch.svg', assets / 'twitch.svg')
    game_assets(game, assets)
    twitch_badges(assets)
    garage_assets(assets)
    shutil.copy2(HERE / 'common.css', OUT / 'common.css')
    for name, (page, width, height) in pages.PAGES.items():
        (OUT / f'{name}.html').write_text(page(), encoding='utf-8')
        print(f'{name}.html: capture at {width}x{height}, device pixel ratio 2')
    (OUT / 'shots').mkdir(exist_ok=True)
    print(f'then save the captures as {OUT / "shots"}/<name>.png and run: build.py export')


def export() -> None:
    from PIL import Image
    target = OUT / 'wgmods'
    target.mkdir(parents=True, exist_ok=True)
    Image.open(GARAGE).convert('RGB').save(target / '1-garage.jpg', quality=92)
    for name, (_, width, height) in pages.PAGES.items():
        shot = OUT / 'shots' / f'{name}.png'
        if not shot.is_file():
            raise SystemExit(f'no capture {shot}')
        image = Image.open(shot).convert('RGB')
        if image.size != (width * 2, height * 2):
            raise SystemExit(f'{shot.name} is {image.size[0]}x{image.size[1]}, not {width * 2}x{height * 2}')
        image.save(target / f'{name}.jpg', quality=92)
    print(f'wrote {target}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Build the listing visuals.')
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('pages', help='write the HTML pages and their assets')
    build.add_argument('--game', required=True, type=Path, help='the World of Tanks install')
    commands.add_parser('export', help='turn the captures into the files to upload')
    args = parser.parse_args()
    if args.command == 'pages':
        build_pages(args.game)
    else:
        export()


if __name__ == '__main__':
    main()

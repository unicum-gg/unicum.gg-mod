"""A rating badge as PNG bytes, drawn in the client from a few masks.

The badges were 30 000 PNGs rendered ahead (one a value, per metric), 36 MB
for a mod. A badge is a fixed grid, so the same pixels come from pieces
instead: badge_glyphs.json holds each digit's coverage in its 6px cell (with a
1px margin a glyph can reach into) and the rounded corners' coverage, rendered
once by tools/badges/glyphs.mjs with the font and rasteriser the whole set was
rendered with. Laying them out:

    3px padding | a 6px cell per digit, 2px between thousands | 3px padding

on the band's colour, text in white. The PNG is written by hand with zlib:
the client's Python has no imaging library.

Plain Python, so tools/checks can compare it with the images it replaces.
"""
import json
import struct
import zlib

HEIGHT = 12
PADDING = 3
DIGIT_WIDTH = 6
GROUP_WIDTH = 2

# A package resource (resources.py).
_GLYPHS = 'badge_glyphs.json'
_masks = []


def _load():
    if not _masks:
        from unicum import resources
        _masks.append(json.loads(resources.read(_GLYPHS)))
    return _masks[0]


def layout(value):
    """'3323' -> ['3', ' ', '3', '2', '3']: grouped by thousands, like the site."""
    digits = '%d' % value
    out = []
    for index, char in enumerate(digits):
        if index and (len(digits) - index) % 3 == 0:
            out.append(' ')
        out.append(char)
    return out


def width_of(value):
    return 2 * PADDING + sum(GROUP_WIDTH if char == ' ' else DIGIT_WIDTH for char in layout(value))


def _rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def pixels(value, hex_color):
    """(width, rows of [r, g, b, a] per pixel) for a badge."""
    masks = _load()
    width = width_of(value)
    red, green, blue = _rgb(hex_color)
    # The band: full coverage but at the rounded corners.
    shape = [[255] * width for _ in range(HEIGHT)]
    corner = len(masks['left'][0])
    for y in range(HEIGHT):
        for x in range(corner):
            shape[y][x] = masks['left'][y][x]
            shape[y][width - corner + x] = masks['right'][y][x]
    # The text's coverage, each digit's mask at its cell, a margin either side.
    text = [[0] * width for _ in range(HEIGHT)]
    x0 = PADDING
    margin = masks['margin']
    for char in layout(value):
        if char == ' ':
            x0 += GROUP_WIDTH
            continue
        mask = masks['digits'][char]
        for y in range(HEIGHT):
            row = mask[y]
            for dx, coverage in enumerate(row):
                x = x0 - margin + dx
                if coverage and 0 <= x < width:
                    text[y][x] = min(255, text[y][x] + coverage)
        x0 += DIGIT_WIDTH
    rows = []
    for y in range(HEIGHT):
        row = []
        for x in range(width):
            a = text[y][x] / 255.0
            back = shape[y][x] / 255.0
            # White text over the band, over transparency.
            out_a = a + back * (1 - a)
            if out_a <= 0:
                row.extend((0, 0, 0, 0))
                continue
            mix = lambda channel: int(round((255 * a + channel * back * (1 - a)) / out_a))
            row.extend((mix(red), mix(green), mix(blue), int(round(out_a * 255))))
        rows.append(row)
    return width, rows


def _chunk(kind, data):
    return (struct.pack('>I', len(data)) + kind + data
            + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))


def png(value, hex_color):
    """PNG bytes of a badge: 8-bit RGBA, no interlacing."""
    width, rows = pixels(value, hex_color)
    raw = b''.join(b'\x00' + bytes(bytearray(row)) for row in rows)
    header = struct.pack('>IIBBBBB', width, HEIGHT, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + _chunk(b'IDAT', zlib.compress(raw, 9))
            + _chunk(b'IEND', b''))

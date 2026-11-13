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
    """3323 -> ['3', ' ', '3', '2', '3']: grouped by thousands, like the site.

    A string passes through as its own characters, already grouped or not:
    that is how a win rate ('59%', '58.7%') and a rounded battle count
    ('161k') reach the same grid as a rating.
    """
    if not isinstance(value, (int, long, float)):
        return list(value)
    digits = '%d' % value
    out = []
    for index, char in enumerate(digits):
        if index and (len(digits) - index) % 3 == 0:
            out.append(' ')
        out.append(char)
    return out


def cell_of(char):
    """How wide this glyph's cell is. A space between thousands is its own width."""
    if char == ' ':
        return GROUP_WIDTH
    return (_load().get('cells') or {}).get(char, DIGIT_WIDTH)


def width_of(value):
    return 2 * PADDING + sum(cell_of(char) for char in layout(value))


def caption_height():
    """How tall a caption row is, or 0 if the glyph set was built without one."""
    return int((_load().get('caption') or {}).get('height') or 0)


def caption_cell_of(char):
    """How wide this caption glyph's cell is, 0 for one the set does not hold.

    0 rather than a default width: a caption is a short code this mod
    chooses itself, so a character missing from the set is this mod's own
    mistake, and a badge that silently grew a gap would hide it.
    """
    return ((_load().get('caption') or {}).get('cells') or {}).get(char, 0)


def _rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _band(width, height, left, right):
    """The badge's own coverage: full, but for the rounded corners.

    A box shorter than the corner masks were rendered for is left square:
    rounding it from a taller mask would round it by the wrong amount, and
    a 6px chip has no room for a 2px radius anyway.
    """
    shape = [[255] * width for _ in range(height)]
    if len(left) != height:
        return shape
    corner = len(left[0])
    for y in range(height):
        for x in range(corner):
            shape[y][x] = left[y][x]
            shape[y][width - corner + x] = right[y][x]
    return shape


def _lay(target, chars, cell_width, masks, margin, x0, y0, scale=1.0):
    """Add each glyph's coverage to `target`, left to right from (x0, y0).

    A character the set was rendered without leaves its cell empty rather
    than stopping the badge: half a figure drawn is more use than none, and
    the gap is visible enough to be reported.
    """
    height, width = len(target), len(target[0])
    for char in chars:
        mask = masks.get(char)
        if mask is None:
            x0 += cell_width(char)
            continue
        for dy, row in enumerate(mask):
            y = y0 + dy
            if not 0 <= y < height:
                continue
            for dx, coverage in enumerate(row):
                x = x0 - margin + dx
                if coverage and 0 <= x < width:
                    target[y][x] = min(255, target[y][x] + int(coverage * scale))
        x0 += cell_width(char)


def _compose(width, height, shape, text, hex_color):
    """White text over the band, over transparency."""
    red, green, blue = _rgb(hex_color)
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            a = text[y][x] / 255.0
            back = shape[y][x] / 255.0
            out_a = a + back * (1 - a)
            if out_a <= 0:
                row.extend((0, 0, 0, 0))
                continue
            mix = lambda channel: int(round((255 * a + channel * back * (1 - a)) / out_a))
            row.extend((mix(red), mix(green), mix(blue), int(round(out_a * 255))))
        rows.append(row)
    return rows


def pixels(value, hex_color):
    """(width, rows of [r, g, b, a] per pixel) for a badge.

    `value` is a number (grouped by thousands) or a string drawn as it is.
    """
    masks = _load()
    width = width_of(value)
    shape = _band(width, HEIGHT, masks['left'], masks['right'])
    text = [[0] * width for _ in range(HEIGHT)]
    _lay(text, layout(value), cell_of, masks['digits'], masks['margin'], PADDING, 0)
    return width, _compose(width, HEIGHT, shape, text, hex_color)


# The corner tag. Pinned to the badge's bottom right and hanging off it,
# rather than stamped into it: a badge is drawn exactly as wide as its
# figure, so anything laid inside the corner lands on the last digit, and
# the digit is what is being read. Overhanging keeps the badge the size it
# is everywhere else in the mod and keeps every digit of it visible.
TAG_PAD = 1
# How far the chip reaches back over the badge. Enough to read as attached
# to it rather than as a second thing floating beside it.
TAG_OVERLAP = 3
# The chip's own band, dark enough for white letters to read on it against
# any of the scales' colours.
TAG_BAND = '#1F1F1F'


def tag_size(value, tag):
    """(width, height) of the whole image: the badge plus the chip's overhang."""
    width, height = width_of(value), HEIGHT
    chip, rows = _chip_size(tag)
    if not chip:
        return width, height
    return width + chip - TAG_OVERLAP, height + rows - TAG_OVERLAP


def _chip_size(tag):
    """(width, height) of the chip itself, (0, 0) without a glyph set for it."""
    rows = caption_height()
    ink = sum(caption_cell_of(char) for char in tag)
    if not rows or not ink:
        return 0, 0
    return ink + 2 * TAG_PAD, rows


def tagged_pixels(value, hex_color, tag):
    """(width, height, rows) for a badge with `tag` pinned to its corner.

    The badge itself is the badge: same width, same height, same pixels as
    `pixels` gives, drawn into the top left of a slightly larger image. The
    chip is a small dark box at the bottom right, overlapping the badge's
    corner and hanging past it, with the tag in white on it.
    """
    chip, rows = _chip_size(tag)
    badge_width, _ = width_of(value), HEIGHT
    if not chip:
        width, pixel_rows = pixels(value, hex_color)
        return width, HEIGHT, pixel_rows
    width, height = tag_size(value, tag)
    _, drawn = pixels(value, hex_color)
    out = [[0] * (width * 4) for _ in range(height)]
    for y in range(HEIGHT):
        out[y][:badge_width * 4] = drawn[y]
    # The chip, with the same rounded corners as a badge of its own size:
    # a square box beside a rounded one reads as a mistake.
    masks = _load()
    shape = _band(chip, rows, masks['left'], masks['right'])
    letters = [[0] * chip for _ in range(rows)]
    _lay(letters, tag, caption_cell_of, (masks.get('caption') or {}).get('glyphs') or {},
         masks['margin'], TAG_PAD, 0)
    patch = _compose(chip, rows, shape, letters, TAG_BAND)
    x0, y0 = width - chip, height - rows
    for y in range(rows):
        row = patch[y]
        target = out[y0 + y]
        for x in range(chip):
            at = x * 4
            if row[at + 3]:
                target[(x0 + x) * 4:(x0 + x) * 4 + 4] = row[at:at + 4]
    return width, height, out


def _chunk(kind, data):
    return (struct.pack('>I', len(data)) + kind + data
            + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))


def _png(width, height, rows):
    raw = b''.join(b'\x00' + bytes(bytearray(row)) for row in rows)
    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + _chunk(b'IDAT', zlib.compress(raw, 9))
            + _chunk(b'IEND', b''))


def png(value, hex_color):
    """PNG bytes of a badge: 8-bit RGBA, no interlacing."""
    width, rows = pixels(value, hex_color)
    return _png(width, HEIGHT, rows)


def tagged_png(value, hex_color, tag):
    """PNG bytes of a badge with its name pinned to its bottom right corner."""
    width, height, rows = tagged_pixels(value, hex_color, tag)
    return _png(width, height, rows)

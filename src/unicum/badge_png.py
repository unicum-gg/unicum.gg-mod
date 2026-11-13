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


def caption_width_of(text):
    return 2 * PADDING + sum(caption_cell_of(char) for char in text)


def captioned_size(value, caption):
    """(width, height) of a badge with `caption` under its figure.

    As wide as the wider of the two rows. Which one that is depends on the
    number: WNX is wider than 412 and narrower than 23 184.
    """
    return max(width_of(value), caption_width_of(caption)), HEIGHT + caption_height()


def _rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _band(width, height, left, right):
    """The badge's own coverage: full, but for the rounded corners."""
    shape = [[255] * width for _ in range(height)]
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


# How much of the figure's brightness the caption keeps. Under it rather
# than beside it, and quieter than it: the number is what is read and the
# caption is what it is called. Full white would make them two figures.
CAPTION_ALPHA = 0.72


def captioned_pixels(value, hex_color, caption):
    """(width, height, rows) for a badge with `caption` under its figure.

    Both rows are centred, because which of the two is wider depends on the
    number. Left-aligning them would put the caption under the start of a
    long count and under the whole of a short one.
    """
    masks = _load()
    low = masks.get('caption') or {}
    width, height = captioned_size(value, caption)
    shape = _band(width, height, low.get('left') or masks['left'],
                  low.get('right') or masks['right'])
    text = [[0] * width for _ in range(height)]
    chars = layout(value)
    _lay(text, chars, cell_of, masks['digits'], masks['margin'],
         (width - sum(cell_of(char) for char in chars)) // 2, 0)
    _lay(text, caption, caption_cell_of, low.get('glyphs') or {}, masks['margin'],
         (width - sum(caption_cell_of(char) for char in caption)) // 2, HEIGHT,
         CAPTION_ALPHA)
    return width, height, _compose(width, height, shape, text, hex_color)


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


def captioned_png(value, hex_color, caption):
    """PNG bytes of a badge with its name on a row under its figure."""
    width, height, rows = captioned_pixels(value, hex_color, caption)
    return _png(width, height, rows)

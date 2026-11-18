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


def corner_width():
    """How many pixels wide a rounded corner is, or 0 without a mask for one."""
    mask = _load().get('left') or []
    return len(mask[0]) if mask else 0


def _corners(mask, height):
    """A corner mask fitted to a box `height` tall.

    A rounded corner is the same curve whatever its box is tall: the two
    ends are drawn and everything between them is solid -- in the mask on
    disk, two rows of curve at each end of twelve. So a mask rendered for a
    twelve pixel badge serves a ten pixel chip exactly, by keeping both of
    its ends and dropping that much of the solid middle, and a taller box
    by repeating the middle. Not by scaling: scaling a coverage mask
    softens the curve, and the chip would stop being the corner the badges
    beside it are drawn with, which is the whole point of sharing it.

    A box too short to hold both ends keeps as much of each as fits. At
    that size there is no corner to speak of and no better answer.
    """
    if len(mask) == height:
        return mask
    if height < len(mask):
        top = height // 2
        return mask[:top] + mask[len(mask) - (height - top):]
    half = len(mask) // 2
    middle = [list(mask[half]) for _ in range(height - len(mask))]
    return mask[:half] + middle + mask[half:]


def _band(width, height, left, right):
    """The badge's own coverage: full, but for the rounded corners.

    Every box this module draws is rounded the same way, whatever its
    height: a chip standing over a column sits right above the badges it
    names, and a square box over a rounded one is read as a mistake.

    A box too narrow to hold two corners is left square, which is the only
    case left: there is nowhere to put them.
    """
    shape = [[255] * width for _ in range(height)]
    corner = len(left[0]) if left else 0
    if not corner or width < 2 * corner:
        return shape
    left, right = _corners(left, height), _corners(right, height)
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


def pixels(value, hex_color, width=0):
    """(width, rows of [r, g, b, a] per pixel) for a badge.

    `value` is a number (grouped by thousands) or a string drawn as it is.

    `width` widens the badge past its own figure and centres that figure in
    it, which is what turns a list of badges into a column: drawn to their
    own size, "100.0%" and "9.1%" are twelve pixels apart and no two rows
    line up. Narrower than the figure is ignored -- a column too narrow for
    one of its values would have to cut it, and a figure cut is a figure
    that lies.
    """
    masks = _load()
    natural = width_of(value)
    width = max(int(width or 0), natural)
    shape = _band(width, HEIGHT, masks['left'], masks['right'])
    text = [[0] * width for _ in range(HEIGHT)]
    _lay(text, layout(value), cell_of, masks['digits'], masks['margin'],
         PADDING + (width - natural) // 2, 0)
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
    """(width, height) of the whole image: the badge plus the chip's overhang.

    The height is the badge's own, always. These images sit inline in a row
    of ordinary badges and flags, and Scaleform lines an inline image up by
    its bottom edge: one a few pixels taller than its neighbours lifts its
    own badge off the line they share, and the row goes crooked. So the
    chip overhangs to the right only.
    """
    chip, _ = _chip_size(tag)
    if not chip:
        return width_of(value), HEIGHT
    return width_of(value) + chip - TAG_OVERLAP, HEIGHT


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
    `pixels` gives, drawn into the left of a slightly wider image. The chip
    is a small dark box sitting on the badge's bottom right corner and
    hanging past its right edge, with the tag in white on it.
    """
    chip, rows = _chip_size(tag)
    badge_width = width_of(value)
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


def chip_size(tag, width=0):
    """(width, height) of a chip standing on its own, (0, 0) without glyphs.

    `width` widens it to the column it names, exactly as it widens a badge:
    a name over a column is read as belonging to that column, and one drawn
    to its own letters sits in the middle of a width it does not claim.
    Narrower than the letters is ignored, for the reason `pixels` gives.
    """
    chip, rows = _chip_size(tag)
    if not chip:
        return 0, 0
    return max(int(width or 0), chip), rows


def chip_pixels(tag, width=0):
    """(width, height, rows) for a chip with no badge behind it.

    The same chip `tagged_pixels` stamps into a badge's corner, drawn alone:
    a column of figures is named by the chip its figures wear, so the two
    have to be one drawing rather than two drawings of one idea.

    `width` widens the band and centres the letters in it, which is what
    makes the name the width of the column under it.
    """
    chip, rows = _chip_size(tag)
    if not chip:
        return 0, 0, []
    width = max(int(width or 0), chip)
    masks = _load()
    shape = _band(width, rows, masks['left'], masks['right'])
    letters = [[0] * width for _ in range(rows)]
    _lay(letters, tag, caption_cell_of, (masks.get('caption') or {}).get('glyphs') or {},
         masks['margin'], TAG_PAD + (width - chip) // 2, 0)
    return width, rows, _compose(width, rows, shape, letters, TAG_BAND)


def chip_png(tag, width=0):
    """A chip on its own as PNG bytes, or None when it cannot be drawn."""
    width, height, rows = chip_pixels(tag, width)
    return _png(width, height, rows) if width else None


def _chunk(kind, data):
    return (struct.pack('>I', len(data)) + kind + data
            + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))


def _png(width, height, rows):
    raw = b''.join(b'\x00' + bytes(bytearray(row)) for row in rows)
    header = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', header) + _chunk(b'IDAT', zlib.compress(raw, 9))
            + _chunk(b'IEND', b''))


def png(value, hex_color, width=0):
    """PNG bytes of a badge: 8-bit RGBA, no interlacing."""
    width, rows = pixels(value, hex_color, width)
    return _png(width, HEIGHT, rows)


def blank_png(width):
    """PNG bytes of `width` by HEIGHT of nothing at all, or None for no width.

    What holds a column's place on a row that has no figure for it.

    Drawn, rather than the column simply left out of that row: the rows are
    laid out from one end, so a row one badge short does not come up one
    badge short, it comes up one badge OVER. Every column after the gap
    slides along into the next one's place, and a screen of rows each
    missing a different figure reads as a staircase rather than as columns.

    An image rather than spaces, which is the other way to take up room: a
    space is measured by whatever font the field is set in, at whatever
    interface scale the player runs, and the width that has to be matched
    here is a badge's. An image is exactly as wide as it says it is.
    """
    width = int(width or 0)
    if width <= 0:
        return None
    return _png(width, HEIGHT, [[0] * (width * 4) for _ in range(HEIGHT)])


def tagged_png(value, hex_color, tag):
    """PNG bytes of a badge with its name pinned to its bottom right corner."""
    width, height, rows = tagged_pixels(value, hex_color, tag)
    return _png(width, height, rows)

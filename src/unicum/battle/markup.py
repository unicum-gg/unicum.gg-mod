"""How wide a piece of markup draws, and the two columns a row is given.

The battle view is handed its markers as text and lays them out itself, so it
has to be told what each piece will take. Nothing here knows what a rating is
or where it came from: it counts images by the width they declare and text by
the character, which is the whole of it.
"""
from __future__ import absolute_import

import re

_IMG_WIDTH = re.compile(r'<IMG[^>]*\bwidth="(\d+)"', re.IGNORECASE)
# Any tag at all. Counting the text inside one as text was close enough while
# the only markup here was images, and stopped being close enough the day a
# figure could arrive as `<font color="#8a8a8a">` -- whose three 8s would have
# been measured as three digits of rating.
_TAG = re.compile(r'<[^>]+>')

# A space in markup; a bare number's digits, when a badge cannot draw.
_SPACE_WIDTH = 4
_DIGIT_WIDTH = 7


def markup_width(markup):
    """Pixels the markup takes: its images' widths, and text by the character."""
    images = sum(int(width) for width in _IMG_WIDTH.findall(markup))
    text = _TAG.sub('', markup)
    return images + text.count(' ') * _SPACE_WIDTH + sum(c.isdigit() for c in text) * _DIGIT_WIDTH


def row_width(widths):
    """How wide a row holding every column measures, in the order they are drawn.

    One slot per column, each after the single space that keeps two inline
    images from showing a seam, so the widths alone are not the answer.
    """
    return sum(_SPACE_WIDTH + int(width or 0) for width in (widths or {}).values())


def padded(markup, width, spacer):
    """`markup` with an empty image in front, so the whole measures `width`.

    What puts a row that is not built of badges under the columns anyway.

    A row of badges needs none of this: each of its slots is drawn to its
    column's width and a hole is an image of exactly that, so the row comes
    out the full width by construction and `short` is nothing. What this
    catches is the rows that are text -- the grey stand-in shown while a
    tank's record is still being fetched, and the grey figures of a mode
    the site publishes no per-tank record for. Text is measured rather than
    drawn, so it lands wherever its digits take it; the screens lay a row
    out from its far end, so filling the difference in front of it puts
    what the row does hold at the end of the columns instead of adrift
    between them.
    """
    short = int(width or 0) - markup_width(markup) - _SPACE_WIDTH
    hole = spacer(short) if short > 0 else ''
    return ' ' + hole + markup if hole else markup


def icon_markers(flags, badge):
    """[badge html, its width, flags html, their width], drawn as two columns."""
    badge, flags = badge.strip(), flags.strip()
    return [badge, markup_width(badge), flags, markup_width(flags)]

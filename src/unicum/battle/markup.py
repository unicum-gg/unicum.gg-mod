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


def icon_markers(flags, badge):
    """[badge html, its width, flags html, their width], drawn as two columns."""
    badge, flags = badge.strip(), flags.strip()
    return [badge, markup_width(badge), flags, markup_width(flags)]

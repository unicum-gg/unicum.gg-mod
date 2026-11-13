"""How a badge's text is written, and where its file is written to.

The pure half of `badges.py`: given a number, the characters a badge draws;
given those characters, the name of the file they are drawn into. No state,
no client, nothing that needs a Badges to exist -- which is why the checks
can call all of it directly, and why it sits here now that the class beside
it has grown a captioned badge of its own.

Imported back into `badges` under its own names, so a caller that has always
asked `badges.count` still asks `badges.count`.
"""
from __future__ import absolute_import

from unicum import badge_png

# Where a battle count stops being written out in full.
#
# Not a matter of width. A badge is one PNG per value and colour, written to
# disk and loaded by its path, and a battle count is unbounded and different
# for every player: an exact count would draw a new file for nearly everyone
# seen. Rounded to thousands past this, the set of files stays small.
_COMPACT_FROM = 10000

# Written with the folder; the client can load it only once it started with
# the folder there.
MARKER = 'ready.png'


def count(battles):
    """A battle count as a badge draws it: 844, or 161k past ten thousand.

    Rounded to whole thousands rather than to a decimal. `161.8k` would be
    ten times as many distinct badges as `161k`, and the count of distinct
    badges is the count of PNG files this mod writes into the player's game
    folder (see `_COMPACT_FROM`).

    A plain space groups the thousands below that, not a comma and not a
    dot: both are decimal separators somewhere this mod is played, and
    "22,565" read as twenty-two is the kind of wrong nobody notices.
    """
    battles = int(battles)
    if battles >= _COMPACT_FROM:
        return '%dk' % (battles // 1000)
    out, rest = '', abs(battles)
    while rest >= 1000:
        out = ' %03d%s' % (rest % 1000, out)
        rest //= 1000
    return '%d%s' % (rest, out)


def winrate(value, decimal=False):
    """A win rate as a badge draws it: '59%', or '58.7%' when asked.

    Whole percent by default, to read as the rating badge beside it reads:
    that one is an integer too, and a tenth of a point of win rate is noise
    at a glance. It also keeps the pill four characters wide instead of six.
    """
    return ('%.1f%%' % value) if decimal else ('%d%%' % round(value))


def badge_width(value):
    return badge_png.width_of(value)


def _slug(text):
    """A badge's text as a file name: '58.7%' -> '58-7pct', '161k' -> '161k'.

    Windows has no quarrel with a dot in a name but plenty with a percent in
    some shells, and a name that round-trips through a resource path should
    not need quoting anywhere. Letters, digits and hyphens only.
    """
    out = []
    for char in text:
        if char.isalnum():
            out.append(char)
        elif char == '%':
            out.append('pct')
        else:
            out.append('-')
    return ''.join(out)


def _drawable(path):
    """ResMgr.isFile, or the disk outside the client."""
    try:
        import ResMgr
    except ImportError:
        return True
    return bool(ResMgr.isFile(path))

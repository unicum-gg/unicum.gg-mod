"""Rating badges for Scaleform name fields, one image per value.

A player name field re-applies its own text format after the text is set
(CommonsLobby.formatPlayerName reads the field's format and passes it to
setTextFormat), so a <FONT COLOR> in the name is painted over and there is
no way to give text a background. Images are left alone, so the site's badge
-- a white number on its colour band -- is an image. Whole badges rather than
digits laid side by side: Scaleform leaves a seam between adjacent inline
images whatever hspace says, and every join showed.

They are drawn in the client, the first time a value is shown, into one
folder of resource files (badge_png.py; they used to ship all 30 000, 36 MB):

    gui/maps/icons/unicum/badges/wnx.3323.7a4fb2.png   "3 323" on its WNX band

The band's colour is in the name, so a scale the site changes draws new
badges rather than showing the old ones.

The client lists its resource folders as it starts: a file written into a
folder it knew loads at once, one in a folder created later does not until the
next start. So a marker file is written into the folder and asked of ResMgr:
if the client can load it, it can load the badges too; if not (the folder is
new, on the mod's first run), a rating is shown as its bare number until the
next start.
"""
import logging
import os

from unicum import badge_png, config

_logger = logging.getLogger('unicum.badges')

METRICS = ('wn7', 'wn8', 'wnx', 'pr', 'wtr')

# Past this a figure is written as plain text instead of drawn as a badge.
#
# Five digits, not four, since Wargaming's two joined the list: the top band
# of their scales opens at 9,600 (PR) and 9,900 (WTR) and closes at nothing,
# so a four-digit cap took the badge away from exactly the players whose
# colour says the most. The cap is here to refuse a figure that cannot be
# real before it becomes a PNG in someone's game folder, and twenty thousand
# is above every rating either side of this ever serves.
MAX_VALUE = 20000

_HEIGHT = badge_png.HEIGHT

_IMG = '<IMG SRC="img://%s" width="%d" height="%d" vspace="-3"/>'

# The fallback when a badge cannot be drawn: the figure as plain text in the
# client's own named font. Without a face Scaleform falls back to its default,
# which is a serif, and the numbers come out in a different typeface from
# every other word on the screen. The size is left alone so they inherit the
# field's, whatever interface scale a player has set.
_FACE = "face='$FieldFont'"
_DIM = '<font ' + _FACE + ' color="#8a8a8a">%s</font>'

# One plain space between badges. They are inline images, and Scaleform
# leaves a visible seam between two that touch.
_GAP = ' '

# The band under a battle count. Every other badge takes its colour from a
# scale the site serves; a battle count has none, and inventing one would
# claim a meaning that does not exist. So it is the one neutral pill, dark
# enough to sit behind white text and to read as the quietest of the three.
NEUTRAL = '#4a4a4a'

# Where a battle count stops being written out in full.
#
# Not a matter of width. A badge is one PNG per value and colour, written to
# disk and loaded by its path, and a battle count is unbounded and different
# for every player: an exact count would draw a new file for nearly everyone
# met, thirty at a time as a battle loads, in a folder that never stops
# growing. Rounded to thousands the whole set is about a thousand files and
# stays that way for good.
_COMPACT_FROM = 10000


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


# Written with the folder; the client can load it only once it started with the folder there.
_MARKER = 'ready.png'


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


class Badges(object):

    def __init__(self, scales=None, directory=None, res_path=None, drawable=_drawable):
        self._scales = scales
        self._dir = directory if directory is not None else config.BADGES_DIR
        self._res_path = res_path or config.BADGES_RES_PATH
        self._drawable = drawable
        # Names this session has already seen on disk; see `_ensure`.
        self._on_disk = set()
        self._ready = self._prepare()
        _logger.info('rating badges %s, in %s', 'drawn' if self._ready else 'as numbers until the next start',
                     os.path.abspath(self._dir) if self._dir else '<none>')

    def rating(self, entry, settings, surface):
        """' ' + the surface's rating as its badge, a bare number, or '' without one.

        A bare number when the badge cannot draw.
        """
        value = settings.rating(entry, surface)
        if value is None:
            return ''
        return ' ' + (self.markup(settings.metric(surface), value) or '%d' % round(value))

    def extras(self, entry, settings, surface, compact=False):
        """' ' + the win rate and battle count this surface shows, or ''.

        Badges, like the rating they sit beside, rather than text: coloured
        text next to a pill read as two different languages on one line, and
        the pill is the one this mod already speaks. The win rate takes its
        band from the site's own nine-step win rate scale; the battle count
        has no scale and takes the one neutral band.

        `compact` is accepted and ignored. A badge count is already rounded,
        because its width is not what bounds it (see `_COMPACT_FROM`).
        """
        if entry is None or not entry.known:
            return ''
        parts = []
        window = settings.extra('winrate', surface)
        if window is not None:
            value = entry.stat('winrate', window)
            if value is not None:
                text = winrate(value, settings.winrate_decimal())
                color = self._scales.color('winrate', value, 'percent') if self._scales else None
                # `or` rather than a branch on the colour: a band the scale
                # gives is still no badge when the client cannot load one,
                # and dropping the figure would be worse than drawing it
                # plainly.
                parts.append(self._pill(text, color) or _DIM % text)
        window = settings.extra('battles', surface)
        if window is not None:
            value = entry.stat('battles', window)
            if value is not None:
                text = count(value)
                parts.append(self._pill(text, NEUTRAL) or _DIM % text)
        if not parts:
            return ''
        return ' ' + _GAP.join(parts)

    def vehicle(self, record, settings, surface):
        """' ' + what a player does on the tank they brought, or ''.

        The mode's own figures and nothing else. A record whose scope is
        'overall' is the career record this row carries anyway, and drawing
        the same number where a reader expects "on this tank, in this mode"
        would be a lie about where it came from.

        The rating is the same drawing as the career one -- same scale, same
        file on disk -- because it is the same measurement over a smaller set
        of battles. Two drawings of one number drift; one does not.
        """
        if record is None or not record.known or record.scope != 'mode':
            return ''
        parts = []
        metric = settings.vehicle_metric(surface)
        value = record.rating(metric) if metric else None
        if value is not None:
            parts.append(self.markup(metric, value) or _DIM % ('%d' % round(value)))
        # The count rides on the choice already made for this surface: a
        # reader who wanted no counts beside the career rating does not
        # suddenly want one here. It earns its place all the same, because on
        # one tank it is the number that says whether the rating beside it
        # means anything -- seventy battles and four read the same otherwise.
        if settings.extra('battles', surface) is not None and record.battles:
            text = count(record.battles)
            parts.append(self._pill(text, NEUTRAL) or _DIM % text)
        if not parts:
            return ''
        return ' ' + _GAP.join(parts)

    def picture(self, text, color):
        """(resource path, width, height) of a badge of arbitrary text, or None.

        What `_pill` draws, without the markup around it. The Scaleform
        surfaces want an `<IMG>` tag and the Gameface ones want the three
        pieces to put in a style, and it is the same badge either way: one
        drawing, two wrappings, rather than two drawings that can drift.
        """
        if not self._ready or not color:
            return None
        name = '%s.%s.png' % (_slug(text), color.lstrip('#').lower())
        if not self._ensure(name, lambda: badge_png.png(text, color)):
            return None
        return '%s/%s' % (self._res_path, name), badge_png.width_of(text), _HEIGHT

    def _pill(self, text, color):
        """One badge of arbitrary text on `color`, or '' when it cannot draw."""
        found = self.picture(text, color)
        return _IMG % found if found is not None else ''

    def markup(self, metric, value):
        """htmlText for a rating badge, or None when it cannot draw."""
        image = self.image(metric, value)
        if image is None:
            return None
        return _IMG % image

    def image(self, metric, value):
        """(resource path, width, height) of a rating's badge, or None when it cannot draw."""
        if not self._ready or metric not in METRICS or value is None or self._scales is None:
            return None
        value = int(round(value))
        if not 0 <= value <= MAX_VALUE:
            return None
        color = self._scales.color(metric, value)
        if not color:
            return None
        name = '%s.%d.%s.png' % (metric, value, color.lstrip('#').lower())
        if not self._ensure(name, lambda: badge_png.png(value, color)):
            return None
        return '%s/%s' % (self._res_path, name), badge_width(value), _HEIGHT

    def _ensure(self, name, draw):
        """Whether `name` is on disk, drawing it once if it is not.

        The answer is remembered for the session, and that is the whole point
        of this method. Both callers run inside the client's VO builders, so
        this is reached once per badge per player per redraw, and a detachment
        list is two hundred players: without the memo that is a `stat` syscall
        per badge, every redraw, forever, for an answer that cannot change.

        It cannot change because nothing in the mod removes a badge once it is
        written, and a file appearing is only ever good news: `_prepare` has
        already established that the folder was there when the client started,
        which is what makes a file written now drawable at all.
        """
        if name in self._on_disk:
            return True
        disk = os.path.join(self._dir, name)
        if not os.path.isfile(disk) and not self._write(disk, draw()):
            return False
        self._on_disk.add(name)
        return True

    def _prepare(self):
        """Whether badges can draw this session: the folder was there when the client started."""
        if not self._dir:
            return False
        marker = os.path.join(self._dir, _MARKER)
        if not os.path.isfile(marker) and not self._write(marker, badge_png.png(0, '#000000')):
            return False
        # `ResMgr.purge` was tried here and does not help: it drops a cached
        # section so the next read hits the disk again, but the index itself
        # is built once at startup, and a folder that was not in it then stays
        # out of it. Measured in the client, drawable=False after purging.
        return self._drawable('%s/%s' % (self._res_path, _MARKER))

    @staticmethod
    def _write(path, data):
        try:
            directory = os.path.dirname(path)
            if not os.path.isdir(directory):
                os.makedirs(directory)
            with open(path, 'wb') as handle:
                handle.write(data)
            return True
        except (IOError, OSError):
            _logger.exception('could not write %s', path)
            return False

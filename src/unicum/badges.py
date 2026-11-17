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
from unicum.badge_files import BadgeFiles
from unicum.badge_text import (BATTLES, MARKER as _MARKER, ON_TANK, WIN_RATE,
                               _drawable, _slug, badge_width, caption, count,
                               winrate)

_logger = logging.getLogger('unicum.badges')


def _column(widths, name):
    """The width of one column out of a caller's measurements, or 0.

    0 means "draw it to its own size", which is what everywhere that is not
    a column wants: a contacts row and a profile line put a badge after a
    name, and padding one there would be a gap in the middle of a sentence.
    """
    return int((widths or {}).get(name) or 0)

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
class Badges(object):

    def __init__(self, scales=None, directory=None, res_path=None, drawable=_drawable):
        self._scales = scales
        self._dir = directory if directory is not None else config.BADGES_DIR
        self._res_path = res_path or config.BADGES_RES_PATH
        # Whether a badge can be written and then drawn this session, and
        # the writing itself: badge_files.py.
        self._files = BadgeFiles(self._dir, self._res_path, drawable)
        self._ready = self._files.ready
        _logger.info('rating badges %s, in %s', 'drawn' if self._ready else 'as numbers until the next start',
                     os.path.abspath(self._dir) if self._dir else '<none>')

    def rating(self, entry, settings, surface, width=0):
        """' ' + the surface's rating as its badge, a bare number, or '' without one.

        A bare number when the badge cannot draw.

        `width` is the column this badge stands in, when it stands in one:
        drawn to their own size, 2 442 and 896 are eight pixels apart and no
        two rows line up. See `picture`.
        """
        value = settings.rating(entry, surface)
        if value is None:
            return ''
        return ' ' + (self.markup(settings.metric(surface), value, width)
                      or '%d' % round(value))

    def extras(self, entry, settings, surface, compact=False, widths=None):
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
                # `or` rather than a branch on the colour: a band the scale
                # gives is still no badge when the client cannot load one,
                # and dropping the figure would be worse than drawing it
                # plainly. `winrate_markup` makes that choice once.
                parts.append(self.winrate_markup(value, settings.winrate_decimal(),
                                                 _column(widths, 'winrate')))
        window = settings.extra('battles', surface)
        if window is not None:
            value = entry.stat('battles', window)
            if value is not None:
                parts.append(self.count_markup(value, _column(widths, 'battles')))
        if not parts:
            return ''
        return ' ' + _GAP.join(parts)

    def vehicle(self, record, settings, surface, widths=None):
        """' ' + what a player does on the tank they brought, or ''.

        Drawn as pills for the mode asked about, and in plain grey for the
        tank's whole record -- every mode together, which is what the site
        sends back for a mode Wargaming publishes no per-vehicle block about
        at all: Frontline, Onslaught, Steel Hunter. That record is still
        about this tank and this was throwing it away, on the belief that it
        was the player's career. It is not: a career figure covers every tank
        they own, and the question here is what they do in THIS one.

        Grey is the same thing it means on the row beside it -- "true, but
        not the figure you asked for" -- and it reads apart from a career
        fallback without a second convention, since that one is a bare
        four-digit rating and this one carries a percent and a count.

        The rating is the same drawing as the career one -- same scale, same
        file on disk -- because it is the same measurement over a smaller set
        of battles. Two drawings of one number drift; one does not.
        """
        if record is None or not record.known:
            return ''
        on_mode = record.scope == 'mode'
        # A surface told to show nothing shows nothing here either. The count
        # below no longer rides on `extra`, which asked this question on its
        # own, so the surface has to be asked directly or a row turned off
        # entirely comes back to life the moment somebody holds Alt.
        if not settings.shows(surface):
            return ''
        parts = []
        metric = settings.vehicle_metric(surface)
        value = record.rating(metric) if metric else None
        if value is not None:
            drawn = self.markup(metric, value, _column(widths, 'rating')) if on_mode else None
            parts.append(drawn or _DIM % ('%d' % round(value)))
        elif record.winrate is not None:
            # No WN rating for this mode, and there never will be: the
            # expected values those scales are built from are computed on
            # random battles alone, so a skirmish, a stronghold or a global
            # map battle has none. The win rate on the tank is the figure
            # that survives, it sits on a scale the site publishes, and it
            # beats leaving a lone battle count to stand for a player --
            # which is what a skirmish drew until tonight.
            text = winrate(record.winrate, settings.winrate_decimal())
            color = self._scales.color('winrate', record.winrate, 'percent') if self._scales else None
            # The tank's win rate stands in the rating's column when there is
            # no WN rating for the mode, so it is the rating's column it has
            # to be as wide as.
            parts.append((self._pill(text, color, _column(widths, 'rating'))
                          if on_mode else '') or _DIM % text)
        # Drawn whatever the surface was told about battle counts, which is
        # the one place this mod overrides that choice and the reason is the
        # figure beside it: a career count is twenty thousand and says nothing
        # a reader did not assume, while a count on one tank is four or four
        # hundred and is the whole difference between a rating worth reading
        # and noise. Turning counts off is a judgement about the first one.
        if record.battles:
            text = count(record.battles)
            parts.append((self._pill(text, NEUTRAL, _column(widths, 'battles'))
                          if on_mode else '') or _DIM % text)
        if not parts:
            return ''
        return ' ' + _GAP.join(parts)

    def plain(self, entry, settings, surface):
        """' ' + the surface's rating as plain grey text, or ''.

        The stand-in while a per-vehicle record is not in hand, and for a tank
        the site holds nothing about. A pill is a figure drawn on the scale
        its colour names; the same number in grey text beside its neighbours'
        pills says "this is the career figure, not the one you asked for"
        without a glyph the badge font has not got -- it draws digits, a
        percent, a dot and a k, and nothing else.

        The rating alone, without the win rate and the count that follow it
        elsewhere: this is a row saying what it does not know yet, and the
        less room it takes while it says so the better.
        """
        value = settings.rating(entry, surface)
        if value is None:
            return ''
        return ' ' + _DIM % ('%d' % round(value))

    def winrate_markup(self, value, decimal=False, width=0):
        """A win rate as its badge, or as plain grey text when none can draw.

        The site's own nine-step win rate scale gives the band. Here rather
        than at each caller because three of them now want the same figure
        drawn the same way: a player's row, a tank's record, and a team's
        average.
        """
        text = winrate(value, decimal)
        color = self._scales.color('winrate', value, 'percent') if self._scales else None
        return self._pill(text, color, width) or _DIM % text

    def band(self, scale, value, unit=None):
        """The colour this scale puts `value` in, or None without a scale.

        Exposed because the settings preview draws the same badges with a
        caption under them, and a caption changes the file, not the band:
        asking the scale here keeps the one answer in one place.
        """
        if self._scales is None or value is None:
            return None
        return self._scales.color(scale, value, unit) if unit else self._scales.color(scale, value)

    def tagged_markup(self, text, color, tag):
        """htmlText for a badge with `tag` pinned to its bottom right corner.

        The badge keeps the size it has everywhere else in the mod; the tag
        is a small dark chip overhanging its corner, which is what leaves
        every digit of the figure visible.

        Only the settings window asks for one. A battle row is thirty lines
        of three badges and would be ninety chips in the narrowest column
        this mod draws; the window is where a reader is asking what the
        figures are, and the only place with the room to answer.

        '' when the badge cannot draw at all, like every other badge here.
        """
        if not self._ready or not color or not tag:
            return ''
        # `text` may be a number, which is how a rating arrives: it is the
        # drawing that groups it by thousands, and the name only has to be
        # unique and spellable.
        key = text if isinstance(text, basestring) else '%d' % text
        chip, rows = badge_png._chip_size(tag)
        # The chip's size is in the name, and it is there for one reason: a
        # badge already on disk is never drawn again, and this chip has been
        # redesigned twice. Both times the file kept its name, so every
        # player who had seen the old one kept seeing it, stretched to the
        # new one's width. Size in the name, and a redesign simply asks for
        # a file nobody has.
        name = '%s.%s%dx%d.%s.png' % (_slug(key), _slug(tag).lower(), chip, rows,
                                      color.lstrip('#').lower())
        if not self._files.ensure(name, lambda: badge_png.tagged_png(text, color, tag)):
            return ''
        width, height = badge_png.tag_size(text, tag)
        return _IMG % ('%s/%s' % (self._res_path, name), width, height)

    def chip_markup(self, tag):
        """htmlText for a chip on its own: what names a column of figures.

        The same chip the mod stamps into a badge's corner, which is the
        whole point of drawing it from the same code: a column headed "WR"
        and a badge wearing "WR" have to be the one marking, or they read as
        two conventions and the reader has to learn both.

        '' when it cannot be drawn, like every other badge here.
        """
        if not self._ready or not tag:
            return ''
        chip, rows = badge_png.chip_size(tag)
        if not chip:
            return ''
        # Its size in the name, for the reason `tagged_markup` gives: a file
        # already on disk is never drawn again, so a redesign has to ask for
        # a name nobody has.
        name = 'chip.%s%dx%d.png' % (_slug(tag).lower(), chip, rows)
        if not self._files.ensure(name, lambda: badge_png.chip_png(tag)):
            return ''
        return _IMG % ('%s/%s' % (self._res_path, name), chip, rows)

    def count_markup(self, battles, width=0):
        """A battle count as its badge, or as plain grey text when none draws.

        Named rather than inlined because the settings preview builds the
        same row one piece at a time, to put each piece's name beside it.
        Two places asking for a battle count is two chances to round it
        differently, and this is the one that rounds it.
        """
        text = count(battles)
        return self._pill(text, NEUTRAL, width) or _DIM % text

    def picture(self, text, color, width=0):
        """(resource path, width, height) of a badge of arbitrary text, or None.

        What `_pill` draws, without the markup around it. The Scaleform
        surfaces want an `<IMG>` tag and the Gameface ones want the three
        pieces to put in a style, and it is the same badge either way: one
        drawing, two wrappings, rather than two drawings that can drift.

        `width` widens the badge and centres the figure in it, which is what
        makes a column of them. It rides in the FILE NAME, for the reason
        every other size here does: a badge already on disk is never drawn
        again, so a badge of the same value at another width has to be a
        file nobody has.
        """
        if not self._ready or not color:
            return None
        drawn = max(int(width or 0), badge_png.width_of(text))
        name = '%s.%s.%d.png' % (_slug(text), color.lstrip('#').lower(), drawn)
        if not self._files.ensure(name, lambda: badge_png.png(text, color, drawn)):
            return None
        return '%s/%s' % (self._res_path, name), drawn, _HEIGHT

    def _pill(self, text, color, width=0):
        """One badge of arbitrary text on `color`, or '' when it cannot draw."""
        found = self.picture(text, color, width)
        return _IMG % found if found is not None else ''

    def markup(self, metric, value, width=0):
        """htmlText for a rating badge, or None when it cannot draw."""
        image = self.image(metric, value, width)
        if image is None:
            return None
        return _IMG % image

    def image(self, metric, value, width=0):
        """(resource path, width, height) of a rating's badge, or None when it cannot draw.

        `width` widens it into its column; the drawn width rides in the file
        name, since a badge already on disk is never drawn again.
        """
        if not self._ready or metric not in METRICS or value is None or self._scales is None:
            return None
        value = int(round(value))
        if not 0 <= value <= MAX_VALUE:
            return None
        color = self._scales.color(metric, value)
        if not color:
            return None
        drawn = max(int(width or 0), badge_width(value))
        name = '%s.%d.%s.%d.png' % (metric, value, color.lstrip('#').lower(), drawn)
        if not self._files.ensure(name, lambda: badge_png.png(value, color, drawn)):
            return None
        return '%s/%s' % (self._res_path, name), drawn, _HEIGHT

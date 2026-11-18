"""The chip that names a figure: in a badge's corner, or standing on its own.

A chip is the small dark label the mod writes a figure's name on, WR or BTL
or 30D, and there are two places one is drawn. Stamped into the bottom right
corner of a badge, which is how the settings window says what each badge in
its preview is; and alone over a column of badges, which is how a battle
screen and the detachment room name their columns. The two are one drawing,
in badge_png, and one piece of code, here: a column headed WR over badges
wearing WR is one marking, and two drawings of it would drift into two.

A mixin on `Badges` rather than a module of plain functions: both halves
reach for the badge folder and for whether this client can load a badge at
all, which is what a `Badges` holds and what nothing else should have to.

Split out of `badges.py` when that module went past the size this repo holds
its modules to.
"""
from __future__ import absolute_import

from unicum import badge_png
from unicum.badge_files import IMG as _IMG
from unicum.badge_text import _slug


class ChipBadges(object):
    """Drawing the chip that names a figure, either way it is worn."""

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
        # The chip's size and its corner are in the name, and they are there
        # for one reason: a badge already on disk is never drawn again, and
        # this chip has been redesigned three times. The first two times the
        # file kept its name, so every player who had seen the old one kept
        # seeing it, stretched to the new one's width. The drawing in the
        # name, and a redesign simply asks for a file nobody has -- which is
        # what the corner is doing there, the third redesign being the day
        # it stopped being square.
        name = '%s.%s%dx%dc%d.%s.png' % (_slug(key), _slug(tag).lower(), chip, rows,
                                         badge_png.corner_width(),
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
        found = self.chip_picture(tag)
        return _IMG % found if found is not None else ''

    def chip_picture(self, tag, width=0):
        """(resource path, width, height) of a chip on its own, or None.

        What `chip_markup` wraps for Scaleform, unwrapped: a Gameface page
        puts the same three pieces in a style instead of in an `<IMG>` tag,
        and the chip over a column of the battle Tab screen has to be the
        same drawing as the chip in the corner of a badge, or the screen
        reads as two conventions.
        """
        if not self._ready or not tag:
            return None
        chip, rows = badge_png.chip_size(tag, width)
        if not chip:
            return None
        # Its size and its corner in the name, for the reason
        # `tagged_markup` gives: a file already on disk is never drawn
        # again, so a redesign has to ask for a name nobody has.
        name = 'chip.%s%dx%dc%d.png' % (_slug(tag).lower(), chip, rows,
                                        badge_png.corner_width())
        if not self._files.ensure(name, lambda: badge_png.chip_png(tag, width)):
            return None
        return '%s/%s' % (self._res_path, name), chip, rows

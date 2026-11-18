"""Badges on disk: whether one is there, and putting it there once.

A badge is a PNG the mod draws itself and the client loads by path, so every
drawing here ends in the same two questions -- is this file already written,
and can the client load it at all this session. Those two are the whole of
this module, and they have nothing to do with what a badge says.

Split out of `badges.py` when that module went past the size this repo holds
its modules to.
"""
from __future__ import absolute_import

import logging
import os

from unicum import badge_png
from unicum.badge_text import MARKER as _MARKER

_logger = logging.getLogger('unicum.badge_files')

#: How a Scaleform field is told to load one of these files.
#:
#: Here, with the folder and the names, because it is the other half of the
#: same answer: this module decides where a badge lives, and this is what a
#: field is handed to go and get it. The two drifting apart is a badge
#: written to one path and asked for at another, which draws nothing and
#: says nothing about why.
IMG = '<IMG SRC="img://%s" width="%d" height="%d" vspace="-3"/>'


class BadgeFiles(object):
    """The folder a mod's badges live in, and what is in it."""

    def __init__(self, directory, res_path, drawable):
        self._dir = directory
        self._res_path = res_path
        self._drawable = drawable
        # Names this session has already seen on disk; see `ensure`.
        self._on_disk = set()
        self.ready = self._prepare()

    def ensure(self, name, draw):
        """Whether `name` is on disk, drawing it once if it is not.

        The answer is remembered for the session, and that is the whole point
        of this method. Its callers run inside the client's VO builders, so
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

    def blank(self, width):
        """The resource path of an empty slot `width` wide, or None.

        A badge like any other as far as this module is concerned: a file
        with a name, written once, loaded by that name. Its width is in the
        name for the same reason every other badge's size is -- a file
        already on disk is never drawn again, so another width has to be
        another name.
        """
        width = int(width or 0)
        if width <= 0 or not self.ready:
            return None
        name = 'blank.%d.png' % width
        if not self.ensure(name, lambda: badge_png.blank_png(width)):
            return None
        return '%s/%s' % (self._res_path, name)

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

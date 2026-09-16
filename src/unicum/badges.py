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

METRICS = ('wn7', 'wn8', 'wnx')
MAX_VALUE = 9999

_HEIGHT = badge_png.HEIGHT

_IMG = '<IMG SRC="img://%s" width="%d" height="%d" vspace="-3"/>'

# Written with the folder; the client can load it only once it started with the folder there.
_MARKER = 'ready.png'


def badge_width(value):
    return badge_png.width_of(value)


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
        disk = os.path.join(self._dir, name)
        if not os.path.isfile(disk) and not self._write(disk, badge_png.png(value, color)):
            return None
        return '%s/%s' % (self._res_path, name), badge_width(value), _HEIGHT

    def _prepare(self):
        """Whether badges can draw this session: the folder was there when the client started."""
        if not self._dir:
            return False
        marker = os.path.join(self._dir, _MARKER)
        if not os.path.isfile(marker) and not self._write(marker, badge_png.png(0, '#000000')):
            return False
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

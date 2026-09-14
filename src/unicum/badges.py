"""Rating badges for Scaleform name fields, one image per value.

A player name field re-applies its own text format after the text is set
(CommonsLobby.formatPlayerName reads the field's format and passes it to
setTextFormat), so a <FONT COLOR> in the name is painted over and there is
no way to give text a background. Images are left alone, so the site's badge
-- a white number on its colour band -- is an image, rendered in advance by
tools/badges for every whole value:

    badges/wnx/3323.png     "3 323" on its WNX band

Whole badges rather than digits laid side by side: Scaleform leaves a seam
between adjacent inline images whatever hspace says, and every join showed.

The images are resource files, indexed when the client starts, so a metric
whose images were missing at startup cannot draw this session and the caller
falls back to the bare number.
"""
import logging
import os

from unicum import config

_logger = logging.getLogger('unicum.badges')

METRICS = ('wnx', 'wn8')
MAX_VALUE = 9999

# Mirrors tools/badges/build.mjs, which the <IMG> width has to match.
_HEIGHT = 12
_PADDING = 3
_DIGIT_WIDTH = 6
_GROUP_WIDTH = 2

_IMG = '<IMG SRC="img://%s/%s/%d.png" width="%d" height="%d" vspace="-3"/>'


def badge_width(value):
    digits = len('%d' % value)
    return 2 * _PADDING + digits * _DIGIT_WIDTH + ((digits - 1) // 3) * _GROUP_WIDTH


class Badges(object):

    def __init__(self, directory=None, res_path=None):
        self._dir = directory if directory is not None else config.BADGES_DIR
        self._res_path = res_path or config.BADGES_RES_PATH
        self._metrics = self._scan()
        _logger.info('badges usable for %s from %s', sorted(self._metrics) or 'no metric',
                     os.path.abspath(self._dir) if self._dir else '<none>')

    def rating(self, entry, metric='wnx'):
        """' ' + a rating as its badge, a bare number, or '' without one.

        The recent value, or the lifetime one while the recent is not
        computed (Entry.rating). A bare number when the badge cannot draw.
        """
        value = entry.rating(metric) if entry is not None else None
        if value is None:
            return ''
        return ' ' + (self.markup(metric, value) or '%d' % round(value))

    def markup(self, metric, value):
        """htmlText for a rating badge, or None when it cannot draw."""
        if metric not in self._metrics or value is None:
            return None
        value = int(round(value))
        if not 0 <= value <= MAX_VALUE:
            return None
        return _IMG % (self._res_path, metric, value, badge_width(value), _HEIGHT)

    def _scan(self):
        """Metrics whose badges are on disk and known to the resource manager.

        Being on disk is not enough. A reload runs this again long after the
        client started, and images installed since then are files ResMgr never
        indexed: Scaleform logs "Cannot load protocol image" for each one, for
        every name, on every redraw. The first and last value stand for the
        whole set, which install_dev.py always copies together.
        """
        if not self._dir or not os.path.isdir(self._dir):
            return set()
        indexed = _indexed()
        usable = set()
        for metric in METRICS:
            ends = [(os.path.join(self._dir, metric, '%d.png' % v),
                     '%s/%s/%d.png' % (self._res_path, metric, v)) for v in (0, MAX_VALUE)]
            if all(os.path.isfile(disk) and indexed(res) for disk, res in ends):
                usable.add(metric)
        return usable


def _indexed():
    """ResMgr.isFile, or a stand-in that trusts the disk outside the client."""
    try:
        import ResMgr
    except ImportError:
        return lambda path: True
    return ResMgr.isFile

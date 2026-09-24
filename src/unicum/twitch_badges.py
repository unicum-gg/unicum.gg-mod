"""The badges Twitch viewers wear in chat (subscriber, moderator, VIP...).

A chat message names its badges and nothing more: the IRC `badges` tag says
`subscriber/12,moderator/1`. unicum.gg resolves those pairs to images for a
channel (GET /api/twitch/{login}/badges, from Twitch's API, which needs a
token the mod cannot carry): Twitch's global badges, and the channel's own
subscriber and bits images where it has them.

A badge is downloaded the first time a message carries it, into one flat
folder of resource files:

    gui/maps/icons/unicum/twitch/badges/global.moderator.1.png
    gui/maps/icons/unicum/twitch/badges/license__.subscriber.12.png

Flat, because the client lists its resource folders once, as it starts: a
file written into a folder it knew draws at once, while one in a folder
created later stays invisible to it (ResMgr.isFile says so, and <IMG> draws
nothing) until the next start. tools/install_dev.py creates the folder, so a
badge draws as soon as it is on disk. ResMgr.isFile is asked before drawing,
being the client's own answer to whether the image will load.
"""
import logging
import os
import re
import urllib

from unicum import config

_logger = logging.getLogger('unicum.twitch_badges')

RES_PATH = 'gui/maps/icons/unicum/twitch/badges'

# Twitch draws them at 18px; the battle chat's line is the Glitch's 14px.
_SIZE = 14
_IMG = '<IMG SRC="img://%s" width="%d" height="%d" vspace="-3"/>'

# Set ids, versions and logins go into file names, joined by dots.
_PART = re.compile(r'^[A-Za-z0-9_-]{1,64}$')

# Downloads at once, so a busy chat's first minute does not open a hundred.
_IN_FLIGHT = 4
_RETRY_SECONDS = 300.0


def parse_badges(value):
    """('subscriber/12', 'moderator/1') from an IRC `badges` tag; bad pairs left out."""
    badges = []
    for pair in (value or '').split(','):
        badge_set, _, version = pair.partition('/')
        if _PART.match(badge_set) and _PART.match(version):
            badges.append('%s/%s' % (badge_set, version))
    return tuple(badges)


def badges_url(api_base, login):
    return '%s/api/twitch/%s/badges' % (api_base.rstrip('/'), urllib.quote(login, safe=''))


def read_badges(payload):
    """{'set/version': (image url, the channel's own)} from the endpoint's answer."""
    found = {}
    badges = payload.get('badges') if isinstance(payload, dict) else None
    for badge in badges if isinstance(badges, list) else ():
        if not isinstance(badge, dict):
            continue
        key = '%s/%s' % (badge.get('set'), badge.get('version'))
        url = badge.get('image1x')
        if parse_badges(key) == (key,) and isinstance(url, basestring) and url.startswith('https://'):
            found[key] = (url, badge.get('channel') is True)
    return found


def res_path(login, key, channel):
    owner = login if channel else 'global'
    return '%s/%s.%s.png' % (RES_PATH, owner, key.replace('/', '.'))


def drawable(path):
    """Whether the client can load this resource now: known to its index."""
    try:
        import ResMgr
        return bool(ResMgr.isFile(path))
    except Exception:
        _logger.exception('could not ask ResMgr about %s', path)
        return False


class ChatBadges(object):
    """Badge images for one channel's chat, fetched as messages need them."""

    def __init__(self, session, drawable=drawable):
        self._session = session
        self._drawable = drawable
        self._login = None
        self._urls = None          # key -> (url, channel), once answered
        self._drawn = set()        # res paths known to draw
        self._pending = []         # (url, disk path)
        self._queued = set()
        self._in_flight = 0
        # The folder itself is not made here: `first_run.prepare()` makes both
        # image folders as the mod loads, before anything draws, and asks for
        # the one restart they need. Made at the first badge instead, it would
        # have cost a streamer a further client start that nothing explained.

    def follow(self, login):
        """The channel whose badges are drawn; asks unicum.gg for them once."""
        if login == self._login:
            return
        self._login, self._urls = login, None
        if login:
            self._ask(login)

    def markup(self, badges):
        """The <IMG> tags for a message's badges that can draw now."""
        return ''.join(_IMG % (source, _SIZE, _SIZE) for source in self.sources(badges))

    def sources(self, badges):
        """The resource paths of a message's badges that can draw now."""
        return [source for source in (self._source(key) for key in badges) if source]

    def _source(self, key):
        login = self._login
        if not login:
            return None
        known = self._urls.get(key) if self._urls is not None else None
        candidates = [known[1]] if known else [True, False]
        for channel in candidates:
            path = res_path(login, key, channel)
            if path in self._drawn or self._drawable(path):
                self._drawn.add(path)
                return path
        if known:
            self._download(known[0], res_path(login, key, known[1]))
        return None

    def _ask(self, login):
        from unicum.api.http import parse

        def answered(response):
            if login != self._login:
                return
            payload = parse(response, 'the Twitch badges of %s' % login)
            if payload is None:
                self._session.callback(_RETRY_SECONDS, lambda: login == self._login and self._ask(login))
                return
            self._urls = read_badges(payload)
            _logger.info('%s Twitch badges known for %s', len(self._urls), login)

        self._session.fetch(badges_url(config.API_BASE, login), answered, timeout=config.API_TIMEOUT)

    def _download(self, url, path):
        disk = config.res_mods_file(path)
        if not disk or disk in self._queued or os.path.isfile(disk):
            return
        self._queued.add(disk)
        self._pending.append((url, disk))
        self._next()

    def _next(self):
        while self._pending and self._in_flight < _IN_FLIGHT:
            url, disk = self._pending.pop(0)
            self._in_flight += 1
            self._session.fetch(url, lambda response, disk=disk: self._received(response, disk),
                                timeout=config.API_TIMEOUT)

    def _received(self, response, disk):
        self._in_flight -= 1
        body = getattr(response, 'body', None)
        if getattr(response, 'responseCode', None) == 200 and body:
            try:
                directory = os.path.dirname(disk)
                if not os.path.isdir(directory):
                    # Created now, the folder stays unknown to the client
                    # until it restarts; install_dev.py creates it beforehand.
                    os.makedirs(directory)
                    _logger.warning('created %s: badges draw from the next start', directory)
                with open(disk, 'wb') as handle:
                    handle.write(body)
                _logger.debug('cached %s', disk)
            except (IOError, OSError):
                _logger.exception('could not cache %s', disk)
        else:
            _logger.warning('could not download a Twitch badge: HTTP %s',
                            getattr(response, 'responseCode', None))
        self._next()

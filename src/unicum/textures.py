"""Serves flag images from the client's resource tree.

The flags themselves are put there ahead of time: tools/flags rasterises the
Flagpack set and tools/install_dev.py copies it in. What this module adds is
the fallback for a flag that is not there. It is downloaded the first time a
player who needs it is seen, and kept, so it shows up from the next session
on. That fallback depends on unicum.gg serving /flags/s/<CODE>.png, which it
does not yet: today it logs a failed fetch and nothing more.

Images are referenced by resource path rather than handed to the engine as
memory textures. That was tried first, since wg_addScaleformTexture needs no
restart and is how the client draws clan emblems and rare achievement icons.
It does not scale: with all 252 flags registered before anything drew, a
contacts list still rendered exactly one. Every client usage shows a single
image at a time, so nothing there ever exercised more than one. Resource
paths have no such ceiling -- the client draws its own icons in every row of
every list this way.

The cost is ResMgr's index, which is built once at startup. A file that
appears later is reported as `Cannot load protocol image` no matter what,
which is why only files present when the client started are offered. What
arrives during a session shows up in the next one.
"""
import base64
import logging
import os

from unicum import config

_logger = logging.getLogger('unicum.textures')


class FlagCache(object):
    """Disk-backed images, addressed by the path the client can resolve."""

    def __init__(self, session, cache_dir=None, res_path=None):
        self._session = session
        self._dir = cache_dir or config.CACHE_DIR
        self._res_path = res_path or config.FLAGS_RES_PATH
        self._failed = set()
        self._in_flight = set()
        # Snapshotted once, because this is the question that matters: not
        # "is the file there now" but "was it there when ResMgr indexed".
        # Anything downloaded later is on disk and still unusable today.
        self._available = self._scan()
        _logger.info('%s images usable from %s', len(self._available),
                     os.path.abspath(self._dir) if self._dir else '<none>')

    def source(self, key):
        """`img://...` for an image the client can resolve, else None.

        Never blocks: callers run inside view builders, so a flag that is not
        ready yet is simply absent this session.
        """
        if key in self._available:
            return 'img://%s/%s.png' % (self._res_path, key)
        if key not in self._failed and key not in self._in_flight:
            self._download(key)
        return None

    def data_uri(self, key):
        """The same flag inlined as a data: URI, for pages outside Scaleform.

        The Stronghold list is a web page in the embedded browser, where the
        resource tree means nothing. unicum.gg's own flag URLs sit behind a
        bot challenge that an <img> request cannot pass, so the bytes already
        on disk are handed over instead: no request, nothing to be blocked.
        """
        if key not in self._available:
            return None
        path = os.path.join(self._dir, '%s.png' % key)
        try:
            with open(path, 'rb') as handle:
                data = handle.read()
        except IOError:
            _logger.exception('could not read %s', path)
            return None
        return 'data:image/png;base64,' + base64.b64encode(data)

    def _scan(self):
        if not self._dir or not os.path.isdir(self._dir):
            return set()
        try:
            return {name[:-4] for name in os.listdir(self._dir)
                    if name.endswith('.png')}
        except OSError:
            _logger.exception('could not read %s', self._dir)
            return set()

    def _download(self, key):
        if not self._dir:
            self._failed.add(key)
            return
        path = os.path.join(self._dir, '%s.png' % key)
        if os.path.isfile(path):
            # Already fetched in an earlier session but after that session's
            # index was built. Nothing to do but wait for the next start.
            self._failed.add(key)
            return

        self._in_flight.add(key)
        url = '%s/flags/s/%s.png' % (config.API_BASE, key)

        def received(response):
            self._in_flight.discard(key)
            code = getattr(response, 'responseCode', None)
            body = getattr(response, 'body', None)
            if code != 200 or not body:
                _logger.warning('fetch failed for %s: HTTP %s', key, code)
                self._failed.add(key)
                return
            if self._write(path, body):
                _logger.info('cached %s (%s bytes), available next session',
                             key, len(body))
            self._failed.add(key)

        _logger.info('fetching %s', url)
        self._session.fetch(url, received, timeout=config.API_TIMEOUT)

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
            # A cache that cannot be written is slower, not broken.
            _logger.exception('could not cache %s', path)
            return False

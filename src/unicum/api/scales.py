"""The site's rating colour scales, from GET /ratings/scales.

unicum.gg paints every WN8, WNx and win rate with a nine-step scale, and
serves the scale itself so a client never re-implements the thresholds and
drifts the day they change. It is region-less and moves rarely, so it is
fetched at most once a day and kept on disk, which also means a number can
be painted before the network answers.
"""
import json
import logging
import os
import time

from unicum import config
from unicum.api.http import parse

_logger = logging.getLogger('unicum.api')

_MAX_AGE = 24 * 3600


class RatingScales(object):

    def __init__(self, session, store=None, api_base=None):
        self._session = session
        self._api_base = (api_base or config.API_BASE).rstrip('/')
        self._store = store if store is not None else config.SCALES_STORE
        self._scales = {}      # name -> {'unit': ..., 'bands': [...]}
        self._fetched_at = 0.0
        self._in_flight = False
        self._load()
        if time.time() - self._fetched_at > _MAX_AGE:
            self.refresh()

    def color(self, scale, value, unit=None):
        """'#RRGGBB' for a value on a scale, or None if it cannot be painted.

        Each scale declares the unit its bands are written in, and that has
        changed once already (win rates went from `ratio` to `percent`). So a
        caller says which unit its own value is in -- /resolve serves win
        rates as percentages -- and the conversion follows the scale.
        """
        info = self._scales.get(scale)
        if info is None or value is None:
            return None
        declared = info.get('unit')
        if unit == 'percent' and declared == 'ratio':
            value = value / 100.0
        elif unit == 'ratio' and declared == 'percent':
            value = value * 100.0
        for band in info.get('bands') or ():
            low, high = band.get('from'), band.get('to')
            if (low is None or value >= low) and (high is None or value < high):
                return band.get('hex')
        return None

    def refresh(self):
        if self._in_flight:
            return
        self._in_flight = True

        def received(response):
            self._in_flight = False
            payload = parse(response, 'ratings/scales')
            if payload is None:
                return
            scales = self._index(payload)
            if scales:
                self._scales, self._fetched_at = scales, time.time()
                self._save(payload)

        self._session.fetch('%s/api/ratings/scales' % self._api_base, received,
                            timeout=config.API_TIMEOUT)

    @staticmethod
    def _index(payload):
        return dict((s['scale'], {'unit': s.get('unit'), 'bands': s.get('bands') or []})
                    for s in payload.get('scales') or () if s.get('scale'))

    def _load(self):
        if not self._store or not os.path.isfile(self._store):
            return
        try:
            with open(self._store, 'rb') as handle:
                stored = json.load(handle)
            self._scales = self._index(stored['payload'])
            self._fetched_at = float(stored['fetchedAt'])
        except (IOError, ValueError, KeyError, TypeError):
            _logger.warning('could not read %s', self._store)

    def _save(self, payload):
        try:
            directory = os.path.dirname(self._store)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            with open(self._store, 'wb') as handle:
                json.dump({'fetchedAt': self._fetched_at, 'payload': payload}, handle)
        except (IOError, OSError):
            _logger.exception('could not write %s', self._store)

"""The half of the uploader that puts loadouts on the wire.

A mixin rather than an object of its own, for the reason the battles package
gives: the fingerprints, the batch in flight and the quiet-until stamp are
read and written by both halves, so a second object would be ceremony without
separation. What the split buys is a file that holds one subject.

What is sent is only ever the difference. A full carousel is a quarter of a
megabyte of which almost nothing moves between two garage visits, so the
server is told what it already holds and answers with what it is missing.
"""
from __future__ import absolute_import

import json
import logging
import time

from unicum import build, config, game_link
from unicum.loadouts.reading import crewed, fingerprint, mounted
from unicum.loadouts.store import (_keep_rejected, changed, load_marks_hash,
                                   load_sent, marks_hash, save_marks_hash,
                                   save_sent, save_withdraw)

_logger = logging.getLogger('unicum.loadouts.sending')

# Vehicles per request. The endpoint accepts far more, but a request carrying
# a whole carousel is a quarter of a megabyte on a connection we know nothing
# about, and a failure throws all of it away rather than a fifth of it.
_BATCH = 50


class Sending(object):
    """The wire; see the module docstring."""

    def _send(self, records):
        self._learn(records)
        pending = changed(records, self._sent, self._held)
        # The fleet's marks, read once and compared to what the server took.
        # They travel with this upload whether or not a loadout changed, which
        # is why an upload can be worth making with no loadout at all.
        try:
            self._marks = build.fleet_marks()
            fresh_marks = marks_hash(self._marks) != load_marks_hash()
        except Exception:
            _logger.exception('could not read the fleet marks')
            self._marks, fresh_marks = {}, False
        # A vehicle the player parted with: we hold a fingerprint for it and
        # it is no longer in the carousel.
        owned = set(record['tankId'] for record in records)
        sold = [tank for tank in self._sent if tank not in owned]
        if not pending and not sold and not fresh_marks:
            self._busy = False
            _logger.info('nothing to send: %d vehicles, all of them unchanged', len(records))
            return
        _logger.info('sending %d of %d vehicles, and %d sold', len(pending), len(records), len(sold))
        self._post(pending, sold)

    def _learn(self, records):
        """Fill in what vehicles we only hold a fingerprint for were carrying.

        Without this neither the demount rule nor the crew rule would protect
        a single vehicle a player already owns: a store written by an earlier
        build says what was sent but not what was on it, and a vehicle would
        only be protected once it changes, which is exactly the moment the
        protection was meant to cover.

        Safe because the fingerprint is what decides: if it still matches, the
        vehicle in the carousel IS the one we sent, so what it carries now is
        what it carried then.
        """
        learned = 0
        for record in records:
            entry = self._sent.get(record['tankId'])
            if not entry or (entry.get('d') is not None and entry.get('c') is not None):
                continue
            if entry.get('f') != fingerprint(record):
                continue
            if entry.get('d') is None:
                entry['d'] = mounted(record)
            if entry.get('c') is None:
                entry['c'] = crewed(record)
            learned += 1
        if learned:
            _logger.info('learned what %d vehicle(s) sent by an earlier build were carrying',
                         learned)
            save_sent(self._sent)

    def _post(self, pending, sold, at=0):
        """One batch, then the next. Stops at the first failure."""
        batch = pending[at:at + _BATCH]
        if not batch and (at > 0 or (not sold and not getattr(self, '_marks', None))):
            self._busy = False
            save_sent(self._sent)
            return
        # The whole fleet's marks ride with the FIRST batch, once.
        #
        # Separate from `loadouts` because they describe a different set: a
        # loadout is what is bolted to a tank the player owns, a mark is what
        # they achieved on a tank they may since have sold. Folding the second
        # into the first would put sold tanks through the `sold` rule below and
        # have each sweep add then remove the same rows.
        #
        # Only on the first batch so a carousel split into five uploads does
        # not send the same two hundred entries five times. It resolves the
        # inventory service itself rather than taking the sweep's: this runs
        # once per upload, not once per vehicle, so the lookup is free here
        # and the uploader does not need to hold the sweep's state.
        marks = []
        if at == 0:
            marks = [{'tankId': intCD, 'marks': found[0], 'markPercent': found[1]}
                     for intCD, found in getattr(self, '_marks', {}).items()]
        body = json.dumps({'loadouts': batch, 'sold': sold if at == 0 else [],
                           'marks': marks})

        def answered(response):
            code = getattr(response, 'responseCode', None)
            if code != 200:
                # Stop rather than push on: a quota answer (429) means the
                # rest of the batches would be refused too, and any other
                # failure is as likely to hit them. What was accepted is
                # remembered, so the next sweep carries on where this left.
                self._busy = False
                save_sent(self._sent)
                _logger.warning('loadout upload stopped on HTTP %s after %d vehicle(s)', code, at)
                _keep_rejected(code, batch)
                return
            if at == 0 and marks:
                # Only once the server has taken them, like the loadouts: a
                # refused batch must leave the fleet looking unsent so the next
                # sweep offers it again.
                save_marks_hash(marks_hash(getattr(self, '_marks', {})))
            for record in batch:
                self._sent[record['tankId']] = {'f': fingerprint(record),
                                                'd': mounted(record),
                                                'c': crewed(record)}
            if at == 0:
                for tank in sold:
                    self._sent.pop(tank, None)
            self._post(pending, sold, at + _BATCH)

        self._request('%s/api/game/loadouts' % config.API_BASE.rstrip('/'), answered,
                      method='POST', post_data=body)

    def _read_held(self, then):
        """What the server already holds, so a lost database is refilled."""

        def answered(response):
            payload = None
            if getattr(response, 'responseCode', None) == 200:
                try:
                    payload = json.loads(response.body)
                except (TypeError, ValueError):
                    payload = None
            tanks = payload.get('tanks') if isinstance(payload, dict) else None
            self._held = set(int(key) for key in tanks) if isinstance(tanks, dict) else set()
            then()

        self._request('%s/api/game/loadouts' % config.API_BASE.rstrip('/'), answered)

    def _request(self, url, answered, method='GET', post_data=''):
        """Signed with whatever proves this account, and nothing if neither does.

        The link's secret when the player has one, because it costs the server
        no call to Wargaming. Otherwise the client's own WGNI web token, which
        the game mints without asking the player anything and which unicum.gg
        has Wargaming confirm. Either way the account is proven rather than
        claimed: a nickname in the body would let anyone publish a loadout
        under somebody else's name, and the whole value of this rests on that
        being impossible.
        """
        secret = getattr(self._link, 'secret', None)
        if secret:
            self._fetch(url, answered, {'Authorization': 'Bearer %s' % secret},
                        method, post_data)
            return

        def with_token(response):
            if not (response and response.isValid()):
                _logger.info('no web token; loadouts wait for the next garage')
                self._busy = False
                return
            self._fetch(url, answered, {
                'X-Wargaming-Token': str(response.getToken()),
                'X-Wargaming-Region': config.REGION,
            }, method, post_data)

        try:
            from constants import TOKEN_TYPE
            from gui.shared.utils.requesters import getTokenRequester
            requester = getTokenRequester(TOKEN_TYPE.WGNI)
            if requester.isInProcess():
                self._busy = False
                return
            requester.request(timeout=10.0)(with_token)
        except Exception:
            _logger.exception('could not ask for a web token')
            self._busy = False

    def _fetch(self, url, answered, headers, method, post_data):
        headers = dict(headers)
        headers['Content-Type'] = 'application/json'
        self._session.fetch(url, answered, headers=headers,
                            timeout=config.API_TIMEOUT, method=method,
                            post_data=post_data)

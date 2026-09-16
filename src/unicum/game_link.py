"""The link between this client and the player's unicum.gg account.

It lets the mod act for the player where that needs their account: today,
writing in their Twitch chat (see twitch_send.py). Nothing is typed.

Linking opens the player's own browser (BigWorld.wg_openWebBrowser) on
unicum.gg's /api/connect/game/<hash>#account_id=...&token=..., where the
fragment carries the game's WGNI web token. The game's built-in browser cannot
be used: it only opens the domains Wargaming's servers list (wargaming.net,
worldoftanks.eu...) and refuses any other with a 418 before a request is made.
On that page unicum.gg starts its Wargaming sign-in and sends the browser
through Wargaming's token sign-in, the one the client uses to open the shop
signed in, on to the OpenID page: signed in already, one confirmation screen
at most. It then links the account and, when Twitch is not linked with the
chat scope yet, goes on to Twitch, where the player's browser is usually
signed in too. A fragment never reaches a server, so the token goes from the
game to Wargaming without passing through unicum.gg.

The mod draws a random secret and sends only its SHA-256 along that chain.
Once the site has linked the hash, the secret is the mod's bearer token; the
mod learns that by polling GET /api/game/me with it. The secret lives in
mods/configs/unicum/account.json, and nowhere else.
"""
import binascii
import hashlib
import json
import logging
import os
import urllib

from unicum import config

_logger = logging.getLogger('unicum.game_link')

STORE = os.path.join('mods', 'configs', 'unicum', 'account.json')

_POLL_SECONDS = 3.0
# How long a linking attempt waits for the player before giving up.
_GIVE_UP_SECONDS = 600.0

TWITCH_READY = 'ready'


def new_secret():
    return binascii.hexlify(os.urandom(32))


def secret_hash(secret):
    return hashlib.sha256(secret).hexdigest()


def connect_url(api_base, region, secret, account_id=None, token=None):
    """The page that links this client; the Wargaming web token rides in the fragment."""
    url = '%s/api/connect/game/%s?region=%s' % (api_base.rstrip('/'), secret_hash(secret), region)
    if account_id and token:
        url += '#' + urllib.urlencode([('account_id', account_id), ('token', token)])
    return url


def bearer(secret):
    return {'Authorization': 'Bearer %s' % secret}


def read_me(response):
    """(name, twitch access) from GET /api/game/me; None when not linked or unreadable."""
    if getattr(response, 'responseCode', None) != 200:
        return None
    try:
        payload = json.loads(response.body)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload.get('name'), payload.get('twitch')


class GameLink(object):

    def __init__(self, session, store=STORE):
        self._session = session
        self._store = store
        self._secret = self._load()
        self._attempt = None

    @property
    def secret(self):
        """The bearer secret of a linked client, or None."""
        return self._secret

    def connect(self, done=None):
        """Open the linking page in the player's browser. done(name, twitch) or done(None, None)."""
        from helpers import isPlayerAccount
        if not isPlayerAccount():
            _logger.warning('linking needs the garage')
            return
        if self._attempt is not None:
            # Clicking again starts over: the player closed the page, or it
            # got stuck.
            self._attempt.cancel()
        from constants import TOKEN_TYPE
        from gui.shared.utils.requesters import getTokenRequester
        requester = getTokenRequester(TOKEN_TYPE.WGNI)
        if requester.isInProcess():
            return

        def received(response):
            if not (response and response.isValid()):
                _logger.warning('Wargaming did not hand out a web token')
                if done:
                    done(None, None)
                return
            secret = new_secret()
            self._attempt = _Attempt(self, secret, done)
            self._attempt.start(connect_url(config.API_BASE, config.REGION, secret,
                                            str(response.getDatabaseID()), str(response.getToken())))

        requester.request(timeout=10.0)(received)

    def _linked(self, secret):
        self._secret = secret
        self._save()

    def _ended(self):
        self._attempt = None

    def _load(self):
        try:
            with open(self._store) as handle:
                secret = json.load(handle).get('secret')
            return str(secret) if isinstance(secret, basestring) and len(secret) == 64 else None
        except (IOError, OSError, ValueError, AttributeError):
            return None

    def _save(self):
        try:
            directory = os.path.dirname(self._store)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            with open(self._store, 'w') as handle:
                json.dump({'secret': self._secret}, handle)
        except (IOError, OSError):
            _logger.exception('could not save the account link')


class _Attempt(object):
    """One linking: from opening the player's browser to the account answering."""

    def __init__(self, link, secret, done):
        self._link = link
        self._session = link._session
        self._secret = secret
        self._done = done
        self._linked = False
        self._left = _GIVE_UP_SECONDS / _POLL_SECONDS
        self._over = False

    def start(self, url):
        import BigWorld
        BigWorld.wg_openWebBrowser(url)
        self._session.repeat(_POLL_SECONDS, self._poll)
        _logger.info('linking: opened in the browser')

    def cancel(self):
        """End this attempt quietly."""
        if not self._over:
            self._over = True
            self._link._ended()

    def _poll(self):
        if self._over:
            return
        self._left -= 1
        if self._left < 0:
            _logger.warning('linking: gave up waiting')
            self._finish(None, None)
            return
        self._session.fetch('%s/api/game/me' % config.API_BASE.rstrip('/'), self._answered,
                            headers=bearer(self._secret), timeout=config.API_TIMEOUT)

    def _answered(self, response):
        if self._over:
            return
        me = read_me(response)
        if me is None:
            return
        name, twitch = me
        if not self._linked:
            self._linked = True
            self._link._linked(self._secret)
            _logger.info('linking: linked to %s', name)
        if twitch == TWITCH_READY:
            self._finish(name, twitch)

    def _finish(self, name, twitch):
        self._over = True
        self._link._ended()
        _logger.info('linking: done (%s, Twitch %s)', name, twitch)
        if self._done:
            self._done(name, twitch)

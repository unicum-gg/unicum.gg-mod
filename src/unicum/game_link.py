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
mod learns that by polling GET /api/game/me with it. The secrets live in
mods/configs/unicum/account.json, one per Wargaming account the game has been
linked on, and nowhere else.
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

ME_PATH = '%s/api/game/me'

# How often a linked game asks the site who it is, so a link revoked elsewhere shows.
_REFRESH_SECONDS = 600.0
# How soon it asks again when the site did not answer.
_RETRY_SECONDS = 30.0
# How often the account logged in is looked at, to follow a switch.
_ACCOUNT_SECONDS = 2.0


def new_secret():
    return binascii.hexlify(os.urandom(32))


def secret_hash(secret):
    return hashlib.sha256(secret).hexdigest()


def connect_url(api_base, region, secret, account_id=None, token=None, twitch=True):
    """The page that links this client; the Wargaming web token rides in the fragment.

    Without `twitch`, the account alone is linked and the page never goes on to Twitch.
    `account` names the game's Wargaming account, which the site checks the
    browser's session against before linking.
    """
    url = '%s/api/connect/game/%s?region=%s' % (api_base.rstrip('/'), secret_hash(secret), region)
    if account_id:
        url += '&account=%s' % account_id
    if not twitch:
        url += '&twitch=0'
    if account_id and token:
        url += '#' + urllib.urlencode([('account_id', account_id), ('token', token)])
    return url


def bearer(secret):
    return {'Authorization': 'Bearer %s' % secret}


def read_me(response):
    """(name, twitch access, twitch login) from GET /api/game/me; None when not linked or unreadable."""
    if getattr(response, 'responseCode', None) != 200:
        return None
    try:
        payload = json.loads(response.body)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    login = payload.get('twitchLogin')
    login = str(login).lower() if isinstance(login, basestring) and login else None
    return payload.get('name'), payload.get('twitch'), login


def current_account_id():
    """The Wargaming account id the client is logged in with, or None (a battle, the login screen)."""
    try:
        import BigWorld
        account_id = getattr(BigWorld.player(), 'databaseID', None)
    except Exception:
        return None
    return str(account_id) if account_id else None


def read_store(raw):
    """(links {account id: secret}, card hidden for [account ids]) from account.json's content.

    An account.json from before links were per account holds one `secret`,
    returned under None for the first account the game logs in with.
    """
    links, hidden = {}, []
    if not isinstance(raw, dict):
        return links, hidden
    for account_id, secret in (raw.get('links') or {}).items():
        if isinstance(secret, basestring) and len(secret) == 64:
            links[str(account_id)] = str(secret)
    legacy = raw.get('secret')
    if isinstance(legacy, basestring) and len(legacy) == 64:
        links[None] = str(legacy)
    hidden = [str(account_id) for account_id in raw.get('cardHidden') or [] if account_id]
    return links, hidden


class GameLink(object):
    """The links of this client, one per Wargaming account it has been logged in with.

    Everything reads the account logged in now: switching accounts in the
    client switches the link, and an account never linked reads as not linked,
    so its messages can never go out as another account's.
    """

    def __init__(self, session, store=STORE, account_id=current_account_id):
        self._session = session
        self._store = store
        self._account_id = account_id
        self._links, self._hidden = self._load()
        self._attempt = None
        # The account last seen logged in, kept through a battle, where the
        # avatar carries no database id.
        self._account = None
        # What the account answered last: its name, Twitch access and channel.
        self.name = None
        self.twitch = None
        self.twitch_login = None
        self._retrying = False
        self._listeners = []

    @property
    def account(self):
        return self._account

    @property
    def secret(self):
        """The bearer secret of the account logged in, or None."""
        return self._links.get(self._account) if self._account else None

    @property
    def card_hidden(self):
        """Whether the player closed the account card for this account."""
        return self._account in self._hidden

    def hide_card(self):
        if self._account and self._account not in self._hidden:
            self._hidden.append(self._account)
            self._save()
            self._changed()

    def on_change(self, callback):
        self._listeners.append(callback)

    def install(self):
        self._follow_account()
        self._session.repeat(_ACCOUNT_SECONDS, self._follow_account)
        self._session.repeat(_REFRESH_SECONDS, self.refresh)

    def _follow_account(self):
        account = self._account_id()
        if not account or account == self._account:
            return
        self._account = account
        if None in self._links:
            # The link saved before links were per account was made on the
            # account the game first logs in with; refresh() drops it if not.
            self._links.setdefault(account, self._links.pop(None))
            self._save()
        self.name = self.twitch = self.twitch_login = None
        _logger.info('account %s, %s', account, 'linked' if self.secret else 'not linked')
        self._changed()
        self.refresh()

    def refresh(self):
        """Ask the account who it is; a link the site no longer knows is forgotten.

        When the site does not answer, it is asked again soon rather than at the
        next refresh: the name and the Twitch channel shown wait on it.
        """
        secret, account = self.secret, self._account
        if not secret:
            return

        def answered(response):
            if account != self._account or secret != self.secret:
                return
            me = read_me(response)
            if me is not None:
                self._set(*me)
            elif getattr(response, 'responseCode', None) == 401:
                _logger.info('the site no longer knows this link, forgetting it')
                self._forget()
            elif not self._retrying:
                _logger.info('the site did not answer who this account is (HTTP %s), asking again soon',
                             getattr(response, 'responseCode', None))
                self._retrying = True
                self._session.callback(_RETRY_SECONDS, self._retry)

        self._session.fetch(ME_PATH % config.API_BASE.rstrip('/'), answered, headers=bearer(secret),
                            timeout=config.API_TIMEOUT)

    def _retry(self):
        self._retrying = False
        self.refresh()

    def unlink(self, done=None):
        """Revoke this account's link on the site and forget it here, whatever the site answers."""
        secret = self.secret
        if not secret:
            if done:
                done()
            return
        self._forget()

        def answered(response):
            _logger.info('unlinked (site answered HTTP %s)', getattr(response, 'responseCode', None))
            if done:
                done()

        self._session.fetch(ME_PATH % config.API_BASE.rstrip('/'), answered, headers=bearer(secret),
                            timeout=config.API_TIMEOUT, method='DELETE', post_data='')

    def _set(self, name, twitch, twitch_login=None):
        if (name, twitch, twitch_login) != (self.name, self.twitch, self.twitch_login):
            self.name, self.twitch, self.twitch_login = name, twitch, twitch_login
            self._changed()

    def _forget(self):
        self._links.pop(self._account, None)
        self.name = self.twitch = self.twitch_login = None
        self._save()
        self._changed()

    def _changed(self):
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                _logger.exception('an account link listener failed')

    def connect(self, done=None, twitch=True):
        """Open the linking page in the player's browser. done(name, twitch) or done(None, None).

        With `twitch`, it goes on to Twitch when the chat scope is missing, and
        ends once the chat can be written to; without, once the account is linked.
        """
        from helpers import isPlayerAccount
        if not isPlayerAccount() or not self._account:
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
        account = self._account

        def received(response):
            if not (response and response.isValid()):
                _logger.warning('Wargaming did not hand out a web token')
                if done:
                    done(None, None)
                return
            secret = new_secret()
            self._attempt = _Attempt(self, secret, done, twitch, account)
            self._attempt.start(connect_url(config.API_BASE, config.REGION, secret, str(response.getDatabaseID()),
                                            str(response.getToken()), twitch))

        requester.request(timeout=10.0)(received)

    def _linked(self, account, secret, name, twitch, twitch_login=None):
        self._links[account] = secret
        if account in self._hidden:
            # Linked again: the card shows who it is linked to until closed again.
            self._hidden.remove(account)
        self._save()
        if account == self._account:
            self.name = self.twitch = self.twitch_login = None
            self._set(name, twitch, twitch_login)

    def _ended(self):
        self._attempt = None

    def _load(self):
        try:
            with open(self._store) as handle:
                return read_store(json.load(handle))
        except (IOError, OSError, ValueError):
            return {}, []

    def _save(self):
        try:
            directory = os.path.dirname(self._store)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            links = dict((account, secret) for account, secret in self._links.items() if account)
            with open(self._store, 'w') as handle:
                json.dump({'links': links, 'cardHidden': self._hidden}, handle)
        except (IOError, OSError):
            _logger.exception('could not save the account links')


class _Attempt(object):
    """One linking: from opening the player's browser to the account answering."""

    def __init__(self, link, secret, done, twitch=True, account=None):
        self._twitch = twitch
        self._account = account
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
        self._session.fetch(ME_PATH % config.API_BASE.rstrip('/'), self._answered,
                            headers=bearer(self._secret), timeout=config.API_TIMEOUT)

    def _answered(self, response):
        if self._over:
            return
        me = read_me(response)
        if me is None:
            return
        name, twitch, twitch_login = me
        if not self._linked:
            self._linked = True
            self._link._linked(self._account, self._secret, name, twitch, twitch_login)
            _logger.info('linking: linked to %s', name)
        elif self._account == self._link.account:
            self._link._set(name, twitch, twitch_login)
        if twitch == TWITCH_READY or not self._twitch:
            self._finish(name, twitch)

    def _finish(self, name, twitch):
        self._over = True
        self._link._ended()
        _logger.info('linking: done (%s, Twitch %s)', name, twitch)
        if self._done:
            self._done(name, twitch)

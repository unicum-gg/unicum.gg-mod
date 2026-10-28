"""Getting the account linked, and keeping it that way.

Opens the browser once, then polls until the site says the hash is claimed,
backing off as it goes. Everything about what is being proved is in `proof`;
this is the part that waits.
"""
from __future__ import absolute_import

import json
import logging
import os
import time

from unicum import config
from unicum.game_link.proof import (ME_PATH, STORE, TWITCH_READY, bearer,
                                    connect_url, current_account_id,
                                    new_secret, read_me, read_privacy,
                                    read_store, secret_hash)

_logger = logging.getLogger('unicum.game_link.link')

_POLL_SECONDS = 3.0
# How long a linking attempt waits for the player before giving up.
_GIVE_UP_SECONDS = 600.0

# How often a linked game asks the site who it is, so a link revoked elsewhere shows.
_REFRESH_SECONDS = 600.0
# How soon it asks again when the site did not answer.
_RETRY_SECONDS = 30.0
# How often the account logged in is looked at, to follow a switch.
_ACCOUNT_SECONDS = 2.0

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
        # Whether this account supports the site, and whether it has taken its
        # loadouts off its public page. Both are the site's answer rather than
        # a local setting: the first is a subscription and the second is a row
        # the site owns, so neither belongs in settings.json.
        self.supporter = False
        self.loadouts_hidden = False
        self._retrying = False
        self._listeners = []

    @property
    def account(self):
        return self._account

    @property
    def secret(self):
        """The bearer secret of the account logged in, or None."""
        if config.PREVIEW_SIGNED_OUT:
            return None
        return self._links.get(self._account) if self._account else None

    @property
    def card_hidden(self):
        """Whether the player closed the account card for this account."""
        if config.PREVIEW_SIGNED_OUT:
            return False
        return self._account in self._hidden

    def hide_card(self):
        if self._account and self._account not in self._hidden:
            self._hidden.append(self._account)
            self._save()
            self._changed()

    def show_card(self):
        """Bring the card back for the account logged in, the settings window's way."""
        if self._account and self._account in self._hidden:
            self._hidden.remove(self._account)
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
        self.supporter = self.loadouts_hidden = False
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
                self._set_privacy(*read_privacy(response))
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

    def _set_privacy(self, supporter, loadouts_hidden):
        if (supporter, loadouts_hidden) != (self.supporter, self.loadouts_hidden):
            self.supporter, self.loadouts_hidden = supporter, loadouts_hidden
            self._changed()

    def hide_loadouts(self, hidden, done=None):
        """Take this player's loadouts off their page, or put them back.

        The site owns the answer, so this asks rather than decides: the local
        flag only moves once the site says it has. A switch that flipped on
        the spot and silently failed would be the worst of both, telling the
        player they are hidden while their page still shows everything.
        """
        secret = self.secret
        if not secret:
            if done:
                done(False)
            return

        def answered(response):
            if getattr(response, 'responseCode', None) != 200:
                _logger.warning('the site would not change the loadout privacy (HTTP %s)',
                                getattr(response, 'responseCode', None))
                if done:
                    done(False)
                return
            self._set_privacy(self.supporter, bool(hidden))
            if done:
                done(True)

        self._session.fetch(ME_PATH % config.API_BASE.rstrip('/'), answered,
                            headers=bearer(secret), timeout=config.API_TIMEOUT,
                            method='PATCH',
                            post_data=json.dumps({'loadoutsHidden': bool(hidden)}))

    def _forget(self):
        self._links.pop(self._account, None)
        self.name = self.twitch = self.twitch_login = None
        self.supporter = self.loadouts_hidden = False
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
        if config.PREVIEW_SIGNED_OUT:
            # A link made now would replace the real one, which the preview keeps.
            _logger.warning('linking is off while previewing signed out')
            return
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
        if self._account == self._link.account:
            self._link._set_privacy(*read_privacy(response))
        if twitch == TWITCH_READY or not self._twitch:
            self._finish(name, twitch)

    def _finish(self, name, twitch):
        self._over = True
        self._link._ended()
        _logger.info('linking: done (%s, Twitch %s)', name, twitch)
        if self._done:
            self._done(name, twitch)

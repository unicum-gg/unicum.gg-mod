"""One click, in the garage, to send battles to a partner site.

The player used to do two things by hand: ask the site for a secret, and write
`destinations.json` with it. Both are gone. This draws the secret, opens the
player's own browser on the site's linking page carrying only its SHA-256,
waits for the site to accept it, and writes the destination down itself.

The same shape as `game_link.py`, deliberately. That flow is the one the player
has already been through once for unicum.gg, and the properties it buys are the
ones that matter here too:

  - the secret is drawn in the client and never travels. The site stores a
    hash, so a site that is breached leaks nothing that can report battles.
  - the player's own browser does the signing in. The game's built-in browser
    only opens the domains Wargaming lists and would refuse this one with a 418
    before a request left.
  - the Wargaming account is named in the URL so the site can refuse a link to
    the wrong account. Left unchecked, every report would be rejected later for
    an account mismatch, which is a silent failure rather than a readable one.

Why the site is named here rather than typed by the player: Battle-Conquest
scores ranked seasons from these reports and is a declared partner of this mod.
A player who has to find and type an address makes a mistake no error message
can explain, and the one thing worth optimising on this path is that nothing is
typed at all.
"""
import logging

from unicum import config
from unicum.game_link import new_secret, secret_hash

_logger = logging.getLogger('unicum.site_link')

# The partner site these reports are scored by.
SITE = 'https://battle-conquest.eu'
LABEL = 'Battle-Conquest'

LINK_PATH = '%s/mod/link?key=%s&account=%s'
ME_PATH = '%s/api/mod/me'

# Matches game_link: the player is in a browser, and three seconds is slow
# enough to be free and quick enough not to be noticed.
_POLL_SECONDS = 3.0

# How long an attempt waits for the player before giving up. A browser left
# open on a sign-in page must not leave a poll running for the session.
_GIVE_UP_SECONDS = 600.0


def read_me(response):
    """(label, modes) from GET /api/mod/me, or None while nothing is linked.

    401 is the ordinary waiting state, not an error: the player has not clicked
    yet. Anything unreadable is treated the same way, because a site answering
    something unexpected is a site we should keep waiting on rather than
    declare linked.
    """
    if getattr(response, 'responseCode', None) != 200:
        return None
    body = getattr(response, 'body', None)
    if not body:
        return None
    try:
        import json

        payload = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    modes = payload.get('modes')
    if not isinstance(modes, (list, tuple)) or not modes:
        # A site that wants nothing would be written down owed nothing, and the
        # capture would keep every battle for no one.
        return None
    label = payload.get('label')
    if not isinstance(label, basestring) or not label.strip():
        label = LABEL
    return label.strip(), list(modes)


class Attempt(object):
    """One linking attempt: a secret drawn, a browser opened, and a poll."""

    def __init__(self, session, destinations, account, site=SITE, on_done=None):
        self._session = session
        self._destinations = destinations
        self._account = account
        self._site = site.rstrip('/')
        self._on_done = on_done
        self._secret = new_secret()
        self._left = int(_GIVE_UP_SECONDS / _POLL_SECONDS)
        self._over = False

    def url(self):
        """Where the player's browser is sent."""
        return LINK_PATH % (self._site, secret_hash(self._secret), self._account)

    def start(self):
        import BigWorld

        BigWorld.wg_openWebBrowser(self.url())
        self._session.repeat(_POLL_SECONDS, self._poll)
        _logger.info('linking to %s: opened in the browser', self._site)

    def _poll(self):
        if self._over:
            return
        self._left -= 1
        if self._left < 0:
            self._finish(None)
            _logger.warning('linking to %s: gave up waiting', self._site)
            return
        self._session.fetch(ME_PATH % self._site, self._answered,
                            headers={'X-Mod-Secret': self._secret},
                            timeout=config.API_TIMEOUT)

    def _answered(self, response):
        if self._over:
            return
        me = read_me(response)
        if me is None:
            return
        label, modes = me
        self._finish(self._destinations.remember(self._site + '/api/mod/battles',
                                                 label, modes, self._secret))

    def _finish(self, destination):
        self._over = True
        if destination is not None:
            _logger.info('linking to %s: done, owed %s',
                         self._site, ', '.join(destination.modes) or 'nothing')
        if self._on_done is not None:
            self._on_done(destination)


class SiteLink(object):
    """The partner link as the settings window sees it: linked, or linkable."""

    def __init__(self, session, destinations, link, site=SITE):
        self._session = session
        self._destinations = destinations
        self._link = link
        self._site = site.rstrip('/')
        self._attempt = None
        self._listeners = []

    def on_change(self, callback):
        self._listeners.append(callback)

    @property
    def url(self):
        return self._site + '/api/mod/battles'

    @property
    def linked(self):
        """Whether this site already has a usable destination here."""
        destination = self._destinations.find(self.url)
        return destination is not None and bool(destination.secret) and destination.enabled

    @property
    def running(self):
        return self._attempt is not None

    def start(self):
        """Begin a linking attempt, unless one is already waiting.

        Refuses without an account rather than guessing one: the site checks it
        against the player's own, and a link made for the wrong account would
        have every report refused afterwards.
        """
        if self._attempt is not None:
            return False
        account = getattr(self._link, 'account', None)
        if not account:
            _logger.warning('linking to %s: no Wargaming account logged in yet; '
                            'open the garage and try again', self._site)
            return False
        self._attempt = Attempt(self._session, self._destinations, account,
                                site=self._site, on_done=self._done)
        self._attempt.start()
        self._changed()
        return True

    def _done(self, destination):
        self._attempt = None
        self._changed()

    def _changed(self):
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                _logger.exception('a link listener failed')


def install(session, destinations, link, site=SITE):
    sites = SiteLink(session, destinations, link, site=site)
    _logger.info('%s is %s', site, 'linked' if sites.linked else 'not linked yet')
    return sites

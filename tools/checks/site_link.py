"""Checks for linking a partner site in one click.

What is checked is what the player never does: typing an address, copying a
secret, writing a file. And the two properties that make it safe to send them
through their own browser -- the secret stays in the client, and the Wargaming
account is named so the site can refuse a link to the wrong one.
"""
import json
import os
import tempfile

from checks.common import check


class _Response(object):
    def __init__(self, code, payload=None):
        self.responseCode = code
        self.body = None if payload is None else json.dumps(payload)


class _Session(object):
    """Enough session to start an attempt and answer its poll."""

    def __init__(self):
        self.repeats = []
        self.sent = []

    def repeat(self, interval, func):
        self.repeats.append(func)

    def fetch(self, url, answer, headers=None, timeout=None, **kwargs):
        self.sent.append({'url': url, 'headers': headers or {}, 'answer': answer})

    def on_close(self, func):
        pass


class _Link(object):
    def __init__(self, account='500123456'):
        self.account = account


def _destinations(known=('random', 'ranked', 'other')):
    from unicum.destinations import Destinations

    return Destinations(known, store=os.path.join(tempfile.mkdtemp(), 'destinations.json'))


def _opened(monkey):
    """Catch what the mod asks the client to open, instead of opening it."""
    import BigWorld

    standing = getattr(BigWorld, 'wg_openWebBrowser', None)
    BigWorld.wg_openWebBrowser = monkey
    return standing


def check_site_link_url():
    from unicum.game_link import secret_hash
    from unicum.site_link import Attempt

    places = _destinations()
    attempt = Attempt(_Session(), places, '500123456', site='https://example.test')
    url = attempt.url()

    # The secret never travels: only its SHA-256, which the site stores. A site
    # that is breached therefore leaks nothing that can report a battle.
    check('the secret itself is not in the URL', attempt._secret not in url)
    check('its hash is', secret_hash(attempt._secret) in url)
    # Named so the site can refuse a link to the wrong account. Unchecked, every
    # report would be rejected later for a mismatch -- a silent failure.
    check('the Wargaming account is named', 'account=500123456' in url)
    check('and it points at the site asked for', url.startswith('https://example.test/mod/link?'))


def check_site_link_waiting():
    from unicum.site_link import read_me

    # 401 is the ordinary waiting state: the player has not clicked yet.
    check('a 401 is not a link', read_me(_Response(401)) is None)
    check('a 200 with no body is not a link', read_me(_Response(200)) is None)
    check('a 200 that is not a dict is not a link', read_me(_Response(200, [1, 2])) is None)
    # A site that wants nothing would be written down owed nothing, and the
    # capture would then keep every battle for no one.
    check('a site asking for no mode is not a link',
          read_me(_Response(200, {'modes': []})) is None)

    answer = read_me(_Response(200, {'label': 'Battle-Conquest', 'modes': ['ranked']}))
    check('a site that answers with modes is a link', answer == ('Battle-Conquest', ['ranked']))
    # The label is a courtesy; a site that forgets it is still linkable.
    check('a missing label falls back to the site name',
          read_me(_Response(200, {'modes': ['ranked']}))[0] == 'Battle-Conquest')


def check_site_link_writes_the_destination():
    from unicum.site_link import SiteLink

    places = _destinations()
    session = _Session()
    sites = SiteLink(session, places, _Link(), site='https://example.test')

    check('nothing is linked before the player clicks', not sites.linked)

    standing = _opened(lambda url: None)
    try:
        check('a click starts an attempt', sites.start())
        check('and a second click does not stack another', not sites.start())
    finally:
        _opened(standing)

    check('nothing is asked before the first poll', session.sent == [])
    session.repeats[0]()
    request = session.sent[0]
    check('the poll asks the site who we are', request['url'] == 'https://example.test/api/mod/me')
    check('with the secret, not its hash', request['headers'].get('X-Mod-Secret'))

    request['answer'](_Response(200, {'label': 'Battle-Conquest', 'modes': ['ranked', 'nonsense']}))

    check('the destination is written down', sites.linked)
    destination = places.find('https://example.test/api/mod/battles')
    check('it points at the battles endpoint', destination is not None)
    # Enabled, unlike one that merely appeared in the file: the player went
    # through the site's own sign-in, which is the act of consent.
    check('it is enabled, because the player just consented', destination.enabled)
    check('it carries the secret the mod drew', destination.secret == request['headers']['X-Mod-Secret'])
    # The site declares what it scores; a mode this mod cannot produce is
    # dropped rather than stored as a promise nothing will keep.
    check('it is owed what the site asked for', destination.modes == ['ranked'])
    check('and the attempt is over', not sites.running)

    # Written to disk, not just held in memory: the next client start has to
    # find it, or the player links again every session.
    from unicum.destinations import Destinations

    reopened = Destinations(('random', 'ranked', 'other'), store=places._store)
    survivor = reopened.find('https://example.test/api/mod/battles')
    check('and it survives a client restart', survivor is not None)
    check('with its secret and its modes',
          survivor.secret == destination.secret and survivor.modes == ['ranked'])


def check_site_link_needs_an_account():
    from unicum.site_link import SiteLink

    places = _destinations()
    session = _Session()
    sites = SiteLink(session, places, _Link(account=None), site='https://example.test')

    standing = _opened(lambda url: None)
    try:
        # Refused rather than guessed: the site checks the account against the
        # player's own, and a link made for the wrong one has every report
        # refused afterwards.
        check('no account logged in means no linking', not sites.start())
    finally:
        _opened(standing)
    check('and nothing was asked of the site', session.sent == [])


def check_site_link_gives_up():
    from unicum.site_link import SiteLink

    session = _Session()
    sites = SiteLink(session, _destinations(), _Link(), site='https://example.test')

    standing = _opened(lambda url: None)
    try:
        sites.start()
    finally:
        _opened(standing)

    # A browser left open on a sign-in page must not leave a poll running for
    # the rest of the session.
    for _ in range(205):
        session.repeats[0]()
    check('an attempt that nobody confirms ends', not sites.running)
    check('and it stops asking', len(session.sent) < 205)

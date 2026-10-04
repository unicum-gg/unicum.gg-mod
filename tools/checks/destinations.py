"""Checks for where battles are sent: what is refused, and what is never sent unasked."""

import json
import logging
import os
import tempfile

from checks.common import check

MODES = ('random', 'ranked', 'onslaught', 'stronghold', 'frontline', 'training', 'other')

SECRET = 'a' * 64


def _file(entries):
    path = os.path.join(tempfile.mkdtemp(), 'destinations.json')
    with open(path, 'wb') as handle:
        json.dump({'schema': 1, 'destinations': entries}, handle)
    return path


def check_destination_urls():
    from unicum.destinations import valid_url

    check('an https URL is accepted', valid_url('https://battle-conquest.com/api/mod/battles'))
    # Refused rather than upgraded or sent anyway: a report names a Wargaming
    # account, and in the clear it is readable by anyone on the way.
    check('plain http is refused', not valid_url('http://battle-conquest.com/api/mod/battles'))
    check('a bare host is refused', not valid_url('battle-conquest.com'))
    check('an empty URL is refused', not valid_url(''))
    check('the scheme alone is refused', not valid_url('https://'))
    # A space means it was typed into the wrong field.
    check('a URL with a space in it is refused', not valid_url('https://foo bar/x'))
    check('something that is not a string is refused', not valid_url(None))


def check_destination_modes():
    from unicum.destinations import clean_modes

    check('a mode the mod knows is kept', clean_modes(['ranked'], MODES) == ['ranked'])
    # An unknown mode is dropped rather than carried: the capture never produces
    # it, so a destination asking for it would wait forever and never be told.
    check('a mode the mod does not know is dropped', clean_modes(['rankedd'], MODES) == [])
    check('the same mode twice is kept once', clean_modes(['ranked', 'ranked'], MODES) == ['ranked'])
    check('nothing asked for is nothing kept', clean_modes(None, MODES) == [])


def check_destination_reading():
    from unicum.destinations import Destinations, read

    good = {'url': 'https://battle-conquest.com/api/mod/battles', 'label': 'Battle-Conquest',
            'enabled': True, 'modes': ['ranked'], 'secret': SECRET}

    places = read({'schema': 1, 'destinations': [good]}, MODES)
    check('a well-formed destination is read', len(places) == 1)
    check('and it is asked for the mode it wants', places[0].wants('ranked'))
    check('but never for a mode it did not ask for', not places[0].wants('random'))

    # One mistyped URL must not take down a destination that is correct.
    mixed = read({'schema': 1, 'destinations': [{'url': 'nope'}, good]}, MODES)
    check('a bad entry is skipped, not fatal', len(mixed) == 1)

    # Two entries for one URL would send the battle twice and leave it ambiguous
    # which secret proves the account there.
    twice = read({'schema': 1, 'destinations': [good, dict(good)]}, MODES)
    check('a URL listed twice is read once', len(twice) == 1)

    check('a payload of another schema is ignored',
          read({'schema': 99, 'destinations': [good]}, MODES) == [])
    check('something that is not a payload is ignored', read(None, MODES) == [])

    # Consent has to be an act. A destination a site's installer wrote in
    # arrives switched off, and a player who never opened the file agreed to
    # nothing.
    off = read({'schema': 1, 'destinations': [dict(good, enabled=False)]}, MODES)
    check('a destination is off unless it says otherwise', not off[0].wants('ranked'))
    default = read({'schema': 1, 'destinations': [{'url': good['url'], 'modes': ['ranked']}]}, MODES)
    check('an entry that says nothing about being enabled is off',
          not default[0].wants('ranked'))

    # Without a secret there is nothing to prove the account with, so there is
    # nothing to send: a report signed by nobody could name anybody.
    unsigned = read({'schema': 1, 'destinations': [dict(good, secret=None)]}, MODES)
    check('a destination with no secret is not sent to', not unsigned[0].wants('ranked'))
    short = read({'schema': 1, 'destinations': [dict(good, secret='abc')]}, MODES)
    check('a secret of the wrong length is no secret', not short[0].wants('ranked'))

    store = _file([good, dict(good, url='https://example.org/in', modes=['random'], enabled=False)])
    destinations = Destinations(MODES, store=store)
    check('the file is read from disk', len(destinations.all()) == 2)
    check('only the enabled destination is owed a ranked battle',
          [d.url for d in destinations.wanting('ranked')] == [good['url']])
    check('a disabled destination is owed nothing', destinations.wanting('random') == [])
    check('the modes waited for are those of the enabled destinations',
          destinations.modes() == ['ranked'])


def check_destination_secrets():
    from unicum.destinations import Destinations
    from unicum.game_link import secret_hash

    url = 'https://battle-conquest.com/api/mod/battles'
    store = _file([{'url': url, 'modes': ['ranked'], 'enabled': True}])
    destinations = Destinations(MODES, store=store)
    check('a destination starts without a secret', destinations.all()[0].secret is None)

    prepared = destinations.prepare(url)
    check('linking draws one', prepared.secret is not None and len(prepared.secret) == 64)
    # Only the hash ever leaves the machine, exactly as the unicum.gg link does.
    check('what travels is the hash, not the secret',
          prepared.hash() == secret_hash(prepared.secret) and prepared.hash() != prepared.secret)
    check('the secret is kept, so the link survives a restart',
          Destinations(MODES, store=store).all()[0].secret == prepared.secret)
    check('preparing again keeps the same secret', destinations.prepare(url).secret == prepared.secret)
    check('a URL that is not listed prepares nothing',
          destinations.prepare('https://elsewhere.test/in') is None)

    # A secret is a proof of identity: one shared between two sites would let
    # either report battles to the other as this player.
    second = 'https://example.org/in'
    both = Destinations(MODES, store=_file([{'url': url, 'modes': ['ranked']},
                                           {'url': second, 'modes': ['ranked']}]))
    check('two destinations never share a secret',
          both.prepare(url).secret != both.prepare(second).secret)


def check_destination_capture():
    from unicum.battle_reports import BattleReports
    from unicum.destinations import Destinations
    from unicum.report_queue import Queue

    class _Settings(object):
        def __init__(self, on):
            self._on = on

        def sends_battle_reports(self):
            return self._on

    url = 'https://battle-conquest.com/api/mod/battles'
    places = Destinations(MODES, store=_file([
        {'url': url, 'modes': ['ranked'], 'enabled': True, 'secret': SECRET}]))

    def _reports(sends):
        return BattleReports(None, _Settings(sends),
                             queue=Queue(store=os.path.join(tempfile.mkdtemp(), 'q.json')),
                             destinations=places)

    check('with unicum.gg on, every mode is wanted', _reports(True).wanted('random'))
    # The point of per-destination modes: a site scoring ranked is not sent the
    # player's random battles, and with unicum.gg off nothing else is either.
    check('with unicum.gg off, the mode a destination asked for is still wanted',
          _reports(False).wanted('ranked'))
    check('with unicum.gg off, a mode nobody asked for is not wanted',
          not _reports(False).wanted('random'))

    none = BattleReports(None, _Settings(False),
                         queue=Queue(store=os.path.join(tempfile.mkdtemp(), 'q.json')))
    check('with nothing to send to, no battle is kept', not none.wanted('ranked'))


class _Capture(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())

    def said(self, fragment):
        return any(fragment in line for line in self.lines)


def _loading(store, known=MODES):
    """What destinations.install() says while it loads this store."""
    from unicum import destinations as module

    captured = _Capture()
    logger = logging.getLogger('unicum.destinations')
    logger.addHandler(captured)
    try:
        module.install(None, known, store=store)
    finally:
        logger.removeHandler(captured)
    return captured


def check_destination_silence():
    """Every way the loading comes back empty says which way it was.

    Written because it did not. A player whose battles reached no site had
    nothing in the log to tell a file that was never written from a file
    written somewhere the mod does not look -- and the two are fixed
    differently. The path is relative to wherever the client was started, so
    without it in the line those two cases read identically.
    """
    good = {'url': 'https://battle-conquest.com/api/mod/battles', 'label': 'Battle-Conquest',
            'enabled': True, 'modes': ['ranked'], 'secret': SECRET}

    missing = os.path.join(tempfile.mkdtemp(), 'nowhere', 'destinations.json')
    said = _loading(missing)
    check('a destinations file that is not there is said to be missing',
          said.said('no destinations file'))
    # The path, because "it is right there" and "this is not where it looks"
    # are the same sentence without it.
    check('and the path it looked at is named', said.said(missing))

    wrong = os.path.join(tempfile.mkdtemp(), 'destinations.json')
    with open(wrong, 'wb') as handle:
        json.dump({'schema': 99, 'destinations': [good]}, handle)
    said = _loading(wrong)
    check('a file of another schema says so', said.said('schema'))
    check('and says which one this mod reads', said.said('reads 1'))

    broken = os.path.join(tempfile.mkdtemp(), 'destinations.json')
    with open(broken, 'wb') as handle:
        handle.write('{not json')
    check('a file that does not parse says so', _loading(broken).said('not readable JSON'))

    # The loaded case is named one destination at a time: "1 destination
    # enabled" and "the one I meant is enabled" are not the same statement.
    said = _loading(_file([good]))
    check('an enabled destination is named', said.said('Battle-Conquest'))
    check('with its URL', said.said(good['url']))
    check('and the modes it is owed', said.said('ranked'))

    off = _loading(_file([dict(good, enabled=False)]))
    check('a destination present but switched off is still reported',
          off.said('present but none enabled'))

    short = _loading(_file([dict(good, secret='abc')]))
    check('a secret of the wrong length is reported rather than dropped in silence',
          short.said('rather than 64'))

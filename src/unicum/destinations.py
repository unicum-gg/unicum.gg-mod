"""Where a captured battle is sent, and which of those the player has agreed to.

unicum.gg is the destination this mod was written for, and it stays the default
one. But the mod is the only thing that can see a ranked battle at all, and it
is not the only site that scores one: a tournament site computing a ladder from
ranked results has the same problem and no other way out of it either. Sending
to one site and having the others read it back from that site's API is how the
last attempt died -- the API those sites depended on started charging, and their
ladders stopped the same week. So the player can name further destinations, and
each one receives its own copy.

Why a file of its own, not settings.json
---------------------------------------
Because a destination carries a secret. `settings.json` is mirrored into
modsSettingsApi, which means another mod's UI reads it and writes it back; a
credential has no business there. This follows `account.json` instead, which
holds the unicum.gg link secrets for the same reason.

Why each destination gets its OWN secret
----------------------------------------
A secret is a proof of identity, not a password. One shared between two sites
would let either of them report battles to the other as this player -- and the
whole worth of a reported battle is that nobody can invent one under somebody
else's name. So a secret is drawn per destination, and only its SHA-256 ever
leaves the machine, exactly as the unicum.gg link does.

Why a destination says which modes it wants
-------------------------------------------
Nothing is gained by sending a ranked-tournament site every random battle the
player plays, and a copy of somebody's play history sitting where it serves no
purpose is a cost with no upside. A destination declares what it scores and is
sent that alone.

Why nothing is enabled by the file appearing
--------------------------------------------
A destination arrives switched off, even when a site's own installer wrote it
in. Consent has to be an act; a player who never looked at this file has not
agreed to anything, and reading a file is not being asked.
"""
import errno
import json
import logging
import os

from unicum.game_link import new_secret, secret_hash

_logger = logging.getLogger('unicum.destinations')

# Beside account.json, for the same reason: it holds secrets.
STORE = os.path.join('mods', 'configs', 'unicum', 'destinations.json')

SCHEMA = 1

# Reports identify a Wargaming account. In the clear they are readable by
# anyone on the way, so a destination that is not https is refused rather than
# downgraded -- silently sending them anyway would be the worst of the three.
_REQUIRED_SCHEME = 'https://'

# A label is shown in a log line and nowhere else yet; long enough to tell two
# sites apart, short enough not to fill the log.
_MAX_LABEL = 40


def valid_url(url):
    """Whether a destination's URL is one we will post to."""
    if not isinstance(url, basestring):
        return False
    url = url.strip()
    if not url.startswith(_REQUIRED_SCHEME):
        return False
    # Something has to follow the scheme, and a space in a URL means it was
    # hand-typed into the wrong field.
    rest = url[len(_REQUIRED_SCHEME):]
    return bool(rest) and ' ' not in rest


def clean_modes(raw, known):
    """The modes a destination asked for, keeping only those this mod knows.

    An unknown mode is dropped rather than passed on: it would be a mode the
    capture never produces, so a destination asking for it would wait forever
    and never be told why.
    """
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for mode in raw:
        if mode in known and mode not in out:
            out.append(mode)
    return out


class Destination(object):
    """One place battles are sent, and what it is allowed to receive."""

    def __init__(self, url, label='', enabled=False, modes=(), secret=None):
        self.url = url.strip() if isinstance(url, basestring) else ''
        self.label = (label or self.url)[:_MAX_LABEL]
        self.enabled = bool(enabled)
        self.modes = list(modes)
        self.secret = secret

    def wants(self, mode):
        """Whether an enabled destination is owed a battle of this mode."""
        return self.enabled and bool(self.secret) and mode in self.modes

    def hash(self):
        """What the player carries to the site: never the secret itself."""
        return secret_hash(self.secret) if self.secret else None

    def as_dict(self):
        return {'url': self.url, 'label': self.label, 'enabled': self.enabled,
                'modes': list(self.modes), 'secret': self.secret}

    def __repr__(self):
        return '<Destination %s %s>' % (self.label, 'on' if self.enabled else 'off')


def read(payload, known_modes):
    """The destinations a stored payload describes, the unusable ones dropped.

    A bad entry is skipped and said so in the log, rather than taking the whole
    file down with it: one mistyped URL must not stop a destination that is
    correct from being sent to.
    """
    if not isinstance(payload, dict):
        _logger.warning('the destinations file holds %s rather than an object; none is used',
                        type(payload).__name__)
        return []
    if payload.get('schema') != SCHEMA:
        # Said rather than assumed: a file this cannot read is indistinguishable
        # from a file that was never written, and the two are fixed differently.
        _logger.warning('the destinations file declares schema %r, and this mod reads %d; '
                        'none is used. Link the site again to have it rewritten',
                        payload.get('schema'), SCHEMA)
        return []
    entries = payload.get('destinations')
    if not isinstance(entries, list):
        _logger.warning('the destinations file has no list of destinations; none is used')
        return []
    out = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = entry.get('url')
        if not valid_url(url):
            _logger.warning('ignoring a destination that is not an https URL: %r', url)
            continue
        url = url.strip()
        # Two entries for one URL would send the battle twice and, worse, leave
        # it ambiguous which secret proves the account there.
        if url in seen:
            _logger.warning('ignoring a second entry for %s', url)
            continue
        seen.add(url)
        secret = entry.get('secret')
        if not (isinstance(secret, basestring) and len(secret) == 64):
            # Kept, but it will never be sent to: the entry stays visible in the
            # settings window so the player can see what is wrong, rather than
            # vanishing from a file they can see with their own eyes.
            if secret is not None:
                _logger.warning('%s has a secret of %d characters rather than 64; nothing is sent '
                                'to it until the site is linked again', url,
                                len(secret) if isinstance(secret, basestring) else 0)
            secret = None
        out.append(Destination(url=url,
                               label=entry.get('label') or '',
                               enabled=entry.get('enabled'),
                               modes=clean_modes(entry.get('modes'), known_modes),
                               secret=secret))
    return out


class Destinations(object):
    """The player's own destinations, read from disk and written back."""

    def __init__(self, known_modes, store=STORE):
        self._store = store
        self._known = tuple(known_modes)
        self._destinations = self._read()

    def _read(self):
        """The stored destinations, and a line saying so either way.

        Every way this can come back empty used to be silent, which is the one
        thing it must not be: a player whose battles reach no site has no way of
        telling a file that was never written from a file that was written
        somewhere this cannot see. The path is in the line because it is
        relative to wherever the client was started, so "it is right there" and
        "this is not where it looks" are the same sentence without it.
        """
        try:
            with open(self._store, 'rb') as handle:
                payload = json.load(handle)
        except (IOError, OSError) as problem:
            if getattr(problem, 'errno', None) == errno.ENOENT:
                _logger.info('no destinations file at %s, so no extra site is sent to. '
                             'It is written by linking a site from the garage', self._store)
            else:
                _logger.warning('could not open %s (%s); no extra destination is used',
                                self._store, problem)
            return []
        except ValueError:
            _logger.warning('%s is not readable JSON; no extra destination is used. The file is '
                            'left as it is rather than overwritten, so a hand edit can be undone',
                            self._store)
            return []
        return read(payload, self._known)

    def all(self):
        return list(self._destinations)

    def wanting(self, mode):
        """The destinations owed a battle of this mode."""
        return [destination for destination in self._destinations if destination.wants(mode)]

    def modes(self):
        """Every mode at least one enabled destination asked for.

        What the capture consults to know whether a battle is worth keeping at
        all: a mode nothing is waiting for is a report nobody will ever read.
        """
        wanted = []
        for destination in self._destinations:
            if not destination.enabled:
                continue
            for mode in destination.modes:
                if mode not in wanted:
                    wanted.append(mode)
        return wanted

    def find(self, url):
        """The destination at this URL, or None."""
        for destination in self._destinations:
            if destination.url == url.strip():
                return destination
        return None

    def remember(self, url, label, modes, secret, enabled=True):
        """Write down a destination the player has just linked, and return it.

        Enabled, unlike one that merely appeared in the file: the player went
        through the site's own sign-in to get here, which is the act of consent
        the rest of this module insists on. Nothing is switched on behind their
        back -- they switched it on.

        The secret is the mod's, drawn here and never received: only its
        SHA-256 was sent to the site. Replacing an existing entry rather than
        adding one keeps a second linking from leaving a credential nobody will
        ever present again.
        """
        url = url.strip()
        wanted = clean_modes(modes, self._known)
        existing = self.find(url)
        if existing is not None:
            existing.label = (label or url)[:_MAX_LABEL]
            existing.modes = wanted
            existing.secret = secret
            existing.enabled = bool(enabled)
            self.save()
            return existing
        destination = Destination(url=url, label=label, enabled=enabled,
                                  modes=wanted, secret=secret)
        self._destinations.append(destination)
        self.save()
        return destination

    def prepare(self, url):
        """Give a destination a secret if it has none, and return it.

        Called when the player is about to link: the secret is drawn here and
        its hash is what travels, so the site never learns the secret and we
        never have to trust it with one.
        """
        for destination in self._destinations:
            if destination.url != url:
                continue
            if not destination.secret:
                destination.secret = new_secret()
                self.save()
            return destination
        return None

    def save(self):
        try:
            directory = os.path.dirname(self._store)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            with open(self._store, 'wb') as handle:
                json.dump({'schema': SCHEMA,
                           'destinations': [d.as_dict() for d in self._destinations]}, handle)
        except (IOError, OSError):
            _logger.debug('could not write the destinations down', exc_info=True)


def install(session, known_modes, store=None):
    # `store` is here so a check can watch what this says about a file it wrote
    # itself. Reassigning the module's STORE would not do: it is a default
    # argument, bound once when the class is defined.
    destinations = (Destinations(known_modes) if store is None
                    else Destinations(known_modes, store=store))
    found = destinations.all()
    enabled = [d for d in found if d.enabled]
    if enabled:
        # Each one by name, because "1 destination enabled" and "the one I
        # meant is enabled" are not the same statement.
        for place in enabled:
            _logger.info('sending battles to %s (%s), for %s', place.label or 'an unnamed site',
                         place.url, ', '.join(place.modes) or 'nothing')
        _logger.info('%d extra destination(s) enabled, for %s',
                     len(enabled), ', '.join(destinations.modes()) or 'nothing')
    elif found:
        # Not a failure, and worth a line: a player who added a site and sees
        # nothing arrive there has no other way of learning that it is sitting
        # switched off.
        _logger.info('%d destination(s) present but none enabled', len(found))
    # The empty case is not said here. `_read()` has already said which of the
    # several ways it got there happened, which is the part worth knowing.
    return destinations

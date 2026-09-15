"""What the player chose to see: one rating, and where it and the flags show.

mods/configs/unicum/settings.json is the one source of truth. It is written
with the defaults on first start, can be edited by hand while the client runs
(it is checked every second), and is all the mod needs: no other mod is
required. When izeberg's modsSettingsApi is installed, settings_window.py
also shows these settings in its window, and writes back here.

    {"enabled": true, "metric": "wnx", "window": "recent", "maxFlags": 3, "tankButton": true,
     "contacts": {"flags": true, "rating": false},
     "battle": {"flags": true, "rating": true, "average": true}, ...}

One rating for the whole mod, so the same number means the same thing on
every screen. Each surface only switches its flags, its rating and, in the
skirmish room and the battle, the average on and off. tankButton is the
unicum.gg button in the hangar's vehicle menu.

Every change reaches the surfaces through on_change(), and each surface
redraws what it has on screen, so nothing needs a restart.
"""
import json
import logging
import os

_logger = logging.getLogger('unicum.settings')

STORE = os.path.join('mods', 'configs', 'unicum', 'settings.json')

METRICS = ('wn7', 'wn8', 'wnx')
WINDOWS = ('recent', 'total')
MAX_FLAGS = 3

SURFACES = ('contacts', 'profile', 'skirmishRoom', 'battle', 'stronghold')

# Surfaces with a team or detachment to average.
AVERAGED = ('skirmishRoom', 'battle')

# Where a rating shows unless the player says otherwise: contact rows and the
# profile title are names first.
_RATED_BY_DEFAULT = ('skirmishRoom', 'battle', 'stronghold')


def _surface(surface):
    values = {'flags': True, 'rating': surface in _RATED_BY_DEFAULT}
    if surface in AVERAGED:
        values['average'] = True
    return values


DEFAULTS = dict({
    'enabled': True,
    'metric': 'wnx',
    'window': 'recent',
    'maxFlags': MAX_FLAGS,
    'tankButton': True,
}, **dict((surface, _surface(surface)) for surface in SURFACES))

_CHECK_SECONDS = 1.0


def validate(raw):
    """A complete, valid settings dict: defaults for anything missing or wrong."""
    if not isinstance(raw, dict):
        raw = {}
    raw = _migrate(raw)
    values = {
        'enabled': _bool(raw.get('enabled'), DEFAULTS['enabled']),
        'metric': raw.get('metric') if raw.get('metric') in METRICS else DEFAULTS['metric'],
        'window': raw.get('window') if raw.get('window') in WINDOWS else DEFAULTS['window'],
        'maxFlags': DEFAULTS['maxFlags'],
        'tankButton': _bool(raw.get('tankButton'), DEFAULTS['tankButton']),
    }
    max_flags = raw.get('maxFlags')
    if isinstance(max_flags, int) and not isinstance(max_flags, bool):
        values['maxFlags'] = min(max(max_flags, 1), MAX_FLAGS)
    for surface in SURFACES:
        given = raw.get(surface) if isinstance(raw.get(surface), dict) else {}
        values[surface] = dict((key, _bool(given.get(key), default))
                               for key, default in DEFAULTS[surface].items())
    return values


def _migrate(raw):
    """Read settings.json as earlier versions wrote it.

    First one switch per surface with global flags and ratings switches, then
    a rating per surface ("none", "wn8", ...). The one rating kept is the
    first a surface showed.
    """
    migrated = dict(raw)
    if any(isinstance(raw.get(s), bool) for s in SURFACES):
        for surface in SURFACES:
            shown = raw.get(surface) is not False
            rated = shown and raw.get('ratings') is not False and surface in _RATED_BY_DEFAULT
            migrated[surface] = {'flags': shown and raw.get('flags') is not False, 'rating': rated,
                                 'average': rated and raw.get('averages') is not False}
    chosen = [raw[s].get('rating') for s in SURFACES
              if isinstance(raw.get(s), dict) and raw[s].get('rating') in METRICS + ('none',)]
    if chosen:
        rated = [rating for rating in chosen if rating != 'none']
        if 'metric' not in raw and rated:
            migrated['metric'] = rated[0]
        for surface in SURFACES:
            section = dict(migrated[surface]) if isinstance(migrated.get(surface), dict) else {}
            if isinstance(section.get('rating'), basestring):
                section['rating'] = section['rating'] != 'none'
                migrated[surface] = section
    return migrated


def _bool(value, default):
    return value if isinstance(value, bool) else default


class Settings(object):

    def __init__(self, session, store=STORE):
        self._session = session
        self._store = store
        self._listeners = []
        self._values, self._stamp = self._read()
        if self._stamp is None or self._values != self._raw:
            self._write()

    def install(self):
        self._session.repeat(_CHECK_SECONDS, self._check)
        _logger.info('loaded %s', self._values)

    def __getitem__(self, key):
        return self._values[key]

    def values(self):
        return json.loads(json.dumps(self._values))

    def shows_tank_button(self):
        return self._values['enabled'] and self._values['tankButton']

    def shows_flags(self, surface):
        return self._values['enabled'] and self._values[surface]['flags']

    def metric(self, surface):
        """The mod's rating when this surface shows it, or None."""
        if self._values['enabled'] and self._values[surface]['rating']:
            return self._values['metric']
        return None

    def shows_average(self, surface):
        return self.metric(surface) is not None and self._values[surface].get('average', False)

    def shows(self, surface):
        """Whether the mod draws anything on this surface."""
        return self.shows_flags(surface) or self.metric(surface) is not None

    def label(self, surface):
        """The surface's rating as named on screen: "30d WN8", or "WN8" for lifetime."""
        metric = self.metric(surface)
        if metric is None:
            return None
        return '30d ' + metric.upper() if self._values['window'] == 'recent' else metric.upper()

    def rating(self, entry, surface):
        """A player's or clan's rating as chosen for this surface, or None."""
        metric = self.metric(surface)
        if entry is None or metric is None:
            return None
        return entry.rating(metric, self._values['window'])

    def on_change(self, listener):
        """Call listener() after every change. Listeners live as long as the session."""
        self._listeners.append(listener)

    def update(self, changes):
        """Apply and save changes; listeners run only when something changed.

        A surface's changes are merged into it: {'battle': {'rating': False}}
        leaves its flags as they were.
        """
        merged = self.values()
        for key, value in changes.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        values = validate(merged)
        if values == self._values:
            return
        self._values = values
        self._write()
        self._notify()

    def _check(self):
        """Pick up a hand edit of the file."""
        stamp = _mtime(self._store)
        if stamp is None or stamp == self._stamp:
            return
        values, self._stamp = self._read()
        if values != self._values:
            self._values = values
            _logger.info('settings.json changed: %s', values)
            self._notify()

    def _notify(self):
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                _logger.exception('a surface failed to apply the new settings')

    def _read(self):
        """The validated settings and the file's stamp; keeps what was on disk in _raw."""
        self._raw = None
        stamp = _mtime(self._store)
        if stamp is None:
            return validate({}), None
        try:
            with open(self._store, 'rb') as handle:
                self._raw = json.load(handle)
        except (IOError, ValueError):
            _logger.exception('could not read %s, using the defaults', self._store)
            return validate({}), stamp
        return validate(self._raw), stamp

    def _write(self):
        try:
            directory = os.path.dirname(self._store)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            with open(self._store, 'wb') as handle:
                json.dump(self._values, handle, indent=2, sort_keys=True)
            self._stamp = _mtime(self._store)
            self._raw = self.values()
        except (IOError, OSError):
            _logger.exception('could not write %s', self._store)


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None

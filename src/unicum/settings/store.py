"""The settings as the mod reads them, and the file they live in.

Reads the file when it changes and tells whoever asked. The mtime check is
how a change made outside the client -- a hand edit, or another of this mod's
own windows -- reaches the surfaces without a restart.
"""
from __future__ import absolute_import

import json
import logging
import os

from unicum.settings.defaults import DEFAULTS, STORE, WINDOWS
from unicum.settings.validating import (_merge, panel_size,
                                        twitch_channel, validate)

_logger = logging.getLogger('unicum.settings.store')

_CHECK_SECONDS = 1.0

class Settings(object):

    def __init__(self, session, store=STORE):
        self._session = session
        self._store = store
        self._listeners = []
        self._values, self._stamp = self._read()
        # Written when missing, or to normalise what was read; never over a
        # file that did not parse, which holds the player's edits.
        if self._stamp is None or (self._raw is not None and self._values != self._raw):
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

    def shows_context_menu(self, kind):
        """Whether the right-click entries are drawn on 'players' or on 'vehicles' menus."""
        return self._values['enabled'] and self._values['contextMenu'].get(kind, True)

    def sends_loadouts(self):
        """Whether this client sends how the player has set their vehicles up."""
        return self._values['enabled'] and self._values['sendLoadouts']

    def sends_battles(self):
        """Whether this client sends the battles it played."""
        return self._values['enabled'] and self._values['sendBattles']

    def sends_replays(self):
        """Whether this client also sends the replay file of those battles.

        Gated on `sendBattles` as well as on its own box: the file is attached
        to a battle the server already has, so sending one without the other
        would be offering a file for a battle nobody reported.
        """
        return (self._values['enabled'] and self._values['sendBattles']
                and self._values['sendReplays'])

    def measures_performance(self):
        """Whether the mod is timing itself. Not gated on `enabled`: a mod
        being turned off is exactly when somebody wants to compare."""
        return self._values['measurePerformance']

    def alt_only(self, surface):
        """Whether a surface waits for Alt: 'markers' above tanks, the 'panel' of players,
        the 'tab' screen or the 'loading' screen, team averages included, the battle
        'results', or the 'skirmishRoom'. A surface that never waits says so."""
        return self._values['altOnly'].get(surface, False)

    def minimap_names(self):
        """What the minimap writes beside a vehicle: one of MINIMAP_NAME_CHOICES."""
        return self._values['minimapNames']

    def shows_auto_reload(self):
        """Whether reloads are announced at all."""
        return self._values['enabled'] and self._values['autoReload'] != 'off'

    def announces_reload(self, magazine):
        """Whether this reload is announced: `magazine` for a clip or autoloader.

        A gun that fires one shell at a time reloads after every shot, which
        is a great deal of announcing; an autoloader only when its magazine
        runs out. So the two can be chosen apart.
        """
        if not self.shows_auto_reload():
            return False
        return self._values['autoReload'] == 'all' or bool(magazine)

    def twitch_channel(self, linked=''):
        """The Twitch channel to follow, or '' when there is none or the mod is off.

        The one typed in the settings wins; without one, `linked`, the channel
        the player linked to their account on unicum.gg.
        """
        if not self._values['enabled']:
            return ''
        return self._values['twitch']['channel'] or twitch_channel(linked)

    def shows_twitch_in_battle(self):
        """Whether the battle chat carries the Twitch messages."""
        return self._values['enabled'] and self._values['twitch']['battle'] in ('chat', 'both')

    def shows_twitch_window_in_battle(self):
        """Whether the chat window stays up over the battle itself.

        Not the battle's loading screen, which the window covers whenever the
        garage panel is on: there it stands in for the panel the queue screen
        took away, and it is the garage's setting that asks for it.
        """
        return self._values['enabled'] and self._values['twitch']['battle'] in ('window', 'both')

    def shows_twitch_in_garage(self):
        return self._values['enabled'] and self._values['twitch']['garage']

    def shows_team(self, mode, ally):
        """Whether a battle of this kind shows the allies' (or enemies') ratings and flags."""
        teams = self._values['modes'].get(mode, self._values['modes']['other'])
        return teams['allies' if ally else 'enemies']

    def shows_flags(self, surface):
        return self._values['enabled'] and self._values[surface]['flags']

    def metric(self, surface):
        """The mod's rating when this surface shows it, or None."""
        if self._values['enabled'] and self._values[surface]['rating']:
            return self._values['metric']
        return None

    def extra(self, name, surface):
        """Which window `name` ('battles' or 'winrate') is shown in here, or None.

        Tied to the surface drawing ANYTHING, not to it drawing a rating.
        They were tied to the rating at first, on the reasoning that they are
        read beside it. That was wrong in the one place it mattered: the
        contacts list and the profile show names and flags by default and no
        rating, so a player who asked for battle counts in the garage got
        them everywhere except the two garage screens they actually open.

        A surface turned off entirely still shows nothing, which is what
        "Nothing" in its dropdown means.
        """
        if not self.shows(surface):
            return None
        window = self._values.get(name)
        return window if window in WINDOWS else None

    def winrate_decimal(self):
        """Whether a win rate is drawn to a tenth of a point."""
        return self._values['winrateDecimal']

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

        Changes are merged in at every level: {'battle': {'rating': False}}
        leaves the battle's flags as they were, and {'modes': {'ranked':
        {'enemies': False}}} leaves the ranked allies.
        """
        merged = self.values()
        _merge(merged, changes)
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
        if self._raw is None:
            # A typo mid-edit: keep what is on screen until the file parses.
            return
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
            _logger.exception('could not read %s, using the defaults and leaving the file as it is',
                              self._store)
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

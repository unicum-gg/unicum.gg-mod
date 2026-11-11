"""The average this mod writes into each team's name.

A team name is the client's own field and the only place in a battle where
something can be said about a side rather than about a player. What goes in
it is a mean of the same figures the rows carry, so the line reads as its
rows do: the chosen rating, and the win rate beside it when the rows show
one.

Kept apart from the markers because it travels differently: the markers are
republished on a timer into a view the mod owns, while this rides in the
client's own arena description and is only resent when that description is
(see `_redraw` in drawing.py).
"""
from __future__ import absolute_import

import logging

from unicum import badges, modes, views
from unicum.api.entry import PLAYERS

_logger = logging.getLogger('unicum.battle.teams')

# The battle screens that show a team average: the players panel does not.
# Read by `_mark_teams`, which puts nothing in a team name while all of them
# are waiting for Alt.
_AVERAGE_SURFACES = ('tab', 'loading')


def _mean(values):
    return sum(values) / float(len(values)) if values else None


class TeamNames(object):
    """Writing a side's average into the client's team name field."""

    def _mark_teams(self, controller, data):
        # Says, once per battle, whether this ran at all and what it found.
        # A team name with no average and a team name this never reached look
        # the same on screen, and that is the whole question right now.
        if not getattr(self, '_probed_teams', False):
            self._probed_teams = True
            try:
                _logger.info('team names: shows_average=%s, keys=%r',
                             self._settings.shows_average('battle'),
                             sorted(data.keys()) if hasattr(data, 'keys') else type(data).__name__)
            except Exception:
                _logger.exception('team names: could not describe the data')
        if not self._settings.shows_average('battle'):
            return
        # Not injected at all while every screen that would show it is waiting
        # for Alt.
        #
        # An average rides in the client's own team name field, which draws
        # plain text until TeamNamesHtml re-sets it as HTML. So putting one
        # there for a screen that is hidden shows a raw `<IMG ...>` tag for a
        # frame or two and then drops it, which is all the player ever sees of
        # it. `_publish` asks for a redraw whenever Alt changes what a screen
        # shows, and that is what puts the average back.
        held = self.alt is not None and self.alt.down
        if not held and all(self._settings.alt_only(surface) for surface in _AVERAGE_SURFACES):
            return
        arena = controller._battleCtx.getArenaDP()
        teams = {'allyTeamName': [], 'enemyTeamName': []}
        # A team whose players show nothing gets no average either.
        shows = modes.team_filter(self._settings)
        for vInfo in arena.getVehiclesInfoIterator():
            if vInfo.isObserver() or not shows(vInfo.team):
                continue
            key = 'allyTeamName' if arena.isAllyTeam(vInfo.team) else 'enemyTeamName'
            teams[key].append(vInfo.player.accountDBID)
        for key, account_ids in teams.items():
            average, winrate = self._team_figures(account_ids)
            name = data.get(key)
            if not getattr(self, '_probed_each', False):
                _logger.info('team names: %s -> %d player(s), average=%r, name=%r',
                             key, len(account_ids), average, name)
            if average is None or name is None:
                continue
            if isinstance(name, str):
                # A localised team name arrives as UTF-8 bytes.
                name = name.decode('utf-8', 'replace')
            self._probed_each = True
            # A literal average sign rather than an entity: the field shows
            # plain text until the battle view re-sets it as HTML.
            badge = (self._badges.markup(self._settings.metric('battle'), average)
                     if views.html_team_names() else None)
            parts = [badge or '%d' % round(average)]
            # The same two figures the rows carry, in the same order, so the
            # line over a team reads as the lines under it. Only when the
            # rows carry a win rate at all: a reader who turned those off did
            # not ask for one here either.
            if winrate is not None:
                parts.append(self._badges.winrate_markup(
                    winrate, self._settings.winrate_decimal())
                    if views.html_team_names() else badges.winrate(winrate))
            data[key] = u'%s  \u00d8 %s' % (name, u' '.join(parts))

    def _team_figures(self, account_ids):
        """(mean rating, mean win rate) over the side, each None without one.

        One pass for the two: the rating is read for every player anyway, and
        asking twice would mean two passes over the roster and two chances to
        queue the same fetch.

        A player the site does not know is in neither mean rather than in one
        as a zero, and the two can cover different players: a 30-day win rate
        exists only for somebody who played in those 30 days.
        """
        ratings, winrates = [], []
        window = self._settings.extra('winrate', 'battle')
        for account_id in account_ids:
            if not account_id:
                continue
            if self._lookup.needs_fetch(PLAYERS, account_id):
                self._request(account_id)
            entry = self._lookup.get(PLAYERS, account_id)
            value = self._settings.rating(entry, 'battle')
            if value is not None:
                ratings.append(value)
            if window is not None and entry is not None:
                found = entry.stat('winrate', window)
                if found is not None:
                    winrates.append(found)
        return _mean(ratings), _mean(winrates)

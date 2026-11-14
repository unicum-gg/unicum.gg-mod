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


def tank_of(vInfo):
    """The vehicle id Wargaming keys its own per-vehicle statistics on, or None.

    `compactDescr` is that id: the same number the site stores a tank
    snapshot under, so a pair asked for here and a row stored there are the
    same tank without a translation table in between.

    Here rather than in drawing.py because both halves want it and this is
    the half the other one imports.
    """
    return getattr(getattr(vInfo, 'vehicleType', None), 'compactDescr', None)


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
            teams[key].append((vInfo.player.accountDBID, tank_of(vInfo)))
        for key, pairs in teams.items():
            average, winrate, count = self._team_figures(pairs)
            name = data.get(key)
            if not getattr(self, '_probed_each', False):
                _logger.info('team names: %s -> %d player(s), on_tank=%s, '
                             'average=%r, winrate=%r, battles=%r, name=%r',
                             key, len(pairs), self._on_tank(), average, winrate,
                             count, name)
            if name is None:
                continue
            if isinstance(name, str):
                # A localised team name arrives as UTF-8 bytes.
                name = name.decode('utf-8', 'replace')
            self._probed_each = True
            parts = self._team_parts(average, winrate, count)
            if not parts:
                continue
            # A literal average sign rather than an entity: the field shows
            # plain text until the battle view re-sets it as HTML.
            data[key] = u'%s  \u00d8 %s' % (name, u' '.join(parts))

    def _team_parts(self, average, winrate, count):
        """The side's figures as markup, in the order a row carries them.

        The same three a row carries, drawn by the same builders, so the
        line over a team reads as the lines under it. A missing one is left
        out rather than drawn as a zero, and all three missing is no line at
        all: on the tank, in a mode the site holds nothing about, that is
        the honest answer.
        """
        html = views.html_team_names()
        parts = []
        if average is not None:
            metric = (self._settings.vehicle_metric('battle') if self._on_tank()
                      else self._settings.metric('battle'))
            badge = self._badges.markup(metric, average) if html else None
            parts.append(badge or u'%d' % round(average))
        if winrate is not None:
            parts.append(self._badges.winrate_markup(
                winrate, self._settings.winrate_decimal())
                if html else badges.winrate(winrate))
        if count is not None:
            whole = int(round(count))
            parts.append(self._badges.count_markup(whole) if html
                         else badges.count(whole))
        return parts

    def _team_figures(self, pairs):
        """(mean rating, mean win rate, mean battles) over the side.

        Each None when nothing of it is known. Measured on the same basis
        as the rows under it, which is the whole point: with the rows on
        the tank each player brought, an average of careers answers a
        different question from the one on screen, and two answers to two
        questions in one column read as one answer that does not add up.
        `_on_tank` decides, so the key that swaps the rows swaps this too.

        One pass for the three: they are read off the same records, and
        asking three times would mean three passes over the roster and
        three chances to queue the same fetch.

        A player the site does not know is in no mean rather than in one as
        a zero, and the three can cover different players: a 30-day win
        rate exists only for somebody who played in those 30 days, and a
        tank record only for somebody whose tank the site has seen.
        """
        if self._on_tank():
            return self._tank_figures(pairs)
        ratings, winrates, counts = [], [], []
        winrate_window = self._settings.extra('winrate', 'battle')
        battles_window = self._settings.extra('battles', 'battle')
        for account_id, _ in pairs:
            if not account_id:
                continue
            if self._lookup.needs_fetch(PLAYERS, account_id):
                self._request(account_id)
            entry = self._lookup.get(PLAYERS, account_id)
            value = self._settings.rating(entry, 'battle')
            if value is not None:
                ratings.append(value)
            if entry is None:
                continue
            if winrate_window is not None:
                found = entry.stat('winrate', winrate_window)
                if found is not None:
                    winrates.append(found)
            if battles_window is not None:
                found = entry.stat('battles', battles_window)
                if found is not None:
                    counts.append(found)
        return _mean(ratings), _mean(winrates), _mean(counts)

    def _tank_figures(self, pairs):
        """The same three, over the tanks the side brought.

        Nothing is fetched from here. The rows ask for every one of these
        records as they draw, and asking again would double a read that is
        the heaviest the site serves; the average fills in as those answers
        land, exactly as the rows do.

        The battle count is always counted, never gated on the Battles
        dropdown, because on a tank it is not an extra: four battles and
        four hundred on the same tank are not the same claim, and that is
        true of a side's average as much as of one row.
        """
        mode = self._tank_mode()
        metric = self._settings.vehicle_metric('battle')
        ratings, winrates, counts = [], [], []
        for account_id, tank_id in pairs:
            if not account_id or not tank_id:
                continue
            record = self._lookup.vehicle(account_id, tank_id, mode)
            if record is None or not record.known or not record.battles:
                continue
            value = record.rating(metric) if metric else None
            if value is not None:
                ratings.append(value)
            elif record.winrate is not None:
                # No WN rating for this mode and there never will be: those
                # scales are built on random battles alone.
                winrates.append(record.winrate)
            counts.append(record.battles)
        return _mean(ratings), _mean(winrates), _mean(counts)

"""A sample battle row, drawn by the code that draws the real ones.

The settings window is a garage window and the rows it configures are in a
battle. So every choice about the battle surfaces was made blind: you picked
a rating, a period, a win rate and a battle count, closed the window, queued,
and found out two minutes later that the column read nothing like what you
meant. Changing your mind cost another battle.

What is drawn here is not a picture of a row and not a second drawing of
one. It is the same calls on the same objects -- `Badges.rating`,
`Badges.extras`, `Badges.vehicle`, the flag textures -- given one made-up
player instead of a real one. A row that changes in battle changes here the
same day, because there is only one drawing.

The player is invented and the numbers with them. They are chosen to be
unremarkable rather than impressive: a preview whose figures are all in the
top band would make every scale look the same colour, which is the one thing
the preview exists to show.
"""
from __future__ import absolute_import

import logging

from unicum import badges as badge_lib

_logger = logging.getLogger('unicum.settings_window.preview')

# What the sample player has done. Both windows carry every metric, so the
# line redraws whichever rating and period are chosen rather than falling
# back to lifetime and quietly showing the same number for both.
_RECENT = {'wn7': 1624, 'wn8': 2187, 'wnx': 2291, 'pr': 1452, 'wtr': 9284,
           'winrate': 57.8, 'battles': 412}
_TOTAL = {'wn7': 1483, 'wn8': 1954, 'wnx': 2046, 'pr': 1381, 'wtr': 8713,
          'winrate': 54.6, 'battles': 23184}

# Three, so the "flags per player" choice has something to shorten. They are
# resolved through the same cache as a real player's, so a flag the client
# could not load this session is missing here exactly as it would be there.
_COUNTRIES = ('PL', 'GB-UKM', 'DE')

# The tank the sample player brought. 'mode' scope: the figures are this
# mode's, which is what a random battle answers. A skirmish answers
# 'overall', drawn quieter -- not shown here, because the preview is about
# the choices in this window and the scope is not one of them.
_VEHICLE = {'scope': 'mode', 'battles': 187, 'winrate': 61.4,
            'ratings': {'wn7': 1712, 'wn8': 2318, 'wnx': 2457}}


def _entry():
    """The sample player, as the API would have described them."""
    from unicum.api.entry import Entry
    return Entry(known=True, name=u'Player', countries=list(_COUNTRIES),
                 ratings={'recent': dict(_RECENT), 'total': dict(_TOTAL)})


def _record():
    """The sample player's record on the tank they brought."""
    from unicum.api.entry import Vehicle
    return Vehicle(known=True, scope=_VEHICLE['scope'], mode='random',
                   battles=_VEHICLE['battles'], winrate=_VEHICLE['winrate'],
                   ratings=dict(_VEHICLE['ratings']))


# What a chip says: what the figure is, then the stretch of battles it
# counts. Both, because they are two different questions and a reader who
# cannot answer either is the reason the chip exists -- 2 187 says nothing
# about being WN8 rather than WNX, and 57.8% says nothing about being a
# month rather than a career.
#
# The chip hangs off the badge's right edge, so its width costs the badge
# nothing and the three of them come to about 255px of the 346 a section
# has. Short forms all the same: a caption longer than the figure it names
# reads as the main event.
_WHEN = {'recent': '30D', 'total': 'ALL'}
_WIN_RATE = 'WR'
_BATTLES = 'BTL'
# What the tank row's chips say in place of a period. Which battles they
# count is not a dropdown in this window but the mode being played, so they
# name the tank instead.
_ON_TANK = 'TANK'


def _career(badges, textures, settings, entry, surface):
    """The row as it reads about the player's whole account."""
    parts = []
    # The flags carry no caption. A flag is a flag, which is the one figure
    # on the row nobody has ever had to ask about.
    if settings.shows_flags(surface):
        parts.append(textures.markup(entry, settings['maxFlags']).strip())
    # Built a piece at a time rather than through `rating` and `extras`,
    # which return the whole group already joined: a caption belongs to one
    # badge and there is no way to give one to a badge inside a finished
    # string. Every piece is still drawn by the real builder, so what is
    # restated here is the order, which is three items long and checked.
    metric = settings.metric(surface)
    value = settings.rating(entry, surface)
    if metric is not None and value is not None:
        parts.append(badges.tagged_markup(
            int(round(value)), badges.band(metric, int(round(value))),
            u'%s %s' % (metric.upper(), _WHEN[settings['window']])))
    # Each of the three names its own period, because each has its own
    # dropdown: a reader can ask for a 30-day rating beside a career win
    # rate, and one caption covering all three would be wrong for two.
    window = settings.extra('winrate', surface)
    if window is not None:
        found = entry.stat('winrate', window)
        if found is not None:
            parts.append(badges.tagged_markup(
                badge_lib.winrate(found, settings.winrate_decimal()),
                badges.band('winrate', found, 'percent'),
                u'%s %s' % (_WIN_RATE, _WHEN[window])))
    window = settings.extra('battles', surface)
    if window is not None:
        found = entry.stat('battles', window)
        if found is not None:
            parts.append(badges.tagged_markup(
                badge_lib.count(found), badge_lib.NEUTRAL,
                u'%s %s' % (_BATTLES, _WHEN[window])))
    return u'  '.join(part for part in parts if part)


def _tank(badges, textures, settings, entry, surface):
    """The row as it reads about the tank that player brought."""
    parts = []
    if settings.shows_flags(surface):
        parts.append(textures.markup(entry, settings['maxFlags']).strip())
    # These chips say TANK where the career row's say a period. Which
    # battles they count is the mode being played, not a dropdown, so a
    # period here would be a promise this window does not make.
    record = _record()
    metric = settings.vehicle_metric(surface)
    value = record.rating(metric) if metric else None
    if value is not None:
        parts.append(badges.tagged_markup(
            int(round(value)), badges.band(metric, int(round(value))),
            u'%s %s' % (metric.upper(), _ON_TANK)))
    elif record.winrate is not None:
        # No WN rating for this mode and there never will be: those scales
        # are built on random battles alone. The win rate is what survives.
        parts.append(badges.tagged_markup(
            badge_lib.winrate(record.winrate, settings.winrate_decimal()),
            badges.band('winrate', record.winrate, 'percent'),
            u'%s %s' % (_WIN_RATE, _ON_TANK)))
    parts.append(badges.tagged_markup(
        badge_lib.count(record.battles), badge_lib.NEUTRAL,
        u'%s %s' % (_BATTLES, _ON_TANK)))
    return u'  '.join(part for part in parts if part)


def garage_surface(settings):
    """The garage surface worth previewing, or None if none is switched on.

    The Stats group above the preview is one set of choices for all of the
    garage screens, so any of them would illustrate it. The first that is
    actually switched on is the honest pick: a reader is shown a row from a
    screen they will meet, not one from a screen they turned off.
    """
    from unicum.settings_window.labels import _GARAGE_SURFACES
    for surface in _GARAGE_SURFACES:
        if settings.shows(surface):
            return surface
    return None


def lines(badges, textures, settings, surface='battle'):
    """[(caption, markup)] of what a row on this surface will look like.

    One line for a surface showing one thing, two for 'both': what sits
    there at rest, and what the extended info key swaps it to. The captions
    say which is which, because a reader looking at two rows of pills has no
    other way to tell them apart.

    Empty when the surface draws nothing at all, so the window does not
    offer an example of silence.
    """
    try:
        if not settings.shows(surface):
            return []
        entry = _entry()
        figures = settings.figures(surface)
        career = _career(badges, textures, settings, entry, surface)
        tank = _tank(badges, textures, settings, entry, surface)
        if figures == 'career':
            return [(u'', career)]
        if figures == 'tank':
            return [(u'on the tank', tank)]
        return [(u'at rest', career), (u'with Alt', tank)]
    except Exception:
        # A preview is a convenience and the window is not. Whatever goes
        # wrong in here, the settings must still open.
        _logger.exception('could not draw the %s preview', surface)
        return []

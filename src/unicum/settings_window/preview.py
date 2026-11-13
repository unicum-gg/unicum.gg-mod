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


# The name beside a badge: smaller and dimmer than the figure, on the same
# baseline, so it settles at the bottom right of the image it names rather
# than reading as another figure. 8 against the badge's own 10.
_TAG = '<font face="$FieldFont" size="8" color="#8a8a7e">%s</font>'

# How a period is said in a tag. Short because it sits inside a line of
# badges: "last 30 days" there would be longer than the figure it qualifies.
_WHEN = {'recent': '30d', 'total': 'all'}


def _tagged(markup, name):
    """A drawn figure with its name against it, or '' when nothing was drawn."""
    if not markup:
        return u''
    return markup + _TAG % name


def _career(badges, textures, settings, entry, surface):
    """The row as it reads about the player's whole account."""
    parts = []
    if settings.shows_flags(surface):
        flags = textures.markup(entry, settings['maxFlags'])
        if flags:
            parts.append(_tagged(flags.strip(), u'spoken'))
    # Built a piece at a time rather than through `rating` and `extras`,
    # which return the whole group: a name has to go against each badge, and
    # there is nowhere to put one between two badges already joined. Every
    # piece is still the real one, so only the order is restated here, and
    # the order is three items long and checked.
    metric = settings.metric(surface)
    value = settings.rating(entry, surface)
    if metric is not None and value is not None:
        parts.append(_tagged(badges.markup(metric, value) or u'%d' % round(value),
                             u'%s %s' % (metric.upper(), _WHEN[settings['window']])))
    window = settings.extra('winrate', surface)
    if window is not None:
        found = entry.stat('winrate', window)
        if found is not None:
            parts.append(_tagged(badges.winrate_markup(found, settings.winrate_decimal()),
                                 u'WR %s' % _WHEN[window]))
    window = settings.extra('battles', surface)
    if window is not None:
        found = entry.stat('battles', window)
        if found is not None:
            parts.append(_tagged(badges.count_markup(found), u'battles %s' % _WHEN[window]))
    return u'  '.join(parts)


def _tank(badges, textures, settings, entry, surface):
    """The row as it reads about the tank that player brought."""
    parts = []
    if settings.shows_flags(surface):
        flags = textures.markup(entry, settings['maxFlags'])
        if flags:
            parts.append(_tagged(flags.strip(), u'spoken'))
    # The whole group at once here, unlike the career row: what a tank
    # answers with is not a set of choices in this window but whatever the
    # site holds, so there is no per-piece name to give. One name for the
    # group says what it is about, which is the question being asked.
    #
    # The fallback is the battle's own: with nothing in hand, the career
    # figure in plain grey rather than an empty column, so the preview shows
    # what an unknown tank really looks like instead of showing nothing.
    drawn = badges.vehicle(_record(), settings, surface)
    if drawn:
        parts.append(_tagged(drawn.strip(), u'on the tank'))
    else:
        parts.append(_tagged(badges.plain(entry, settings, surface).strip(),
                             u'career, no record for this tank'))
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
            return [(u'', tank)]
        return [(u'at rest', career), (u'with Alt', tank)]
    except Exception:
        # A preview is a convenience and the window is not. Whatever goes
        # wrong in here, the settings must still open.
        _logger.exception('could not draw the %s preview', surface)
        return []

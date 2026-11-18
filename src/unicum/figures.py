"""The pills a Gameface page draws: a rating, a battle count, a vehicle.

The Scaleform surfaces take their badges as `<IMG>` markup (see `badges.py`);
a page drawn in Gameface takes the same badge as three fields it puts in a
style. One drawing, two wrappings, rather than two drawings that drift -- the
Tab screen, the results screen and the room rows all ask here.

Every figure falls back to text and a colour when the badge cannot be drawn,
which happens for a whole session when the badge folder was not in the
client's resource index at startup.
"""
from __future__ import absolute_import

from unicum import badge_png
from unicum import badges as badge_lib

# What a figure with no band of its own is drawn on, when even the scale is
# missing: the page's own foreground, so it reads as text rather than as a
# pill of some colour nobody chose.
_PLAIN = '#F2F2F7'


def _column(widths, name):
    """The width of one column out of a caller's measurements, or 0.

    0 means "draw it to its own size", which is what a page that is not
    drawing columns wants: one pill after a name is not a column, and
    padding it there would be a gap in the middle of a sentence.
    """
    return int((widths or {}).get(name) or 0)


def columns(rows, metric):
    """{column: width} for a page drawing these rows as columns.

    A column is one width for every pill in it, and that width is not
    knowable from one row: 787 and 5 143 are eight pixels apart, and a list
    of pills each drawn to its own figure lines up nowhere. So the page is
    measured before it is drawn, and every pill of a column is drawn to the
    widest figure that column has to hold.

    The widest ON SCREEN, not the widest a figure can ever be. A count of
    four digits is twenty pixels wider than one of one, and padding every
    count to the largest a count can be would carry that on every row of a
    battle whose counts are all small.

    `rows` is (account rating or None, vehicle record or None) per player,
    and the figures here are measured the same way `vehicle_figures` and
    `rating_pill` draw them: a width measured one way and drawn another
    gives a column sized for something it does not hold.
    """
    widest = {}

    def widen(column, value):
        widest[column] = max(widest.get(column, 0), badge_png.width_of(value))

    for value, record in rows:
        if value is not None:
            widen('rating', int(round(value)))
        if record is None or not record.known or not record.battles:
            continue
        found = record.rating(metric) if metric else None
        if found is not None:
            widen('vehicle', int(round(found)))
        elif record.winrate is not None:
            widen('vehicle', badge_lib.winrate(record.winrate))
        widen('battles', badge_lib.count(record.battles))
    return widest


def count_pill(badges, battles, width=0):
    """{image, width, height} of a battle-count pill, or {text, color}.

    The one neutral band, like every battle count this mod draws: the count
    has no scale of its own, and inventing a colour for it would claim a
    meaning that does not exist.

    `width` is the column this pill stands in, when it stands in one: drawn
    to their own sizes, 70 and 2 836 are a dozen pixels apart and no two
    rows line up. See `columns`.
    """
    text = badge_lib.count(battles)
    found = badges.picture(text, badge_lib.NEUTRAL, width)
    if found is not None:
        path, width, height = found
        return {'image': 'img://%s' % path, 'width': width, 'height': height}
    # `text`, not `value`: the count is already shortened and grouped (844,
    # 161k), and a page's own grouping would make "1 61k" of it.
    return {'text': text, 'color': badge_lib.NEUTRAL}


def rating_pill(badges, scales, metric, value, width=0):
    """{image, width, height} of a rating's badge, or {value, color}.

    The IMAGE, not a shape built in CSS. The mod draws this badge everywhere
    else -- above the vehicles, in the players panel, on the results screen
    -- from `badge_png`, on a fixed grid: 3px of padding, a 6px cell per
    digit, 2px between thousands, rounded corners, the band's colour, white
    text. Reproducing that in a stylesheet gets close and stays visibly not
    the same thing, which is what the first two attempts were. `img://`
    resolves in these pages: the language flags beside these badges are
    already drawn that way.
    """
    found = badges.image(metric, value, width) if metric else None
    if found is not None:
        path, width, height = found
        return {'image': 'img://%s' % path, 'width': width, 'height': height}
    color = scales.color(metric, value) if (metric and scales is not None) else None
    return {'value': int(round(value)), 'color': color or _PLAIN}


def vehicle_figures(badges, scales, record, metric, widths=None):
    """What a player does on one vehicle, as a page draws it, or None.

    None when there is nothing to say: a pair we hold no record for, or one
    with no battles in it. That is the answer the whole figure exists for, so
    it is never dressed up as a zero -- never played and played badly are
    different things.

    `scope` rides along because the two it can hold are not the same claim:
    'mode' is the mode being played, 'overall' is the vehicle over every mode
    at once, which is what the site sends back for a mode Wargaming publishes
    no per-vehicle block about. The page draws the second one quieter.
    """
    if record is None or not record.known or not record.battles:
        return None
    shown = {'scope': record.scope or 'overall',
             'battles': count_pill(badges, record.battles, _column(widths, 'battles'))}
    value = record.rating(metric) if metric else None
    if value is not None:
        shown['rating'] = rating_pill(badges, scales, metric, value,
                                      _column(widths, 'vehicle'))
    # No WN rating for this mode and there never will be: those scales are
    # built from expected values computed on random battles alone. The win
    # rate on the tank is the figure that survives.
    elif record.winrate is not None:
        shown['winrate'] = _winrate_pill(badges, scales, record.winrate,
                                         _column(widths, 'vehicle'))
    return shown


def _winrate_pill(badges, scales, value, width=0):
    text = badge_lib.winrate(value)
    color = scales.color('winrate', value, 'percent') if scales is not None else None
    found = badges.picture(text, color, width) if color else None
    if found is not None:
        path, width, height = found
        return {'image': 'img://%s' % path, 'width': width, 'height': height}
    return {'text': text, 'color': color or _PLAIN}

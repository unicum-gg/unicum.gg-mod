# -*- coding: utf-8 -*-
"""Checks for the win rate and battle count badges drawn beside a rating."""

from checks.common import check


def check_battle_count():
    """The label a battle count badge carries, and why it is rounded."""
    from unicum.badges import count

    check('a small count is written out', count(844) == '844')
    check('and grouped below ten thousand', count(9999) == '9 999')
    check('rounded to whole thousands above it', count(22565) == '22k')
    check('a big one too', count(161762) == '161k')
    check('the boundary rounds', count(10000) == '10k')
    check('and just below it does not', count(9500) == '9 500')
    check('zero is a real answer and is shown', count(0) == '0')

    # The rounding is not about width. A badge is one PNG per distinct label,
    # written into the player's game folder, and a battle count differs for
    # every player met. Rounded, the whole set is about a thousand files and
    # stays there; exact, it would grow without end.
    labels = set(count(n) for n in range(0, 1000000, 137))
    check('the whole range of counts needs only so many badges', len(labels) < 1200)
    check('and none of them carries a decimal', not any('.' in label for label in labels))

    # The client font has no thin space, and a missing glyph draws a box.
    check('nothing the client font cannot draw', all(ord(c) < 128 for c in count(9999)))


def check_winrate_label():
    from unicum.badges import winrate

    check('a win rate is a whole percent by default', winrate(58.7) == '59%')
    check('rounded, not truncated', winrate(58.4) == '58%' and winrate(58.5) == '59%')
    check('to a tenth when asked', winrate(58.7, decimal=True) == '58.7%')
    check('and a round number keeps its tenth', winrate(59.0, decimal=True) == '59.0%')
    # Four characters against six: the pill is drawn into a players panel
    # column, and the rating badge beside it is a whole number too.
    check('the default is the shorter label', len(winrate(58.7)) < len(winrate(58.7, True)))


class _Entry(object):
    def __init__(self, ratings, known=True):
        self.known = known
        self.ratings = ratings

    def stat(self, name, window):
        value = (self.ratings.get(window) or {}).get(name)
        return value if isinstance(value, (int, float)) else None


class _Settings(object):
    """Only what `extras` asks of the settings."""

    def __init__(self, winrate=None, battles=None, rated=True, decimal=False):
        self._winrate, self._battles = winrate, battles
        self._rated, self._decimal = rated, decimal

    def metric(self, surface):
        return 'wnx' if self._rated else None

    def vehicle_metric(self, surface):
        return self.metric(surface)

    def shows(self, surface):
        return self._rated

    def winrate_decimal(self):
        return self._decimal

    def extra(self, name, surface):
        if not self._rated:
            return None
        return self._winrate if name == 'winrate' else self._battles


class _Scales(object):
    def color(self, scale, value, unit=None):
        if scale != 'winrate' or unit != 'percent':
            return None
        return '#4A92B7' if value >= 56 else None


def _badges(tmp, scales=None):
    """A Badges that really draws, into a throwaway folder."""
    from unicum.badges import Badges
    return Badges(scales=scales, directory=tmp, res_path='gui/maps/icons/unicum/badges',
                  drawable=lambda path: True)


def check_extras_badges():
    import os
    import tempfile

    tmp = tempfile.mkdtemp()
    badges = _badges(tmp, _Scales())
    entry = _Entry({'total': {'battles': 161762, 'winrate': 58.7},
                    'recent': {'battles': 72, 'winrate': 52.7}})

    out = badges.extras(entry, _Settings(winrate='total', battles='total'), 'battle')
    check('both figures are drawn as badges, not as text',
          out.count('<IMG') == 2 and '<font' not in out)
    check('the win rate badge is painted on its own band', '59pct.4a92b7.png' in out)
    # The one pill with no scale behind it. A colour invented for it would
    # claim a meaning the site does not publish.
    check('the battle count badge takes the one neutral band', '161k.4a4a4a.png' in out)
    check('they are separated, since two touching images show a seam', '/> <IMG' in out)
    check('with a leading space, since they follow the rating badge', out.startswith(' '))

    written = sorted(os.listdir(tmp))
    check('each badge is a real file on disk',
          '59pct.4a92b7.png' in written and '161k.4a4a4a.png' in written)
    check('and a PNG at that',
          open(os.path.join(tmp, '161k.4a4a4a.png'), 'rb').read(8) == '\x89PNG\r\n\x1a\n')

    # Drawn once and reused: the whole reason the label is rounded.
    before = len(os.listdir(tmp))
    badges.extras(_Entry({'total': {'battles': 161999, 'winrate': 58.9}}),
                  _Settings(winrate='total', battles='total'), 'battle')
    check('a nearby count reuses the badge already drawn', len(os.listdir(tmp)) == before)

    out = badges.extras(entry, _Settings(winrate='total', battles='total', decimal=True), 'battle')
    check('the decimal setting reaches the badge', '58-7pct.4a92b7.png' in out)


class _Record(object):
    """Only what `vehicle` asks of a per-vehicle record."""

    def __init__(self, scope='mode', battles=70, wnx=1933.6, known=True):
        self.known, self.scope, self.battles = known, scope, battles
        self._wnx = wnx

    def rating(self, metric):
        return self._wnx if metric == 'wnx' else None


def check_vehicle_badges():
    """The pills a battle row shows for the tank its player brought."""
    import tempfile

    badges = _badges(tempfile.mkdtemp(), _VehicleScales())
    settings = _Settings(battles='total')

    out = badges.vehicle(_Record(), settings, 'battle')
    check('the rating on this tank is drawn as a badge',
          'wnx.1934.4a92b7.png' in out and out.count('<IMG') == 2)
    check('the count of battles on it comes with it, on the neutral band',
          '70.4a4a4a.png' in out)
    check('it leads with a space, like every group that follows a name',
          out.startswith(' '))

    # The same drawing as the career rating: same metric, same value, same
    # file. A second set of files for the same number would drift from the
    # first the day one scale changes.
    check('and the career rating draws the very same file',
          badges.markup('wnx', 1933.6) in out)

    check('a record of every mode together draws nothing, since the row has it already',
          badges.vehicle(_Record(scope='overall'), settings, 'battle') == '')
    check('a pair the site has never stored draws nothing',
          badges.vehicle(_Record(known=False), settings, 'battle') == '')
    check('and no record at all draws nothing', badges.vehicle(None, settings, 'battle') == '')
    check('a reader who wanted no counts gets the rating alone',
          badges.vehicle(_Record(), _Settings(), 'battle').count('<IMG') == 1)
    check('a mode the WN scales do not measure leaves the count to speak alone',
          badges.vehicle(_Record(wnx=None), settings, 'battle').count('<IMG') == 1)
    check('and a surface showing nothing draws nothing here either',
          badges.vehicle(_Record(), _Settings(rated=False), 'battle') == '')


class _VehicleScales(object):
    def color(self, scale, value, unit=None):
        if scale == 'winrate':
            return '#4A92B7' if value >= 56 else None
        return '#4A92B7'


def check_plain_rating():
    """The grey number a row falls back to, and why it is not a pill."""
    import tempfile

    class Settings(object):
        def __init__(self, value=1933.6):
            self._value = value

        def rating(self, entry, surface):
            return self._value

    badges = _badges(tempfile.mkdtemp(), _VehicleScales())
    out = badges.plain(None, Settings(), 'battle')
    check('the stand-in is text, not a badge', '<IMG' not in out and '1934' in out)
    check('and grey, so it does not read as a figure on a scale', '#8a8a8a' in out)
    check('it leads with a space, like every group that follows a name', out.startswith(' '))
    check('no rating to stand in for draws nothing', badges.plain(None, Settings(None), 'battle') == '')


def check_marker_width_ignores_tags():
    """A tag's own text is not text the player reads.

    The colour of the grey stand-in carries three 8s. Measured as rating
    digits they would have widened the column by half a pill.
    """
    from unicum.battle.drawing import markup_width

    check('a grey figure is measured by its digits alone',
          markup_width('<font face="$FieldFont" color="#8a8a8a">1934</font>') == 4 * 7)
    check('an image still counts for the width it declares',
          markup_width('<IMG SRC="img://b.png" width="38" height="12"/>') == 38)


def check_alt_swaps_to_the_tank():
    """Alt puts a battle row on the tank its player brought, where it can.

    The swap is a swap, not an addition: the players panel column is the
    narrowest place these numbers fit, and the career figure and the figure
    on one tank cannot both be in it.
    """
    from unicum import modes
    from unicum.battle.flags import BattleFlags

    class Alt(object):
        def __init__(self, down):
            self.down = down

    class Settings(object):
        def __init__(self, alt_only=False):
            self._alt_only = alt_only

        def alt_only(self, surface):
            return self._alt_only

    drawing = BattleFlags(None, None, None, None, Settings())

    check('with no Alt key at all the row stays on the career figures',
          not drawing._on_tank('battle'))
    drawing.alt = Alt(False)
    check('and with Alt up too', not drawing._on_tank('battle'))
    drawing.alt = Alt(True)
    check('held, the row goes on the tank', drawing._on_tank('battle'))
    drawing._settings = Settings(alt_only=True)
    check('unless Alt already means "show this surface at all" here, '
          'which one key cannot mean twice',
          not drawing._on_tank('battle'))

    # Read once for the battle. It cannot change inside one, and this is
    # asked for every player on every pass.
    held, asked = modes.current_wg_mode, []
    try:
        modes.current_wg_mode = lambda: asked.append(1) or 'random'
        check('the mode is the one being played', drawing._tank_mode() == 'random')
        drawing._tank_mode()
        drawing._tank_mode()
        check('and the client answers for it once a battle, not once a row', len(asked) == 1)

        drawing = BattleFlags(None, None, None, None, Settings())
        del asked[:]
        modes.current_wg_mode = lambda: asked.append(1) or None
        check('a mode Wargaming publishes no per-vehicle record for has no mode at all',
              drawing._tank_mode() is None)
        drawing._tank_mode()
        check('and that answer is held too, rather than asked again every pass',
              len(asked) == 1)
    finally:
        modes.current_wg_mode = held

    # One request for the screen, not one per row: Alt going down redraws
    # every row in the same pass.
    asked = []

    class Session(object):
        def callback(self, delay, func):
            asked.append(delay)

    from unicum.battle.flags import _BATCH_DELAY, _PAIR_DELAY
    # The rows of a loading battle arrive over seconds, and nobody is waiting
    # on a tank the instant it lands: Alt comes later. Gathering them for
    # longer than the roster is what makes it one request instead of ten.
    check('the tanks are gathered for longer than the roster is',
          _PAIR_DELAY > _BATCH_DELAY)

    drawing = BattleFlags(Session(), None, None, None, Settings())
    drawing._request_vehicle(1, 100, 'random')
    drawing._request_vehicle(2, 200, 'random')
    drawing._request_vehicle(3, 300, 'random')
    check('three rows asking at once queue one flush',
          len(asked) == 1 and drawing._pending_pairs == set([(1, 100), (2, 200), (3, 300)]))
    check('and it is the slower of the two delays', asked == [_PAIR_DELAY])
    check('and the mode they are read over travels with them',
          drawing._pair_mode == 'random')


def check_a_tank_is_asked_for_before_alt():
    """The pairs are asked for as the battle loads, not on the first press.

    Waiting for the press was the cheaper of the two and it put the whole wait
    where it hurts: the site answers these in twenty to thirty seconds under
    load, which turns a key held for a moment into a key held for nothing.
    """
    from unicum import modes
    from unicum.battle.flags import BattleFlags

    class Alt(object):
        def __init__(self, down):
            self.down = down

    class Lookup(object):
        def needs_fetch(self, kind, entity_id):
            return False

        def get(self, kind, entity_id):
            return None

        def needs_vehicle(self, account_id, tank_id, mode=None):
            return True

        def vehicle(self, account_id, tank_id, mode=None):
            return None

    class Settings(object):
        def shows(self, surface):
            return True

        def shows_flags(self, surface):
            return False

        def alt_only(self, surface):
            return False

    class Badges(object):
        def rating(self, entry, settings, surface):
            return ' career'

        def extras(self, entry, settings, surface, compact=False):
            return ''

        def vehicle(self, record, settings, surface):
            return ''

        def plain(self, entry, settings, surface):
            return ' grey'

    class Session(object):
        def callback(self, delay, func):
            pass

    drawing = BattleFlags(Session(), Lookup(), None, Badges(), Settings())
    held = modes.current_wg_mode
    try:
        modes.current_wg_mode = lambda: 'random'
        badge = drawing._marker(1, 100)[1]
        check('a tank is asked for with Alt up, so the answer is in hand when Alt goes down',
              drawing._pending_pairs == set([(1, 100)]))
        check('and until it is, the row shows the career figures as always', badge == ' career')

        drawing.alt = Alt(True)
        check('held with nothing in hand, the row shows the career rating in grey, not nothing',
              drawing._marker(1, 100)[1] == ' grey')

        modes.current_wg_mode = lambda: None
        drawing = BattleFlags(Session(), Lookup(), None, Badges(), Settings())
        drawing.alt = Alt(True)
        check('and in a mode with no per-vehicle record, no pair is asked for and nothing changes',
              drawing._marker(1, 100)[1] == ' career' and not drawing._pending_pairs)
    finally:
        modes.current_wg_mode = held

    check('a row with no tank asks for nothing',
          BattleFlags(Session(), Lookup(), None, Badges(), Settings())._marker(1)[1] == ' career')


def check_extras_fallbacks():
    import tempfile
    from unicum.badges import Badges

    entry = _Entry({'total': {'battles': 161762, 'winrate': 58.7}})
    plain = _badges(tempfile.mkdtemp(), _Scales())

    low = _Entry({'total': {'battles': 10, 'winrate': 48.0}})
    out = plain.extras(low, _Settings(winrate='total'), 'battle')
    check('a win rate off the painted range still shows, as text',
          '48%' in out and '<font' in out)

    # A client whose resource folder was made after it started cannot load
    # any badge; the figures must still reach the player.
    mute = Badges(scales=_Scales(), directory='', drawable=lambda path: False)
    out = mute.extras(entry, _Settings(winrate='total', battles='total'), 'battle')
    check('a client that cannot draw badges falls back to text',
          '59%' in out and '161k' in out and '<IMG' not in out)
    check('and that text is in the client own font', "face='$FieldFont'" in out)

    check('either figure can be off on its own',
          '%' not in plain.extras(entry, _Settings(battles='total'), 'battle'))
    check('both off draws nothing at all', plain.extras(entry, _Settings(), 'battle') == '')
    check('a surface turned off entirely draws nothing',
          plain.extras(entry, _Settings(winrate='total', battles='total', rated=False), 'battle') == '')
    check('a player the server knows nothing about draws nothing',
          plain.extras(_Entry({}, known=False), _Settings(battles='total'), 'battle') == '')
    check('nor does one whose window the server has not filled',
          plain.extras(_Entry({'total': {}}), _Settings(winrate='total', battles='total'), 'battle') == '')


def check_badge_glyphs():
    """The masks a badge is laid out from, and the ones the new labels need."""
    from unicum import badge_png

    for label in ('59%', '58.7%', '161k', '9 999'):
        width = badge_png.width_of(label)
        check('a badge of %r has a width' % label, width > 0)
        drawn, rows = badge_png.pixels(label, '#4A92B7')
        check('and draws to exactly that width',
              drawn == width and len(rows) == badge_png.HEIGHT)

    # Every glyph these labels need must be in the set, or its cell comes out
    # blank and the badge silently loses a character.
    masks = badge_png._load()
    for char in '0123456789.%k':
        check('the mask set has %r' % char,
              char in masks['digits'] and char in masks['cells'])
    check('a digit keeps the grid cell the layout assumes',
          badge_png.cell_of('0') == badge_png.DIGIT_WIDTH)
    check('while a full stop is narrower than a digit',
          badge_png.cell_of('.') < badge_png.DIGIT_WIDTH)
    check('and a percent sign is wider', badge_png.cell_of('%') > badge_png.DIGIT_WIDTH)
    check('a rating still lays out grouped by thousands',
          ''.join(badge_png.layout(3818)) == '3 818')


def check_entry_stat():
    """Unlike a rating, these never fall back to the other window."""
    from unicum.api.entry import Entry

    entry = Entry(known=True, ratings={'total': {'battles': 22565, 'winrate': 59.5},
                                       'recent': {'battles': None, 'winrate': None}})
    check('a figure comes from the window it was asked for',
          entry.stat('battles', 'total') == 22565)
    check('and a window the server has not filled says so, rather than lying',
          entry.stat('battles', 'recent') is None)
    check('a window that does not exist at all is the same answer',
          entry.stat('battles', 'nonsense') is None)
    check('while a rating still falls back to the career value',
          Entry(known=True, ratings={'total': {'wnx': 3274}, 'recent': {'wnx': None}})
          .rating('wnx', 'recent') == 3274)


def check_extras_setting():
    import os
    import tempfile
    from unicum.runtime.session import Session
    from unicum.settings import Settings, validate

    check('battles are shown over a whole career by default', validate({})['battles'] == 'total')
    check('so is the win rate', validate({})['winrate'] == 'total')
    check('and the win rate is a whole percent', validate({})['winrateDecimal'] is False)
    check('a nonsense value falls back to the default',
          validate({'battles': 'yesterday'})['battles'] == 'total')
    check('and a real one survives', validate({'battles': 'recent'})['battles'] == 'recent')
    check('the decimal survives a round trip',
          validate({'winrateDecimal': True})['winrateDecimal'] is True)

    settings = Settings(Session(generation=0),
                        store=os.path.join(tempfile.mkdtemp(), 'settings.json'))
    check('a fresh install draws both over the career',
          settings.extra('battles', 'battle') == 'total'
          and settings.extra('winrate', 'battle') == 'total')
    check('and to a whole percent', not settings.winrate_decimal())
    settings.update({'battles': 'off'})
    check('off means nothing to draw', settings.extra('battles', 'battle') is None)
    check('and leaves the win rate alone', settings.extra('winrate', 'battle') == 'total')
    # Deliberately NOT tied to the rating: contacts and the profile show a
    # name and a flag by default, and a player who asks for battle counts in
    # the garage means those two screens above all.
    settings.update({'battle': {'rating': False}})
    check('a surface showing flags but no rating still draws them',
          settings.extra('winrate', 'battle') == 'total')
    settings.update({'battle': {'rating': False, 'flags': False}})
    check('a surface turned off entirely draws nothing',
          settings.extra('winrate', 'battle') is None)
    settings.update({'enabled': False})
    check('the mod off draws nothing anywhere',
          settings.extra('winrate', 'contacts') is None)

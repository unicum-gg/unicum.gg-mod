"""Checks for the settings: the file, the window's translation, and a live change."""

import json
import os

from checks.common import SAMPLE_PLAYERS, check
from checks.fakes import FakeContact, FakeContactConverter


def check_settings(workdir):
    """settings.json is created, validated and saved; changes are announced."""
    from unicum.runtime.session import Session
    from unicum.settings import DEFAULTS, Settings, validate

    check('anything missing or wrong falls back to its default',
          validate({'maxFlags': 7, 'metric': 'wn9', 'window': 'total',
                    'battle': {'rating': 'yes', 'flags': 'no'}}) ==
          dict(DEFAULTS, maxFlags=3, window='total'))
    migrated = validate({'metric': 'wn8', 'ratings': True, 'averages': False, 'flags': True,
                         'contacts': True, 'battle': False})
    check('the first settings.json is read surface by surface',
          migrated['metric'] == 'wn8'
          and migrated['stronghold'] == {'flags': True, 'rating': True}
          and migrated['skirmishRoom'] == {'flags': True, 'rating': True, 'average': False}
          # `figures` rides along because the battle surface carries it now;
          # the first settings.json predates it, so it arrives at its default.
          and migrated['battle'] == {'flags': False, 'rating': False, 'average': False,
                                     'figures': 'both'}
          and migrated['contacts']['rating'] is False)
    migrated = validate({'contacts': {'flags': True, 'rating': 'none'},
                         'battle': {'flags': True, 'rating': 'wn7', 'average': True}})
    check('a rating per surface becomes the one rating, shown where one was',
          migrated['metric'] == 'wn7' and migrated['battle']['rating'] is True
          and migrated['contacts']['rating'] is False)

    store = os.path.join(workdir, 'settings-check', 'settings.json')
    settings = Settings(Session(generation=0), store=store)
    check('a first start writes the defaults', os.path.isfile(store))
    check('the recent window is labelled as such', settings.label('battle') == '30d WNX')
    check('a surface without a rating has no label', settings.label('contacts') is None)

    # Wargaming's two are career figures: the 30-day choice stands, since it
    # is still what a WN rating uses, and it does not reach these.
    from unicum.api.entry import Entry
    settings.update({'metric': 'wtr'})
    check('a career rating is not labelled as 30 days', settings.label('battle') == 'WTR')
    check('and is read over the career, whatever the period says',
          settings.rating(Entry(known=True, ratings={'total': {'wtr': 8740},
                                                     'recent': {'wtr': None}}),
                          'battle') == 8740)
    check('while a WN rating still follows the period',
          settings.window_of('wnx') == 'recent' and settings.window_of('pr') == 'total')
    check('a per-vehicle figure falls back to WNX for a career rating',
          settings.vehicle_metric('battle') == 'wnx')
    settings.update({'metric': 'wn7'})
    check('and keeps a WN rating as it is',
          settings.vehicle_metric('battle') == 'wn7'
          and settings.vehicle_metric('contacts') is None)
    settings.update({'metric': 'wnx'})

    changes = []
    settings.on_change(lambda: changes.append(settings.metric('contacts')))
    settings.update({'metric': 'wn8', 'contacts': {'rating': True}, 'battle': {'rating': False},
                     'window': 'total'})
    check('a change is announced once', changes == ['wn8'])
    check('every surface shows the one rating, or none',
          settings.label('contacts') == 'WN8' and settings.metric('battle') is None)
    check('a surface change leaves the rest of the surface alone', settings['contacts']['flags'])
    check('no rating means no average either', not settings.shows_average('battle'))
    settings.update({'contacts': {'rating': True}})
    check('a change to the same values is not announced', changes == ['wn8'])
    with open(store, 'rb') as handle:
        check('and saved', json.load(handle)['contacts']['rating'] is True)

    with open(store, 'wb') as handle:
        handle.write('{"metric": "wn8",')
    typo = Settings(Session(generation=0), store=store)
    with open(store, 'rb') as handle:
        check('a settings.json that does not parse is left as it is', handle.read() == '{"metric": "wn8",')
    check('and the defaults are used meanwhile', typo.metric('battle') == 'wnx')
    settings._check()
    check('a hand edit that does not parse keeps the settings on screen', settings.metric('contacts') == 'wn8')

    settings.update({'enabled': False})
    check('the master switch turns every surface off',
          not settings.shows('contacts') and not settings.shows_flags('battle'))


def check_settings_preview(workdir):
    """The sample battle row the window draws, so a choice can be seen at all.

    The point of the preview is that it is not a second drawing: it runs the
    same badges the battle runs. So the checks are about what it asks for,
    not about what comes out -- the shape of a badge is checked where badges
    are checked.
    """
    import tempfile

    from unicum.runtime.session import Session
    from unicum.settings import METRICS, Settings, validate
    from unicum.settings.validating import _merge
    from unicum.settings_window import preview
    from unicum.settings_window.codec import from_window
    from unicum.settings_window.page import preview_lines

    from checks.extras import _VehicleScales, _badges

    badges = _badges(tempfile.mkdtemp(), _VehicleScales())

    class Textures(object):
        """Stands in for the flag cache: one tag per country, up to the limit."""

        def markup(self, entry, limit=None):
            codes = entry.flags[:limit] if limit else []
            return u''.join(u'<IMG src="%s.png"/>' % code for code in codes)

    settings = Settings(Session(generation=0), store=os.path.join(workdir, 'preview.json'))
    textures = Textures()

    settings.update({'battle': {'figures': 'career', 'rating': True, 'flags': True}})
    lines = preview.lines(badges, textures, settings)
    check('the career choice previews one row, with no caption to disambiguate',
          len(lines) == 1 and lines[0][0] == u'' and u'<IMG' in lines[0][1])

    settings.update({'battle': {'figures': 'both'}})
    both = preview.lines(badges, textures, settings)
    check('asking for both previews the resting row and the one Alt swaps to',
          len(both) == 2 and [row[0] for row in both] == [u'at rest', u'with Alt']
          and both[0][1] != both[1][1])

    settings.update({'battle': {'figures': 'tank'}})
    tank = preview.lines(badges, textures, settings)
    check('and the tank choice previews the tank row alone',
          len(tank) == 1 and tank[0][1] == both[1][1])

    # The flags are the one part a reader can turn off on its own, so it is
    # the one that proves the preview reads the live settings rather than a
    # snapshot taken when the window opened.
    settings.update({'battle': {'flags': False}})
    check('turning the flags off takes them out of the preview too',
          u'<IMG src="PL.png"/>' not in preview.lines(badges, textures, settings)[0][1])

    # ----------------------------------------- each pill carries its name
    settings.update({'battle': {'flags': True, 'rating': True, 'figures': 'both'},
                     'metric': 'wnx', 'window': 'recent',
                     # The 30-day win rate, because the scale this check
                     # stands up gives no band under 56 and the career one
                     # is 54.6: a badge with no band is not drawn at all.
                     'winrate': 'recent', 'battles': 'total'})
    from unicum import badge_png

    named = preview.lines(badges, textures, settings)[0][1]
    check('each badge carries what it is, in the badge and not beside it',
          u'.wnx' in named and u'.wr' in named and u'.btl' in named
          and u'<font' not in named)
    # The chip has been redesigned twice and kept its file name both times,
    # which left every badge already on disk being served at the new one's
    # width. The size is in the name now.
    chip_w, chip_h = badge_png._chip_size(u'WNX')
    check('and its file name says what size chip drew it',
          u'.wnx%dx%d.' % (chip_w, chip_h) in named)

    # The chip hangs off the corner rather than sitting inside it, which is
    # what keeps the figure's last digit readable. To the right only: these
    # images sit inline among plain badges and flags, and Scaleform lines an
    # inline image up by its bottom edge, so one pixel of extra height would
    # lift its badge off the line the row shares. This is the check that
    # caught that, and it is here to catch it again.
    chip, rows = badge_png._chip_size(u'WNX')
    width, height = badge_png.tag_size(2291, u'WNX')
    check('a tagged badge is the badge, with the chip hanging off to its right',
          width == badge_png.width_of(2291) + chip - badge_png.TAG_OVERLAP)
    check('and it is exactly as tall as a badge with no chip, so a row stays level',
          height == badge_png.HEIGHT
          and len(badge_png.tagged_pixels(2291, '#7E3BC9', u'WNX')[2]) == badge_png.HEIGHT)
    check('and the badge under it is pixel for pixel the badge drawn anywhere else',
          badge_png.tagged_pixels(2291, '#7E3BC9', u'WNX')[2][0][:badge_png.width_of(2291) * 4]
          == badge_png.pixels(2291, '#7E3BC9')[1][0])
    check('the chip is tall enough to read and still inside the badge it marks',
          4 < rows < badge_png.HEIGHT)

    tank = preview.lines(badges, textures, settings)[1][1]
    check('the tank row carries the same chips, its caption saying whose battles',
          u'.wnx' in tank and u'.btl' in tank)

    settings.update({'battles': 'off', 'winrate': 'off', 'battle': {'flags': False}})
    bare = preview.lines(badges, textures, settings)[0][1]
    check('a badge that is not drawn carries no chip either',
          u'.wnx' in bare and u'.wr' not in bare and u'.btl' not in bare
          and u'PL.png' not in bare)
    settings.update({'battles': 'total', 'winrate': 'total', 'battle': {'flags': True}})

    settings.update({'battle': {'rating': False, 'average': False, 'flags': False}})
    check('a surface showing nothing previews nothing, rather than an empty row',
          preview.lines(badges, textures, settings) == [])

    # A preview is a convenience; the settings window is not. Anything that
    # goes wrong drawing it must cost the line, never the window.
    class Broken(object):
        def markup(self, entry, limit=None):
            raise RuntimeError('no flags today')

    settings.update({'battle': {'rating': True, 'flags': True, 'figures': 'both'}})
    check('a drawing that throws costs the preview and not the window',
          preview.lines(badges, Broken(), settings) == [])
    check('and no badges at all means no rows asked for',
          preview_lines(None) == ())

    rows = preview_lines((badges, textures, settings))
    check('a caption is joined to its row with spaces, never a tab',
          len(rows) == 2 and rows[0].startswith(u'at rest   ')
          and not [row for row in rows if u'	' in row])

    # ------------------------------------------------ the garage's own row
    from unicum.settings_window.page import garage_preview_lines

    settings.update({'contacts': {'rating': True, 'flags': True},
                     'battles': 'total', 'winrate': 'total'})
    garage = garage_preview_lines((badges, textures, settings))
    check('the garage row says which of the five screens it is a row of',
          len(garage) == 1 and garage[0].startswith(u'Contacts list   '))
    check('and no number in it goes unnamed',
          u'.wnx' in garage[0])

    # A battle count is shortened past ten thousand wherever it is drawn:
    # the badge is an image and each distinct number is a file, so the limit
    # is the count of files, not the width of a column. The window's tooltip
    # said otherwise for a while, and this is here so it cannot say it again
    # without something going red.
    from unicum.badges import count
    check('a battle count reads the same in the garage as in the battle',
          count(23184) == '23k' and count(9999) == '9 999')
    settings.update({'battle': {'rating': True, 'flags': False, 'figures': 'career'}})
    battle_row = preview_lines((badges, textures, settings))[0]
    check('so the two previews carry the same count badge',
          u'23k' in garage[0] and u'23k' in battle_row)

    settings.update({'contacts': {'rating': False, 'flags': False}})
    after = garage_preview_lines((badges, textures, settings))
    check('with contacts off it falls through to the next screen that is on',
          len(after) == 1 and after[0].startswith(u'Profile   '))

    for surface in ('contacts', 'profile', 'skirmishRoom', 'stronghold', 'battleResults'):
        settings.update({surface: {'rating': False, 'flags': False, 'average': False}})
    check('and with every garage screen off there is nothing to preview',
          garage_preview_lines((badges, textures, settings)) == ())

    # ------------------------------------ a choice seen before it is saved
    #
    # The tab holds a change until Apply, like the client's own settings do.
    # So the preview was showing what was already saved, which is the one
    # thing nobody opens a preview to find out.
    from unicum.settings_window.codec import read_native, read_peek

    sent = u'peek\tmetric\td\t1\nbattleShow\td\t2\npeek\twinrateDecimal\tc\t1'
    peeked = read_peek(sent)
    check('a peeked choice is read, and only the peeked ones',
          peeked == {'metric': 1, 'winrateDecimal': True})
    raw, _ = read_native(sent)
    check('and a peek is never read as a change, so it is never saved',
          raw == {'battleShow': 2})
    check('the settling line says nothing is pending any more',
          read_peek(u'peek\t\t\t') == {})

    # The preview drawn off a peeked metric is the one the player is about
    # to choose, not the one on disk.
    settings.update({'metric': 'wnx', 'window': 'recent',
                     'battle': {'rating': True, 'flags': False, 'figures': 'career'},
                     'winrate': 'off', 'battles': 'off'})
    saved = preview_lines((badges, textures, settings))

    merged = settings.values()
    _merge(merged, from_window({'metric': METRICS.index('wn8')}))
    shadow = Settings.__new__(Settings)
    shadow._values = validate(merged)
    peeking = preview_lines((badges, textures, shadow))
    check('a peeked rating previews the badge the player is about to choose',
          u'.wn8' in peeking[0] and u'.wnx' in saved[0])
    check('and what is on disk has not moved',
          settings['metric'] == 'wnx')


def check_res_mods_version():
    """The newest res_mods folder is picked by version, not by spelling."""
    from unicum.config import _version_key
    check('2.10 is newer than 2.9', max(['2.9.0.0', '2.10.0.0', '2.4.0.0'], key=_version_key) == '2.10.0.0')


def check_settings_window():
    """The window's values and settings.json's translate both ways."""
    from unicum.settings import DEFAULTS, validate
    from unicum.settings_window.codec import from_window, to_window
    from unicum.settings_window.labels import CARD_VAR, SHOW_CHOICES

    values = validate(dict(DEFAULTS, metric='wn7', window='total', maxFlags=2,
                           battle={'flags': False, 'rating': True, 'average': True}))
    window = to_window(values)
    check('dropdowns are stored by index', window['metric'] == 0 and window['window'] == 1)
    check('a screen is one choice of what it shows',
          SHOW_CHOICES[window['battleShow']][0] == 'Ratings only' and 'contactsAverage' not in window)
    check('an average goes with the ratings',
          from_window({'battleResultsShow': 2})['battleResults'] == {'rating': False, 'flags': True, 'average': False}
          and 'average' not in from_window({'contactsShow': 0})['contacts'])
    check('and read back to the same settings', validate(dict(values, **from_window(window))) == values)
    check('an index out of range is ignored', 'metric' not in from_window({'metric': 9}))

    # The two twin traps of a surface key that is not a switch. The window
    # rewrites a surface's dict whole, so a choice written beside the show
    # dropdown has to be merged into it rather than assigned over it; and
    # validate() reads every surface key with the same reader, which used to
    # be the boolean one and would have turned 'tank' back into its default
    # without a word. Either one alone makes a setting that resets itself.
    from unicum.settings import FIGURE_CHOICES, FIGURED
    from unicum.settings_window.labels import FIGURE_LABELS
    check('the figures dropdown has a label for each of its values',
          len(FIGURE_LABELS) == len(FIGURE_CHOICES))
    for index, name in enumerate(FIGURE_CHOICES):
        sent = from_window({'battleFigures': index})
        check('the window sends back %s, and it survives validation' % name,
              sent['battle']['figures'] == name
              and validate(dict(DEFAULTS, **sent))['battle']['figures'] == name)
    check('a figures choice rides beside what the show dropdown writes',
          from_window({'battleShow': 1, 'battleFigures': 1})['battle']
          == {'rating': True, 'flags': False, 'average': True, 'figures': 'tank'})
    check('and a surface that has no such choice is never sent one',
          [s for s in ('contacts', 'profile') if s not in FIGURED]
          and 'contactsFigures' not in to_window(values))
    check('an index out of range leaves the choice alone',
          'figures' not in from_window({'battleFigures': 9}).get('battle', {}))

    # The hidden switch this grew out of. It shipped for a day, settable only
    # by hand, so the file of whoever did is owed its meaning.
    check('a settings.json written when this was onTank is read as the tank',
          validate({'battle': {'onTank': True}})['battle']['figures'] == 'tank')
    check('and one that says otherwise lands on the default',
          validate({'battle': {'onTank': False}})['battle']['figures'] == 'both'
          and validate({'battle': {'figures': 'nonsense'}})['battle']['figures'] == 'both')
    check('a choice already written wins over the switch it replaced',
          validate({'battle': {'onTank': True, 'figures': 'career'}})['battle']['figures'] == 'career')
    check('the account card box shows the card by default and follows its state',
          to_window(values)[CARD_VAR] is True and to_window(values, False)[CARD_VAR] is False)
    check('the account card box is not a settings.json value', CARD_VAR not in from_window({CARD_VAR: False}))

    from unicum.settings_window.labels import HIDE_LABEL, HIDE_VAR
    check('the hiding box follows the site rather than settings.json',
          to_window(values)[HIDE_VAR] is False
          and to_window(values, True, True)[HIDE_VAR] is True
          and HIDE_VAR not in from_window({HIDE_VAR: True}))

    from unicum.settings_window.codec import read_native
    from unicum.settings_window.labels import CONNECT_VAR
    from unicum.settings_window.page import native_page
    lines = [line.split(u'\t') for line in native_page(values, u'license__', True).split(u'\n')]
    check('the hiding box is not offered to somebody who cannot use it',
          not any(line[2] == HIDE_LABEL for line in lines if line[0] == u'checkbox'))
    supporter = [line.split(u'\t') for line
                 in native_page(values, u'license__', True, True, True, True).split(u'\n')]
    boxes = [line[2] for line in supporter if line[0] == u'checkbox']
    hiding = [line for line in supporter if line[0] == u'checkbox' and line[2] == HIDE_LABEL]
    check('and is offered, ticked, to a supporter who has hidden theirs',
          len(hiding) == 1 and hiding[0][3] == u'1')
    check('right after the box that shares them',
          boxes.index(HIDE_LABEL) == boxes.index(u'Share my loadouts') + 1)
    from unicum.settings_window.labels import HIDE_BATTLES_LABEL
    check('the battle-hiding box is left out when no account is linked',
          HIDE_BATTLES_LABEL not in [line[2] for line in lines if line[0] == u'checkbox'])
    linked = [line.split(u'\t') for line
              in native_page(values, u'license__', True, True, False, False, True).split(u'\n')]
    battles = [line for line in linked if line[0] == u'checkbox' and line[2] == HIDE_BATTLES_LABEL]
    check('and offered, ticked, to any linked account that has hidden its battles',
          len(battles) == 1 and battles[0][3] == u'1')
    check('there is no box that stops sending battles',
          not any(line[1] == u'sendBattles' for line in linked if line[0] == u'checkbox'))
    check('the settings tab has the Garage, Battle and Twitch sub-tabs',
          [line[1] for line in lines if line[0] == u'tab'] == [u'Garage', u'Battle', u'Twitch'])
    flags = [line for line in lines if line[0] == u'dropdown' and line[1] == u'maxFlags'][0]
    check('a dropdown carries its index, its offset and its options',
          flags[3:] == [u'1', u'1', u'1|2|3'] and len([l for l in lines if l[0] == u'dropdown']) == 33)
    check('a linked Twitch shows its channel, an unlinked one a Connect button',
          [u'text', u'Channel: license__'] in lines
          and [u'button', CONNECT_VAR, u'Channel: not linked', u'Connect'] in
          [line.split(u'\t') for line in native_page(values, u'', False).split(u'\n')])
    from unicum.settings_window.labels import (DISCORD_VAR, LINKS, SOURCE_VAR,
                                               SUPPORT_VAR)
    from unicum.settings_window.window import link_url
    unlinked = [line.split(u'\t') for line in native_page(values, u'', False).split(u'\n')]
    check('the settings tab has the link buttons, whatever the Twitch state',
          all([u'button', var, text, word] in lines and [u'button', var, text, word] in unlinked
              for var, text, word in LINKS))
    check('each one opens its own page, the support one tagged with what opened it',
          link_url(SUPPORT_VAR, 'settings-tab').startswith('https://unicum.gg/support?')
          and 'utm_content=settings-tab' in link_url(SUPPORT_VAR, 'settings-tab')
          and link_url(DISCORD_VAR, 'x').startswith('https://discord.gg/')
          and link_url(SOURCE_VAR, 'x') == 'https://github.com/unicum-gg/unicum.gg-mod'
          and link_url('maxFlags', 'x') is None)
    raw, buttons = read_native(u'maxFlags\td\t3\nmetric\td\t1\ntankButton\tc\t0\n%s\tb\t1\nbad line' % CONNECT_VAR)
    check('what the tab sends back reads as the window\'s values',
          raw == {'maxFlags': 3, 'metric': 1, 'tankButton': False} and buttons == [CONNECT_VAR]
          and from_window(raw) == {'maxFlags': 3, 'metric': 'wn8', 'tankButton': False})


def check_settings_registration(workdir):
    """Registering the page with the API, and what it tells it about the site's own boxes.

    Nothing reached `install` before this one: modsSettingsApi is not among
    the fake client modules, so the window returned early and the whole
    registration path went untested. A field added to the state tuple's two
    readers and not to its seed took the mod down at every start with the
    suite green, and two of the three values handed to the API were left at
    their defaults, which the API hands back as the player's choice.
    """
    import sys
    import types
    from unicum.runtime.session import Session
    from unicum.settings import Settings
    from unicum.settings_window import window as window_module
    from unicum.settings_window.labels import HIDE_BATTLES_VAR, HIDE_VAR, LINKAGE

    class FakeApi(object):
        """The surface the window uses, and what it was handed."""

        def __init__(self):
            self.templates = []
            self.pushed = []

        def setModTemplate(self, linkage, template, on_window, on_button):
            self.templates.append(template)

        def updateModSettings(self, linkage, values):
            self.pushed.append(values)

    class FakeLink(object):
        """An account that has hidden both, which is what the bugs needed to show."""

        secret = 's' * 64
        name = 'Someone'
        twitch = 'ready'
        supporter = True
        card_hidden = False

        def __init__(self):
            self.loadouts_hidden = True
            self.battles_hidden = True
            self.asked = []

        def hide_loadouts(self, hidden, done=None):
            self.asked.append(('loadouts', hidden))

        def hide_battles(self, hidden, done=None):
            self.asked.append(('battles', hidden))

    drawn = []

    def fake_template(values, channel=u'', linked=False, card_shown=True,
                      supporter=False, loadouts_hidden=False, battles_hidden=None,
                      drawing=None):
        """Stands in for `page.template`, which needs the client's own builders."""
        drawn.append((loadouts_hidden, battles_hidden))
        return {'linkage': LINKAGE}

    api, link = FakeApi(), FakeLink()
    module = types.ModuleType('gui.modsSettingsApi')
    module.g_modsSettingsApi = api
    held, held_template = sys.modules.get('gui.modsSettingsApi'), window_module.template
    sys.modules['gui.modsSettingsApi'] = module
    sys.modules['gui'].modsSettingsApi = module
    window_module.template = fake_template
    try:
        settings = Settings(Session(generation=0), store=os.path.join(workdir, 'registration.json'))
        page = window_module.SettingsWindow(Session(generation=0), settings, link)
        page.install()
        check('the window registers its page with the API',
              len(api.templates) == 1 and len(api.pushed) == 1)
        check('and draws it before the link has answered, as its seed says',
              drawn[-1] == (False, None))

        page._check_state()
        check('a link that hides both draws both boxes ticked', drawn[-1] == (True, True))
        # The API keeps its own copy of every value it is given and hands that
        # back as the player's choice, so what is pushed has to say the same as
        # what was drawn. Left at their defaults, the two hiding boxes went out
        # unticked, and the answer read as a player asking for what they had
        # hidden to be put back on their page.
        check('and tells the API about them what it drew',
              api.pushed[-1][HIDE_VAR] is True and api.pushed[-1][HIDE_BATTLES_VAR] is True)
        page._on_settings()
        check('a settings change keeps telling it the truth about them',
              api.pushed[-1][HIDE_VAR] is True and api.pushed[-1][HIDE_BATTLES_VAR] is True)
        # The harm itself, end to end.
        page._on_window(LINKAGE, api.pushed[-1])
        check('so what the API sends back unhides nothing', link.asked == [])
    finally:
        window_module.template = held_template
        if held is None:
            sys.modules.pop('gui.modsSettingsApi', None)
            delattr(sys.modules['gui'], 'modsSettingsApi')
        else:
            sys.modules['gui.modsSettingsApi'] = held

def check_live_settings(bigworld):
    """Editing settings.json while the mod runs reaches the surfaces.

    Uses the first sample player, whose language check_contacts_redraw
    already resolved.
    """
    from unicum.settings import STORE

    def contact_region():
        return FakeContactConverter.makeBaseUserProps(FakeContact(SAMPLE_PLAYERS[0]))['region']

    if not contact_region():
        print('skip no language came back, live settings not checked')
        return
    with open(STORE, 'rb') as handle:
        saved = json.load(handle)
    try:
        _write(STORE, dict(saved, contacts={'flags': False, 'rating': False}))
        bigworld.run_pending()
        check('switching contacts off in settings.json removes their flags',
              contact_region() is None)
        _write(STORE, dict(saved, maxFlags=1))
        bigworld.run_pending()
        check('and back on, with one flag at most',
              contact_region() is not None and contact_region().count('<IMG') == 1)
    finally:
        _write(STORE, saved)
        bigworld.run_pending()


def _write(path, values):
    with open(path, 'wb') as handle:
        json.dump(values, handle)
    # A later mtime than the last check saw, however fast the test runs.
    stamp = os.path.getmtime(path) + 10 + len(json.dumps(values))
    os.utime(path, (stamp, stamp))

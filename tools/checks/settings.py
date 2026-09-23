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
          and migrated['battle'] == {'flags': False, 'rating': False, 'average': False}
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


def check_res_mods_version():
    """The newest res_mods folder is picked by version, not by spelling."""
    from unicum.config import _version_key
    check('2.10 is newer than 2.9', max(['2.9.0.0', '2.10.0.0', '2.4.0.0'], key=_version_key) == '2.10.0.0')


def check_settings_window():
    """The window's values and settings.json's translate both ways."""
    from unicum.settings import DEFAULTS, validate
    from unicum.settings_window import CARD_VAR, SHOW_CHOICES, from_window, to_window

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
    check('the account card box shows the card by default and follows its state',
          to_window(values)[CARD_VAR] is True and to_window(values, False)[CARD_VAR] is False)
    check('the account card box is not a settings.json value', CARD_VAR not in from_window({CARD_VAR: False}))

    from unicum.settings_window import CONNECT_VAR, native_page, read_native
    lines = [line.split(u'\t') for line in native_page(values, u'license__', True).split(u'\n')]
    check('the settings tab has the Garage, Battle and Twitch sub-tabs',
          [line[1] for line in lines if line[0] == u'tab'] == [u'Garage', u'Battle', u'Twitch'])
    flags = [line for line in lines if line[0] == u'dropdown' and line[1] == u'maxFlags'][0]
    check('a dropdown carries its index, its offset and its options',
          flags[3:] == [u'1', u'1', u'1|2|3'] and len([l for l in lines if l[0] == u'dropdown']) == 22)
    check('a linked Twitch shows its channel, an unlinked one a Connect button',
          [u'text', u'Channel: license__'] in lines
          and [u'button', CONNECT_VAR, u'Channel: not linked', u'Connect'] in
          [line.split(u'\t') for line in native_page(values, u'', False).split(u'\n')])
    from unicum.settings_window import DISCORD_VAR, LINKS, SOURCE_VAR, SUPPORT_VAR, link_url
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

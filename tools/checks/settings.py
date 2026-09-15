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

    settings.update({'enabled': False})
    check('the master switch turns every surface off',
          not settings.shows('contacts') and not settings.shows_flags('battle'))


def check_settings_window():
    """The window's values and settings.json's translate both ways."""
    from unicum.settings import DEFAULTS, validate
    from unicum.settings_window import from_window, to_window

    values = validate(dict(DEFAULTS, metric='wn7', window='total', maxFlags=2,
                           battle={'flags': False, 'rating': True, 'average': True}))
    window = to_window(values)
    check('dropdowns are stored by index', window['metric'] == 0 and window['window'] == 1)
    check('surfaces are spelled flat', window['battleFlags'] is False and 'contactsAverage' not in window)
    check('and read back to the same settings', validate(dict(values, **from_window(window))) == values)
    check('an index out of range is ignored', 'metric' not in from_window({'metric': 9}))


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

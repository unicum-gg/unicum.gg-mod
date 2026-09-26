"""Checks for the loadouts the mod sends: what changes, and what is never sent twice."""

from checks.common import check


def check_loadouts():
    from unicum.loadouts import changed, fingerprint

    first = {'tankId': 7169, 'crew': [{'role': 'commander', 'skills': ['repair']}]}
    same = {'crew': [{'role': 'commander', 'skills': ['repair']}], 'tankId': 7169}
    other = {'tankId': 7169, 'crew': [{'role': 'commander', 'skills': ['brotherhood']}]}
    check('a loadout fingerprints the same whatever order its keys come in',
          fingerprint(first) == fingerprint(same))
    check('a changed skill changes the fingerprint', fingerprint(first) != fingerprint(other))

    sent = {7169: fingerprint(first)}
    check('an unchanged vehicle is not sent again',
          changed([first], sent, set([7169])) == [])
    check('a vehicle whose setup moved is sent',
          [r['tankId'] for r in changed([other], sent, set([7169]))] == [7169])
    check('a vehicle we have never sent is sent',
          [r['tankId'] for r in changed([first], {}, set())] == [7169])
    # The fingerprints outlive the server's own rows: this file sits in the
    # player's game folder and knows nothing of a database that was restored
    # from a backup, so a vehicle the server does not list is sent again even
    # though we believe we sent it.
    check('a vehicle the server no longer holds is sent again',
          [r['tankId'] for r in changed([first], sent, set())] == [7169])
    check('with no answer from the server, the fingerprints alone decide',
          changed([first], sent, None) == [])


def check_loadout_setting():
    import os
    import tempfile
    from unicum.runtime.session import Session
    from unicum.settings import Settings, validate

    check('loadouts are sent unless the player says otherwise',
          validate({})['sendLoadouts'] is True)
    check('the switch survives a round trip',
          validate({'sendLoadouts': False})['sendLoadouts'] is False)
    settings = Settings(Session(generation=0),
                        store=os.path.join(tempfile.mkdtemp(), 'settings.json'))
    check('a fresh install sends them', settings.sends_loadouts())
    settings.update({'sendLoadouts': False})
    check('turning it off stops them', not settings.sends_loadouts())
    settings.update({'sendLoadouts': True, 'enabled': False})
    check('the mod off sends nothing either', not settings.sends_loadouts())

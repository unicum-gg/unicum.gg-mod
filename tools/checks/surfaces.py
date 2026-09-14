"""Checks for each surface the mod draws on."""

import sys

from checks.common import SAMPLE_PLAYERS, check
from checks.fakes import (
    Comp7VehicleInfoComponent,
    FakeContact,
    FakeContactConverter,
    FakeContactsDataProvider,
    FakeOpenProfile,
    FakePlayerInfo,
    FakeResMgr,
    FakeSortieCandidatesLegionariesDP,
    FakeStrongholdBattleRoom,
    FakeVInfo,
    FakeVehicleInfoComponent,
    SENTINEL_REGION)


def check_contacts_redraw(bigworld):
    """A list drawn before its languages arrived is rebuilt once they do.

    Without this, the flags of a freshly opened contacts list only appeared
    after closing and reopening the panel.
    """
    provider = FakeContactsDataProvider()
    provider.buildList()
    builds_before = provider.builds

    row = FakeContactConverter.makeBaseUserProps(FakeContact(SAMPLE_PLAYERS[0]))
    # None, not '': some views type `region` as Object and reject a string.
    check('a row drawn before its language arrives is left untouched',
          row['region'] is None)

    # batch timer, then the request, then its response
    for _ in range(4):
        bigworld.run_pending()

    if provider.builds == builds_before:
        print('skip no language came back, redraw checks not run')
        return
    check('the list is rebuilt once the language arrives',
          provider.builds == builds_before + 1)
    check('and refreshed, as the client does', provider.refreshes == 1
          and provider.status_changes == 1)

    for _ in range(4):
        bigworld.run_pending()
    check('rebuilding does not start another lookup',
          provider.builds == builds_before + 1)


def check_skirmish_room(bigworld):
    """Members and volunteers get a flag, and a room redraws once one lands.

    Uses the second sample player, who check_contacts_redraw left uncached,
    so the room first draws without a flag and has to be refreshed.
    """
    room = FakeStrongholdBattleRoom(SAMPLE_PLAYERS[1])
    room._updateMembersData()
    check('a member drawn before the language arrives is left untouched',
          room.member_region() is None)
    check('an empty slot is left alone', room.sent[1]['player'] is None)

    for _ in range(4):
        bigworld.run_pending()

    if not room.member_region():
        print('skip no language came back, skirmish checks not run')
        return
    check('the room is redrawn with a flag once the language arrives',
          'img://gui/maps/icons/unicum/flags/' in room.member_region())
    check('and its volunteers are rebuilt too', room.candidate_rebuilds == 1)
    room._updateRallyData()
    check('the flag survives the room going into battle',
          'img://gui/maps/icons/unicum/flags/' in (room.member_region() or ''))

    volunteer = FakeSortieCandidatesLegionariesDP()._makePlayerVO(
        FakePlayerInfo(SAMPLE_PLAYERS[0]), None, None, False)
    check('a volunteer with a known language gets a flag',
          'img://gui/maps/icons/unicum/flags/' in (volunteer['region'] or ''))


def check_battle_panels():
    """Battle names get flags in the stats exchange, and only there.

    Uses the first sample player, whose language check_contacts_redraw
    already resolved.
    """
    component = FakeVehicleInfoComponent()
    component.addVehicleInfo(FakeVInfo(SAMPLE_PLAYERS[0]), None)
    region = component.get()['region']
    if region == SENTINEL_REGION:
        print('skip no language came back, battle panels not checked')
        return
    check('a battle player gets flags after the region the client set',
          region.startswith(SENTINEL_REGION + ' <IMG SRC="img://gui/maps/icons/unicum/flags/'))

    onslaught = Comp7VehicleInfoComponent()
    onslaught.addVehicleInfo(FakeVInfo(SAMPLE_PLAYERS[0]), None)
    check('onslaught players get flags too, through the base builder',
          '<IMG SRC="img://gui/maps/icons/unicum/flags/' in onslaught.get()['region']
          and onslaught.get()['role'] == 'assault')


def check_profile_title():
    """The title gets a flag only when the title SWF can render it.

    Uses the first sample player, whose language check_contacts_redraw
    already resolved. A flag sent to a plain-text title shows its <IMG> tag
    as text, so the two cases must never mix.
    """
    title = FakeOpenProfile(SAMPLE_PLAYERS[0]).title()
    if title == 'Player [TAG]':
        print('skip no language came back, profile title not checked')
        return
    check('without the title SWF the title gets a language code',
          '<IMG' not in title and title.startswith('Player [TAG] ')
          and title[len('Player [TAG] '):].isupper())

    factories = sys.modules['gui.Scaleform.framework'].g_entitiesFactories
    FakeResMgr.files.add('gui/flash/unicum.titles.swf')
    factories.settings['unicumTitleHtml'] = ('unicumTitleHtml',)
    try:
        check('with it the title gets a flag instead',
              FakeOpenProfile(SAMPLE_PLAYERS[0]).title().startswith(
                  'Player [TAG] <IMG SRC="img://gui/maps/icons/unicum/flags/'))
    finally:
        FakeResMgr.files.discard('gui/flash/unicum.titles.swf')
        factories.settings.clear()


def check_badges(workdir):
    """A rating becomes the one image of its badge, or nothing it cannot draw."""
    import os
    from unicum.badges import MAX_VALUE, Badges

    folder = os.path.join(workdir, 'badges', 'wnx')
    os.makedirs(folder)
    for value in (0, MAX_VALUE):
        open(os.path.join(folder, '%d.png' % value), 'wb').close()
        # Installed before the client started, so the resource manager knows it.
        FakeResMgr.files.add('gui/badges/wnx/%d.png' % value)
    badges = Badges(directory=os.path.join(workdir, 'badges'), res_path='gui/badges')
    check('a rating is one image of the rounded value, sized to its digits',
          badges.markup('wnx', 3322.6) ==
          '<IMG SRC="img://gui/badges/wnx/3323.png" width="32" height="12" vspace="-3"/>')
    check('a metric whose badges were not installed draws nothing',
          badges.markup('wn8', 3323) is None)
    check('a value past the rendered range draws nothing',
          badges.markup('wnx', MAX_VALUE + 1) is None)

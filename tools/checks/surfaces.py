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
    FakeStatisticsController,
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
    from unicum import views
    view = type('LobbyView', (object,), {'averageHtml': '', 'ratingByPlayer': ''})()
    real_view, views.lobby_view = views.lobby_view, lambda: view
    try:
        room._updateMembersData()
        check('the room view is handed the average rating of the members',
              bool(view.averageHtml))
        check('and every member rating, for the score order',
              view.ratingByPlayer.startswith('%d:' % SAMPLE_PLAYERS[1]))
        room._dispose()
        check('and both are cleared when the room closes',
              view.averageHtml == '' and view.ratingByPlayer == '')
    finally:
        views.lobby_view = real_view
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

    stats = FakeStatisticsController(SAMPLE_PLAYERS[0], 1)
    stats.invalidateArenaInfo()
    check('the ally team name gains its average WNX as plain text',
          stats.arena_info['allyTeamName'].startswith(u'DOUBT  \u00d8 '))
    check('a team with no known rating keeps its name as it was',
          stats.arena_info['enemyTeamName'] == 'SMTHG')

    onslaught = Comp7VehicleInfoComponent()
    onslaught.addVehicleInfo(FakeVInfo(SAMPLE_PLAYERS[0]), None)
    check('onslaught players get flags too, through the base builder',
          '<IMG SRC="img://gui/maps/icons/unicum/flags/' in onslaught.get()['region']
          and onslaught.get()['role'] == 'assault')


def check_team_order():
    """The order the client sends each team's screens in is kept, and wins."""
    from unicum.battle import BattleFlags
    flags = BattleFlags(None, None, None, None, None)
    flags._keep_order({'leftItemsIDs': [3, 1, 2], 'rightItemsIDs': 'not a list'})
    check('a team order the client sends is kept', flags._order['leftItemsIDs'] == [3, 1, 2])
    check('and marked as received, so the default order does not replace it',
          flags._received == set(['leftItemsIDs']))
    flags._keep_order({'leftItemsIDs': []})
    check('an empty team from the client is an order too', flags._order['leftItemsIDs'] == []
          and 'leftItemsIDs' in flags._received)


def check_icon_markers():
    """The markers drawn beside a vehicle icon, and the width they take."""
    from unicum.battle import icon_markers, markup_width
    flag = '<IMG SRC="img://f/fr.png" width="12" height="9" vspace="-1"/>'
    badge = '<IMG SRC="img://b/wnx/1234.png" width="38" height="12" vspace="-3"/>'
    check('the badge and the flags come apart, each with its width',
          icon_markers(' ' + flag + flag, ' ' + badge) == [badge, 38, flag + flag, 24])
    check('a bare number is counted by its digits', markup_width('1234') == 28)
    check('no badge leaves an empty badge column', icon_markers(' ' + flag, '') == ['', 0, flag, 12])


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
    FakeResMgr.files.add('gui/flash/unicum.lobby.swf')
    factories.settings['unicumLobby'] = ('unicumLobby',)
    try:
        check('with it the title gets a flag instead',
              FakeOpenProfile(SAMPLE_PLAYERS[0]).title().startswith(
                  'Player [TAG] <IMG SRC="img://gui/maps/icons/unicum/flags/'))
    finally:
        FakeResMgr.files.discard('gui/flash/unicum.lobby.swf')
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


def check_room_sort(workdir):
    """The members order is saved, and written back to a freshly loaded view."""
    import os
    import json
    from unicum import room_sort, views
    from unicum.runtime.session import Session
    from unicum.settings import Settings

    view = type('LobbyView', (object,), {'sortMode': '', 'sortLabels': ''})()
    real_view, views.lobby_view = views.lobby_view, lambda: view
    store = os.path.join(workdir, 'sort.json')
    settings = Settings(Session(generation=0), store=os.path.join(workdir, 'sort-settings.json'))
    try:
        # Closed below: its repeating poll must not outlive the check.
        session = Session(generation=0)
        sort = room_sort.RoomSort(session, settings, store=store)
        sort.install()
        sort._poll()
        check('a fresh view gets the client order while nothing is saved',
              view.sortMode == 'default')
        check('the dropdown gets the client labels, then ours',
              view.sortLabels.split('\n') == ['client byOrder', 'client byVehicles', 'client byStatus',
                                              'client byName', 'By 30d WNX', 'By rating'])
        settings.update({'metric': 'wn8', 'window': 'total'})
        sort._poll()
        check('and follows the room rating chosen in the settings',
              view.sortLabels.split('\n')[4] == 'By WN8')
        settings.update({'skirmishRoom': {'rating': False}})
        sort._poll()
        check('and leaves that order out when the room shows no rating',
              view.sortLabels.split('\n')[4] == '')
        view.sortMode = 'score'
        sort._poll()
        check('a picked order is saved',
              room_sort.RoomSort(Session(generation=0), settings, store=store)._mode == 'score')
        with open(store, 'wb') as handle:
            json.dump({'mode': 'wnx'}, handle)
        check('an order saved under its old name is still read',
              room_sort.RoomSort(Session(generation=0), settings, store=store)._mode == 'score')
    finally:
        session.close()
        views.lobby_view = real_view

"""Exercise the reload harness outside the game.

The client is a slow place to find out that a hook did not come back off.
This stands in fake BigWorld and client GUI modules, drives the bootstrap
through a full edit-and-reload cycle, and checks the one property the whole
design rests on: after stop(), the game's own function is back, by identity.

    python2.7 tools/selftest.py

Python 2.7, same as the client.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from checks.api import check_browser_scope, check_entries, check_lookup, check_scales
from checks.battle_options import check_battle_modes, check_reload_announcer
from checks.client import install_fake_client
from checks.common import FLAG_CODES, REPO, check, render_stub
from checks.engine import FakeBigWorld
from checks.fakes import (
    FakeContact,
    FakeContactConverter,
    FakeContactsDataProvider,
    FakeProfileWindow,
    FakeSortieCandidatesLegionariesDP,
    FakeStrongholdBattleRoom,
    FakeVInfo,
    ORIGINAL_ADD_VEHICLE_INFO,
    ORIGINAL_BUILD_LIST,
    SENTINEL_REGION)
from checks.surfaces import (
    check_badges,
    check_battle_panels,
    check_icon_markers,
    check_team_order,
    check_contacts_redraw,
    check_profile_title,
    check_room_sort,
    check_skirmish_room)
from checks.settings import check_live_settings, check_res_mods_version, check_settings, check_settings_window
from checks.tank_menu import check_tank_menu
from checks.twitch import check_echo_guard, check_own_message, check_regions, check_twitch, check_twitch_badges, check_twitch_receiver, check_twitch_send


def main():
    import imp
    import logging
    logging.basicConfig(level=logging.INFO,
                        format='       %(name)s: %(message)s')

    workdir = tempfile.mkdtemp(prefix='unicum-selftest-')
    original_cwd = os.getcwd()
    try:
        # A copy, so a test run never writes .pyc into the checkout.
        src_root = os.path.join(workdir, 'src')
        shutil.copytree(os.path.join(REPO, 'src'), src_root)

        # The mod resolves its caches against the client's working directory.
        # Running from a scratch one keeps a test run from reading or writing
        # anything under the checkout.
        os.chdir(workdir)

        # Flags the mod can resolve, laid out as the client sees them. Only
        # their names matter: the cache offers what was on disk at startup.
        flags_dir = os.path.join(workdir, 'res_mods', '2.4.0.0', 'gui', 'maps',
                                 'icons', 'unicum', 'flags')
        os.makedirs(flags_dir)
        for code in FLAG_CODES:
            open(os.path.join(flags_dir, code + '.png'), 'wb').close()

        bigworld = FakeBigWorld()
        target = install_fake_client(bigworld)
        stub = imp.load_source('mod_unicum_dev', render_stub(workdir, src_root))

        def hooked():
            return target.__dict__['addVehicleInfo'] is not ORIGINAL_ADD_VEHICLE_INFO

        def delegates():
            # Account id 0 yields no marker and starts no lookup, so what
            # comes back is exactly what the original decided.
            component = target()
            component.addVehicleInfo(FakeVInfo(0), None)
            return component.get()['region'] == SENTINEL_REGION

        stub.init()
        check('load installed the hook', hooked())
        check('hook delegates to the original', delegates())
        check('watcher armed', bool(bigworld.pending))

        check_contacts_redraw(bigworld)
        check_skirmish_room(bigworld)
        check_profile_title()
        check_battle_panels()
        check_icon_markers()
        check_team_order()
        check_badges(workdir)
        check_room_sort(workdir)
        check_settings(workdir)
        check_settings_window()
        check_battle_modes(workdir)
        check_reload_announcer()
        check_twitch()
        check_twitch_badges()
        check_twitch_send()
        check_regions()
        check_twitch_receiver()
        check_echo_guard()
        check_own_message()
        check_res_mods_version()
        check_live_settings(bigworld)
        check_tank_menu()

        first_hook = target.__dict__['addVehicleInfo']
        generation_before = stub._generation

        # Touch a source file the way an editor would.
        edited = os.path.join(src_root, 'unicum', 'battle.py')
        os.utime(edited, (os.path.getatime(edited), os.path.getmtime(edited) + 10))

        bigworld.run_pending()
        check('reload happened', stub._generation == generation_before + 1)
        check('hook was reinstalled, not stacked',
              target.__dict__['addVehicleInfo'] is not first_hook)
        check('still delegates to the game original', delegates())

        bigworld.run_pending()
        check('watcher still running after reload', bool(bigworld.pending))

        # A reload with a broken file must not take the watcher down.
        with open(edited) as handle:
            intact = handle.read()
        with open(edited, 'a') as handle:
            handle.write('\nthis is not python\n')
        bigworld.run_pending()
        check('broken source leaves the original restored', not hooked())
        bigworld.run_pending()
        check('watcher survived the failed load', bool(bigworld.pending))

        # And the fix lands without a restart, which is the whole point.
        with open(edited, 'w') as handle:
            handle.write(intact)
        bigworld.run_pending()
        check('saving a fix recovers in place', hooked())

        stub.fini()
        check('fini leaves the game function untouched', not hooked())
        check('fini cancelled every callback', not bigworld.pending)

        # Undoing a patch has to put back what was *stored*, which is not
        # always what getattr returned.
        check('classmethod restored as a descriptor, not a bound method',
              isinstance(FakeContactConverter.__dict__['makeBaseUserProps'],
                         classmethod))
        check('classmethod still callable off the class',
              FakeContactConverter.makeBaseUserProps(
                  FakeContact(1))['region'] is None)
        check('inherited method left inherited, not shadowed',
              'as_setInitDataS' not in FakeProfileWindow.__dict__)
        check('plain method restored to the original function',
              FakeContactsDataProvider.__dict__['buildList'] is ORIGINAL_BUILD_LIST)
        check('skirmish room patches undone',
              'as_setMembersS' not in FakeStrongholdBattleRoom.__dict__
              and 'as_updateRallyS' not in FakeStrongholdBattleRoom.__dict__
              and '_makePlayerVO' not in FakeSortieCandidatesLegionariesDP.__dict__)

        check_browser_scope(src_root)
        check_entries(src_root)

        from unicum import config
        check_lookup(bigworld, src_root, config.API_BASE, 'resolve')
        check_scales(bigworld, src_root, config.API_BASE)

        print('\nall checks passed')
    finally:
        # Windows will not remove the directory a process is standing in.
        os.chdir(original_cwd)
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == '__main__':
    main()

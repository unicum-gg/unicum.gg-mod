"""Registers the fake client modules the mod imports."""

import sys
import types

from checks.fakes import (
    FakeBrowserController,
    FakeContactConverter,
    FakeContactsDataProvider,
    FakeEntitiesFactories,
    FakeLobbyContext,
    FakeProfileWindow,
    FakeResMgr,
    FakeSortieCandidatesLegionariesDP,
    FakeStrongholdBattleRoom,
    FakeStatisticsController,
    FakeVehicleInfoComponent)
from checks.engine import FakeEvent, FakeEventBus
from checks.surfaces import check_profile_title


def _package(name):
    module = types.ModuleType(name)
    module.__path__ = []
    sys.modules[name] = module
    return module


def _attach(parent, name, module):
    sys.modules[name] = module
    setattr(sys.modules[parent], name.rsplit('.', 1)[1], module)


def install_fake_client(bigworld):
    """Register the client modules the mod imports.

    Only the surface the mod actually touches, and each stand-in keeps the
    real signature: a fake that accepts anything would hide exactly the kind
    of mismatch this test exists to catch -- the decorator collision on
    getRegionCode was one.
    """
    sys.modules['BigWorld'] = bigworld

    for name in ('gui', 'gui.Scaleform', 'gui.Scaleform.daapi',
                 'gui.Scaleform.daapi.view', 'gui.Scaleform.daapi.view.lobby',
                 'gui.Scaleform.daapi.view.battle',
                 'gui.Scaleform.daapi.view.battle.shared',
                 'gui.Scaleform.daapi.view.battle.shared.stats_exchange',
                 'helpers', 'skeletons', 'skeletons.gui'):
        _package(name)

    exchange = types.ModuleType(
        'gui.Scaleform.daapi.view.battle.shared.stats_exchange.vehicle')
    exchange.VehicleInfoComponent = FakeVehicleInfoComponent
    _attach('gui.Scaleform.daapi.view.battle.shared.stats_exchange',
            'gui.Scaleform.daapi.view.battle.shared.stats_exchange.vehicle', exchange)
    stats_ctrl = types.ModuleType(
        'gui.Scaleform.daapi.view.battle.shared.stats_exchange.stats_ctrl')
    stats_ctrl.BattleStatisticsDataController = FakeStatisticsController
    _attach('gui.Scaleform.daapi.view.battle.shared.stats_exchange',
            'gui.Scaleform.daapi.view.battle.shared.stats_exchange.stats_ctrl', stats_ctrl)

    for name in ('gui.Scaleform.daapi.view.lobby.profile',
                 'gui.Scaleform.daapi.view.lobby.fortifications',
                 'gui.Scaleform.daapi.view.lobby.rally', 'messenger',
                 'messenger.gui', 'messenger.gui.Scaleform',
                 'messenger.gui.Scaleform.data'):
        _package(name)

    # views.py. The SWFs start out missing, so install() stands down and
    # profile titles keep their language code; check_profile_title adds it.
    sys.modules['ResMgr'] = FakeResMgr

    # The client's player-state events. `__init__.py` reaches for these while
    # it starts, to hold the first-run restart until the garage is up, and
    # twitch_window subscribes to the queue ones.
    player_events = types.ModuleType('PlayerEvents')
    player_events.g_playerEvents = type('PlayerEvents', (object,), {})()
    for name in ('onAccountShowGUI', 'onAccountBecomePlayer', 'onAvatarBecomePlayer',
                 'onAvatarBecomeNonPlayer', 'onArenaCreated', 'onEnqueued', 'onDequeued',
                 'onEnqueueFailure', 'onKickedFromQueue'):
        setattr(player_events.g_playerEvents, name, FakeEvent())
    sys.modules['PlayerEvents'] = player_events
    _package('frameworks')
    wulf = types.ModuleType('frameworks.wulf')
    wulf.WindowLayer = type('WindowLayer', (object,), {'SERVICE_LAYOUT': 'service'})
    wulf.WindowStatus = type('WindowStatus', (object,), {'DESTROYING': 4, 'DESTROYED': 5})
    wulf.ViewModel = type('ViewModel', (object,), {})
    _attach('frameworks', 'frameworks.wulf', wulf)
    for name in ('gui.app_loader', 'gui.Scaleform.framework',
                 'gui.Scaleform.framework.entities',
                 'gui.Scaleform.framework.managers', 'gui.shared'):
        _package(name)
    app_settings = types.ModuleType('gui.app_loader.settings')
    app_settings.APP_NAME_SPACE = type('APP_NAME_SPACE', (object,), {'SF_LOBBY': 'lobby', 'SF_BATTLE': 'battle'})
    _attach('gui.app_loader', 'gui.app_loader.settings', app_settings)
    framework = sys.modules['gui.Scaleform.framework']
    framework.ScopeTemplates = type('ScopeTemplates', (object,), {'GLOBAL_SCOPE': 'global'})
    framework.ViewSettings = lambda *args: args
    framework.g_entitiesFactories = FakeEntitiesFactories()
    view_module = types.ModuleType('gui.Scaleform.framework.entities.View')
    view_module.View = type('View', (object,), {})
    view_module.ViewKey = lambda alias, name=None: (alias, name or alias)
    _attach('gui.Scaleform.framework.entities',
            'gui.Scaleform.framework.entities.View', view_module)
    sf_window = types.ModuleType('gui.Scaleform.framework.entities.sf_window')
    sf_window.SFWindow = type('SFWindow', (object,), {})
    _attach('gui.Scaleform.framework.entities',
            'gui.Scaleform.framework.entities.sf_window', sf_window)
    loaders = types.ModuleType('gui.Scaleform.framework.managers.loaders')
    loaders.SFViewLoadParams = lambda alias, parent=None: alias
    _attach('gui.Scaleform.framework.managers',
            'gui.Scaleform.framework.managers.loaders', loaders)
    shared = sys.modules['gui.shared']
    shared.EVENT_BUS_SCOPE = type('EVENT_BUS_SCOPE', (object,), {'GLOBAL': 'global', 'BATTLE': 'battle'})
    shared.events = types.ModuleType('gui.shared.events')
    shared.events.GameEvent = type('GameEvent', (object,), {'BATTLE_LOADING': 'battleLoading'})
    shared.g_eventBus = FakeEventBus()

    room = types.ModuleType(
        'gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room')
    room.StrongholdBattleRoom = FakeStrongholdBattleRoom
    _attach('gui.Scaleform.daapi.view.lobby.fortifications',
            'gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room',
            room)

    dps = types.ModuleType('gui.Scaleform.daapi.view.lobby.rally.rally_dps')
    dps.SortieCandidatesLegionariesDP = FakeSortieCandidatesLegionariesDP
    _attach('gui.Scaleform.daapi.view.lobby.rally',
            'gui.Scaleform.daapi.view.lobby.rally.rally_dps', dps)

    profile = types.ModuleType(
        'gui.Scaleform.daapi.view.lobby.profile.ProfileWindow')
    profile.ProfileWindow = FakeProfileWindow
    _attach('gui.Scaleform.daapi.view.lobby.profile',
            'gui.Scaleform.daapi.view.lobby.profile.ProfileWindow', profile)

    # room_sort.py: the client's translations of its sort orders.
    _package('gui.impl')
    # tank_button.py, which stands down without openwg_gameface.
    current_vehicle = types.ModuleType('CurrentVehicle')
    current_vehicle.g_currentVehicle = None
    sys.modules['CurrentVehicle'] = current_vehicle
    gen_utils = types.ModuleType('gui.impl.gen_utils')
    gen_utils.INVALID_RES_ID = -1
    _attach('gui.impl', 'gui.impl.gen_utils', gen_utils)
    for name in ('gui.impl.lobby', 'gui.impl.lobby.hangar', 'gui.impl.lobby.hangar.presenters', 'gui.impl.pub'):
        _attach(name.rsplit('.', 1)[0], name, _package(name))
    menu = types.ModuleType('gui.impl.lobby.hangar.presenters.vehicle_menu_presenter')
    menu.VehicleMenuPresenter = type('VehicleMenuPresenter', (object,), {})
    _attach('gui.impl.lobby.hangar.presenters', menu.__name__, menu)
    view_component = types.ModuleType('gui.impl.pub.view_component')
    view_component.ViewComponent = type('ViewComponent', (object,), {})
    _attach('gui.impl.pub', view_component.__name__, view_component)
    backport = types.ModuleType('gui.impl.backport')
    backport.text = lambda resource: 'client %s' % resource
    _attach('gui.impl', 'gui.impl.backport', backport)
    gen = types.ModuleType('gui.impl.gen')
    sort = type('Sort', (object,), dict(
        (name, staticmethod(lambda name=name: name))
        for name in ('byOrder', 'byVehicles', 'byStatus', 'byName')))
    gen.R = type('R', (object,), {'strings': type('Strings', (object,), {
        'prebattle': type('Prebattle', (object,), {
            'labels': type('Labels', (object,), {'sort': sort})})})})
    _attach('gui.impl', 'gui.impl.gen', gen)

    contacts = types.ModuleType(
        'messenger.gui.Scaleform.data.contacts_vo_converter')
    contacts.ContactConverter = FakeContactConverter
    _attach('messenger.gui.Scaleform.data',
            'messenger.gui.Scaleform.data.contacts_vo_converter', contacts)

    provider = types.ModuleType(
        'messenger.gui.Scaleform.data.contacts_data_provider')
    provider.ContactsDataProvider = FakeContactsDataProvider
    _attach('messenger.gui.Scaleform.data',
            'messenger.gui.Scaleform.data.contacts_data_provider', provider)

    skeleton = types.ModuleType('skeletons.gui.lobby_context')
    skeleton.ILobbyContext = type('ILobbyContext', (object,), {})
    _attach('skeletons.gui', 'skeletons.gui.lobby_context', skeleton)

    control = types.ModuleType('skeletons.gui.game_control')
    control.IBrowserController = type('IBrowserController', (object,), {})
    _attach('skeletons.gui', 'skeletons.gui.game_control', control)
    for interface in ('app_loader:IAppLoader', 'impl:IGuiLoader'):
        module_name, class_name = interface.split(':')
        module = types.ModuleType('skeletons.gui.' + module_name)
        setattr(module, class_name, type(class_name, (object,), {}))
        _attach('skeletons.gui', 'skeletons.gui.' + module_name, module)

    # Keyed by interface, because handing every caller the same object hides
    # a whole class of mistake: asking for the wrong service still "works".
    services = {
        skeleton.ILobbyContext: FakeLobbyContext(),
        control.IBrowserController: FakeBrowserController(),
    }
    dependency = types.ModuleType('helpers.dependency')
    dependency.instance = lambda interface: services[interface]
    _attach('helpers', 'helpers.dependency', dependency)

    return FakeVehicleInfoComponent

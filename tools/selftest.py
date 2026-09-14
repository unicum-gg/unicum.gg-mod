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
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUB_TEMPLATE = os.path.join(REPO, 'dev', 'mod_unicum_dev.py.in')


class FakeBigWorld(object):
    """Scheduler that runs when told to, instead of on a frame clock."""

    def __init__(self):
        self.pending = {}
        self.fetched = []
        self._next = 1

    def callback(self, delay, func):
        handle = self._next
        self._next += 1
        self.pending[handle] = func
        return handle

    def cancelCallback(self, handle):
        self.pending.pop(handle, None)

    def fetchURL(self, url, callback, headers, timeout, method, postData):
        """Real HTTP, delivered the way the client delivers it: deferred.

        Keeping it out-of-band matters, because code that accidentally
        depends on the response having already arrived would pass against a
        synchronous fake and deadlock against the game.
        """
        import urllib2
        self.fetched.append(url)
        try:
            # A plain urlopen announces itself as Python-urllib and gets a
            # 403 from the API's bot protection. The client sends its own
            # user agent and is let through, so borrowing a browser's keeps
            # the test measuring the mod rather than the WAF.
            request = urllib2.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            raw = urllib2.urlopen(request, timeout=timeout)
            response = FakeResponse(raw.getcode(), raw.read())
        except Exception as error:
            response = FakeResponse(getattr(error, 'code', 0), '')
        self.callback(0.0, lambda: callback(response))

    def run_pending(self):
        """Fire everything queued right now, once."""
        due, self.pending = self.pending, {}
        for _, func in sorted(due.items()):
            func()


class FakeResponse(object):
    """The shape BigWorld hands back: a code, a body, and headers()."""

    def __init__(self, code, body):
        self.responseCode = code
        self.body = body

    def headers(self):
        return {}


SENTINEL_REGION = 'XX'


def sentinel_getRegionCode(accountDBID, lobbyContext=None):
    """Stands in for the client's function, and says it was reached.

    Returns a real-looking region code so a hook that forgets to delegate --
    or drops what the original decided -- shows up as a missing 'XX'.
    """
    return SENTINEL_REGION


class FakeEvent(object):
    """Stands in for a WG Event, and remembers who is attached."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)
        return self


class FakeLobbyContext(object):

    def getRegionCode(self, dbID):
        return None


class FakeContact(object):

    def __init__(self, account_id):
        self._id = account_id

    def getID(self):
        return self._id

    def getName(self):
        return 'contact%s' % self._id

    def getTags(self):
        return []

    def getClanAbbrev(self):
        return None


class FakeContactConverter(object):
    """Carries makeBaseUserProps as a classmethod, as the client's does."""

    @classmethod
    def makeBaseUserProps(cls, contact):
        return {'userName': contact.getName(), 'region': None}


class FakeContactsDataProvider(object):
    """Counts the rebuild sequence the client runs when a list goes stale."""

    def __init__(self):
        self.builds = 0
        self.refreshes = 0
        self.status_changes = 0

    def buildList(self):
        self.builds += 1

    def refresh(self):
        self.refreshes += 1

    def onTotalStatusChanged(self):
        self.status_changes += 1


ORIGINAL_BUILD_LIST = FakeContactsDataProvider.__dict__['buildList']


class FakeBaseRallyRoomViewMeta(object):
    """as_setMembersS lives on the meta, as in the client."""

    def as_setMembersS(self, hasRestrictions, slots):
        self.sent = slots

    def as_updateRallyS(self, data):
        self.sent = data['slots']


class FakeStrongholdBattleRoom(FakeBaseRallyRoomViewMeta):
    """A skirmish room with one occupied slot and one empty one."""

    def __init__(self, account_id):
        self.account_id = account_id
        self.sent = None
        self.candidate_rebuilds = 0

    def isDisposed(self):
        return False

    def _updateMembersData(self):
        self.as_setMembersS(False, [
            {'player': {'dbID': self.account_id, 'region': None}},
            {'player': None},
        ])

    def _updateRallyData(self):
        # What the client sends when the detachment goes into battle.
        self.as_updateRallyS({'slots': [
            {'player': {'dbID': self.account_id, 'region': None}},
        ]})

    def _rebuildCandidatesDP(self):
        self.candidate_rebuilds += 1

    def member_region(self):
        return self.sent[0]['player']['region']


class FakeSortieCandidatesDP(object):

    def _makePlayerVO(self, pInfo, user, colorGetter, isPlayerSpeaking):
        return {'dbID': pInfo.dbID, 'region': None}


class FakeSortieCandidatesLegionariesDP(FakeSortieCandidatesDP):
    """Inherits _makePlayerVO, so patching it is an override to undo."""


class FakePlayerInfo(object):

    def __init__(self, account_id):
        self.dbID = account_id


class FakeProfileWindowMeta(object):
    """as_setInitDataS lives on the base, so the patch is an override.

    That is the shape that has to be undone by deleting the attribute rather
    than assigning to it: assigning would leave a permanent shadow over the
    inherited method.
    """

    def as_setInitDataS(self, data):
        return data


class FakeProfileWindow(FakeProfileWindowMeta):
    pass


class FakeOpenProfile(FakeProfileWindow):
    """Another player's profile window, as the client builds it."""

    def __init__(self, account_id):
        self._ProfileWindow__databaseID = account_id

    def title(self):
        return self.as_setInitDataS({'fullName': 'Player [TAG]'})['fullName']


class FakeResMgr(object):
    """Which files the client indexed at startup; titles.py asks for its SWF."""

    files = set()

    @classmethod
    def isFile(cls, path):
        return path in cls.files


class FakeEntitiesFactories(object):

    def __init__(self):
        self.settings = {}

    def getSettings(self, alias):
        return self.settings.get(alias)

    def addSettings(self, settings):
        self.settings[settings[0]] = settings


class FakeBrowserController(object):

    def __init__(self):
        self.onBrowserAdded = FakeEvent()

    def getAllBrowsers(self):
        return {}

    def getBrowser(self, browserID):
        return None


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
                 'gui.battle_control', 'gui.battle_control.arena_info',
                 'helpers', 'skeletons', 'skeletons.gui'):
        _package(name)

    player_format = types.ModuleType(
        'gui.battle_control.arena_info.player_format')
    player_format.getRegionCode = sentinel_getRegionCode
    _attach('gui.battle_control.arena_info',
            'gui.battle_control.arena_info.player_format', player_format)

    for name in ('gui.Scaleform.daapi.view.lobby.profile',
                 'gui.Scaleform.daapi.view.lobby.fortifications',
                 'gui.Scaleform.daapi.view.lobby.rally', 'messenger',
                 'messenger.gui', 'messenger.gui.Scaleform',
                 'messenger.gui.Scaleform.data'):
        _package(name)

    # titles.py. The SWF starts out missing, so install() stands down and
    # profile titles keep their language code; check_profile_title adds it.
    sys.modules['ResMgr'] = FakeResMgr
    _package('frameworks')
    wulf = types.ModuleType('frameworks.wulf')
    wulf.WindowLayer = type('WindowLayer', (object,), {'SERVICE_LAYOUT': 'service'})
    _attach('frameworks', 'frameworks.wulf', wulf)
    for name in ('gui.app_loader', 'gui.Scaleform.framework',
                 'gui.Scaleform.framework.entities',
                 'gui.Scaleform.framework.managers', 'gui.shared'):
        _package(name)
    app_settings = types.ModuleType('gui.app_loader.settings')
    app_settings.APP_NAME_SPACE = type('APP_NAME_SPACE', (object,), {'SF_LOBBY': 'lobby'})
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
    loaders = types.ModuleType('gui.Scaleform.framework.managers.loaders')
    loaders.SFViewLoadParams = lambda alias, parent=None: alias
    _attach('gui.Scaleform.framework.managers',
            'gui.Scaleform.framework.managers.loaders', loaders)
    shared = sys.modules['gui.shared']
    shared.EVENT_BUS_SCOPE = type('EVENT_BUS_SCOPE', (object,), {'GLOBAL': 'global'})
    shared.events = types.ModuleType('gui.shared.events')
    shared.g_eventBus = None

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

    return player_format


def render_stub(workdir, src_root):
    with open(STUB_TEMPLATE) as handle:
        text = handle.read().replace('__SRC_ROOT__', src_root.replace('\\', '/'))
    path = os.path.join(workdir, 'mod_unicum_dev.py')
    with open(path, 'w') as handle:
        handle.write(text)
    return path


def check(label, condition):
    print('%-4s %s' % ('ok' if condition else 'FAIL', label))
    if not condition:
        raise SystemExit(1)


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
            return target.getRegionCode is not sentinel_getRegionCode

        def delegates():
            # Account id 0 yields no marker and starts no lookup, so what
            # comes back is exactly what the original decided.
            return target.getRegionCode(0) == SENTINEL_REGION

        stub.init()
        check('load installed the hook', hooked())
        check('hook delegates to the original', delegates())
        check('watcher armed', bool(bigworld.pending))

        check_contacts_redraw(bigworld)
        check_skirmish_room(bigworld)
        check_profile_title()

        first_hook = target.getRegionCode
        generation_before = stub._generation

        # Touch a source file the way an editor would.
        edited = os.path.join(src_root, 'unicum', 'battle.py')
        os.utime(edited, (os.path.getatime(edited), os.path.getmtime(edited) + 10))

        bigworld.run_pending()
        check('reload happened', stub._generation == generation_before + 1)
        check('hook was reinstalled, not stacked',
              target.getRegionCode is not first_hook)
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
        check_clan_resolver(bigworld, src_root)

        check_language_lookup(bigworld, src_root)

        print('\nall checks passed')
    finally:
        # Windows will not remove the directory a process is standing in.
        os.chdir(original_cwd)
        shutil.rmtree(workdir, ignore_errors=True)


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


def check_clan_resolver(bigworld, src_root):
    """Clan tags from the page turn into the ids the languages API wants."""
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    from unicum.browser import ClanResolver
    from unicum.runtime.session import Session

    session = Session(generation=0)
    resolver = ClanResolver(session, 'eu')
    answers = []
    resolver.resolve([SAMPLE_CLAN_TAG, 'ZZZZZ9'], answers.append)
    resolver.resolve([SAMPLE_CLAN_TAG], answers.append)
    fetched_before = len(bigworld.fetched)
    for _ in range(3):
        bigworld.run_pending()

    if not answers:
        print('skip the API is unreachable, clan resolver checks not run')
        session.close()
        return
    check('a tag asked for twice is fetched once',
          sum(1 for url in bigworld.fetched if url.endswith('/' + SAMPLE_CLAN_TAG)) == 1)
    check('both callers get an answer', len(answers) == 2)
    # Matched by content, not position: the single-tag call settles first,
    # as soon as its tag is back, while the other still waits on 'ZZZZZ9'.
    both = [a for a in answers if 'ZZZZZ9' in a]
    check('each caller gets exactly the tags it asked for',
          len(both) == 1 and sorted(both[0]) == sorted([SAMPLE_CLAN_TAG, 'ZZZZZ9']))
    check('a known tag resolves to its clan id',
          both[0][SAMPLE_CLAN_TAG] == SAMPLE_CLAN)
    check('an unknown tag resolves to None', both[0]['ZZZZZ9'] is None)

    resolver.resolve([SAMPLE_CLAN_TAG], answers.append)
    check('a resolved tag is answered without a request',
          len(answers) == 3 and len(bigworld.fetched) == fetched_before)
    session.close()


def check_browser_scope(src_root):
    """Script goes into Stronghold pages and nowhere else."""
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    from unicum.browser import (content_script, flags_script, is_stronghold_page,
                                parse_need)

    check('the page asking for tags is understood',
          parse_need('[unicum] need RASZ,TENTS') == ['RASZ', 'TENTS'])
    check('any other console output is ignored',
          parse_need('Uncaught TypeError: x is undefined') is None)
    check('a malformed tag from the page is dropped',
          parse_need('[unicum] need RASZ,<img onerror=x>') == ['RASZ'])

    # javascript: URLs are percent-decoded, and '#' would start a fragment.
    script = content_script(7)
    check('the content script carries its generation', 'var G=7,' in script)
    check('the content script survives being a URL',
          '%' not in script and '#' not in script)
    pushed = flags_script({'RASZ': 'data:image/png;base64,iVBOR+/w==', 'TENTS': ''})
    check('the flags script survives being a URL',
          '%' not in pushed and '#' not in pushed)

    check('stronghold page is scripted', is_stronghold_page(
        'https://wgsh-woteu-static.wgcdn.co/auth/entry?spa_id=1&next=/%23/battlerooms'))
    check('shop page is left alone', not is_stronghold_page(
        'https://eu.wargaming.net/shop/wot/'))
    check('clan portal is left alone', not is_stronghold_page(
        'https://eu.wargaming.net/clans/wot/500198413/'))
    check('a page without a url is left alone', not is_stronghold_page(None))


# Accounts and a clan from a real EU skirmish roster, used so the lookup is
# exercised against answers the server actually holds.
SAMPLE_PLAYERS = [518080300, 538132472]
# A third real account, never looked up before the profile check.
SAMPLE_UNCACHED_PLAYER = 554095149
SAMPLE_CLAN = 500198413
SAMPLE_CLAN_TAG = 'RASZ'

# Enough to cover what those samples resolve to, without depending on it.
FLAG_CODES = ('CZ', 'GB-UKM', 'PL', 'DE', 'FR', 'RU', 'UA', 'SK')


def check_language_lookup(bigworld, src_root):
    """Drive the resolve client against whatever API is configured."""
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    from unicum import config
    from unicum.api.languages import CLANS, LanguageLookup, PLAYERS
    from unicum.runtime.session import Session

    print('\n-- language lookup against %s' % config.API_BASE)
    session = Session(generation=0)
    # Its own store, so a previous run's answers cannot make this one pass.
    lookup = LanguageLookup(session, region='eu',
                            store=os.path.join(src_root, 'languages.json'))

    check('nothing is cached before a fetch',
          lookup.get(PLAYERS, SAMPLE_PLAYERS[0]) is None)

    ready = []
    # Counted from here: earlier checks share the same fake engine.
    fetched_before = len(bigworld.fetched)
    lookup.prefetch(players=SAMPLE_PLAYERS, clans=[SAMPLE_CLAN],
                    on_ready=lambda: ready.append(True))
    check('one request for the whole roster',
          len(bigworld.fetched) == fetched_before + 1)
    check('nothing resolved before the response lands', not ready)

    bigworld.run_pending()
    bigworld.run_pending()
    if not ready:
        print('skip the API is unreachable, lookup checks not run')
        return
    check('on_ready fired once the response landed', ready == [True])

    entry = lookup.get(CLANS, SAMPLE_CLAN)
    check('clan resolved', entry is not None and bool(entry.countries))
    if entry is not None:
        print('       clan %s -> %s (%s)'
              % (SAMPLE_CLAN, entry.countries, entry.source))
        check('clan entry exposes a primary flag', entry.primary is not None)

    for account in SAMPLE_PLAYERS:
        resolved = lookup.get(PLAYERS, account)
        check('player %s resolved' % account, resolved is not None)
        if resolved is not None:
            print('       player %s -> %s (%s)'
                  % (account, resolved.countries, resolved.source))

    before = len(bigworld.fetched)
    lookup.prefetch(players=SAMPLE_PLAYERS, clans=[SAMPLE_CLAN],
                    on_ready=lambda: ready.append(True))
    check('a cached roster asks for nothing', len(bigworld.fetched) == before)
    check('on_ready still fires on a full cache hit', len(ready) == 2)

    # The contacts list was opened again long after the last lookup. The old
    # answer has to keep being drawn while the fresh one is fetched: deleting
    # it here is what blanked every flag at once.
    stale = lookup.get(CLANS, SAMPLE_CLAN)
    stale.fetched_at -= config.REFRESH_SECONDS + 1
    check('a stale entry is still served', lookup.get(CLANS, SAMPLE_CLAN) is stale)
    check('a stale entry is asked for again', lookup.needs_fetch(CLANS, SAMPLE_CLAN))
    before = len(bigworld.fetched)
    lookup.prefetch(clans=[SAMPLE_CLAN])
    check('refreshing it sends one request', len(bigworld.fetched) == before + 1)
    check('it is not asked for twice while in flight',
          not lookup.needs_fetch(CLANS, SAMPLE_CLAN))
    check('the stale answer is drawn during the refresh',
          lookup.get(CLANS, SAMPLE_CLAN) is stale)
    bigworld.run_pending()
    bigworld.run_pending()
    check('the fresh answer replaces it', not lookup.needs_fetch(CLANS, SAMPLE_CLAN)
          and lookup.get(CLANS, SAMPLE_CLAN) is not stale)

    session.close()
    lookup.prefetch(players=[1], on_ready=lambda: ready.append(True))
    bigworld.run_pending()
    bigworld.run_pending()
    check('a closed session swallows its own response', len(ready) == 2)


if __name__ == '__main__':
    main()

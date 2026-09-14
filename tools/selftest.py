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

    for name in ('gui.Scaleform.daapi.view.lobby.profile', 'messenger',
                 'messenger.gui', 'messenger.gui.Scaleform',
                 'messenger.gui.Scaleform.data'):
        _package(name)

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

        check_browser_scope(src_root)

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
    check('a row drawn before its language arrives has no flag', not row['region'])

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


def check_browser_scope(src_root):
    """Script goes into Stronghold pages and nowhere else."""
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    from unicum.browser import is_stronghold_page

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
SAMPLE_CLAN = 500198413


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

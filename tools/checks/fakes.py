"""Stand-ins for the client classes the mod patches."""

from checks.engine import FakeEvent


SENTINEL_REGION = 'XX'


class FakeVInfo(object):

    def __init__(self, account_id):
        self.player = type('Player', (object,), {'accountDBID': account_id})()


class FakeVehicleInfoComponent(object):
    """Stands in for the stats exchange's builder, and says it was reached.

    Writes a real-looking region code so a hook that forgets to delegate --
    or drops what the original decided -- shows up as a missing 'XX'.
    """

    def __init__(self):
        self._data = {}

    def get(self, forced=False):
        return self._data

    def addVehicleInfo(self, vInfoVO, overrides):
        self._data = {'accountDBID': vInfoVO.player.accountDBID,
                      'region': SENTINEL_REGION}


class Comp7VehicleInfoComponent(FakeVehicleInfoComponent):
    """Onslaught's builder: extends the base one through super()."""

    def addVehicleInfo(self, vInfoVO, overrides):
        super(Comp7VehicleInfoComponent, self).addVehicleInfo(vInfoVO, overrides)
        self._data.update({'role': 'assault'})


ORIGINAL_ADD_VEHICLE_INFO = FakeVehicleInfoComponent.__dict__['addVehicleInfo']


class FakeStatisticsController(object):
    """The battle's statistics controller, with one player on each side."""

    def __init__(self, ally, enemy):
        def vehicle(account_id, team):
            return type('VInfo', (object,), {
                'team': team, 'isObserver': lambda self: False,
                'player': type('Player', (object,), {'accountDBID': account_id})()})()
        vehicles = [vehicle(ally, 1), vehicle(enemy, 2)]
        arena = type('ArenaDP', (object,), {
            'getVehiclesInfoIterator': lambda self: iter(vehicles),
            'isAllyTeam': lambda self, team: team == 1})()
        self._battleCtx = type('BattleCtx', (object,), {'getArenaDP': lambda self: arena})()
        self.arena_info = None

    def as_setArenaInfoS(self, data):
        self.arena_info = data

    def invalidateArenaInfo(self):
        self.as_setArenaInfoS({'allyTeamName': 'DOUBT', 'enemyTeamName': 'SMTHG'})


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

    def _dispose(self):
        self.disposed = True

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
    """Which files the client indexed at startup; views.py asks for its SWFs."""

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

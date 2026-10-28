"""Checks for the loadouts the mod sends: what changes, and what is never sent twice."""

from checks.common import check


def check_loadouts():
    from unicum.loadouts.reading import fingerprint
    from unicum.loadouts.store import changed

    first = {'tankId': 7169, 'crew': [{'role': 'commander', 'skills': ['repair']}]}
    same = {'crew': [{'role': 'commander', 'skills': ['repair']}], 'tankId': 7169}
    other = {'tankId': 7169, 'crew': [{'role': 'commander', 'skills': ['brotherhood']}]}
    check('a loadout fingerprints the same whatever order its keys come in',
          fingerprint(first) == fingerprint(same))
    check('a changed skill changes the fingerprint', fingerprint(first) != fingerprint(other))

    # The shape `load_sent` hands out: a fingerprint and what was mounted.
    sent = {7169: {'f': fingerprint(first), 'd': set()}}
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


def check_loadout_store():
    """The file survives a mod that did not write it in this shape."""
    import json
    import os
    import tempfile
    from unicum.loadouts import store as loadouts

    folder = tempfile.mkdtemp()
    path = os.path.join(folder, 'loadouts.json')
    store, loadouts.STORE = loadouts.STORE, path
    try:
        check('no file means nothing was ever sent', loadouts.load_sent() == {})
        # Written by a build that kept fingerprints alone. Reading it must not
        # throw away the carousel: a vehicle is simply unprotected against a
        # demount until its next real change.
        with open(path, 'wb') as handle:
            json.dump({'sent': {'7169': 'oldfingerprint'}}, handle)
        old = loadouts.load_sent()
        check('a store from before the devices were kept is still read',
              old == {7169: {'f': 'oldfingerprint', 'd': None, 'c': None}})
        loadouts.save_sent({7169: {'f': 'abc', 'd': set(['rammer']), 'c': 5}})
        check('what a sweep saves comes back as it went in',
              loadouts.load_sent() == {7169: {'f': 'abc', 'd': set(['rammer']), 'c': 5}})
        # A network answer outlives the generation that sent it, so a reload
        # can hand the serialiser the shape the PREVIOUS build kept in memory.
        # Raising there runs inside a fetch callback: it loses the whole store
        # and reports an error the player can do nothing about. Seen live.
        loadouts.save_sent({7169: 'a bare fingerprint from before the reload'})
        back = loadouts.load_sent()
        check('a store handed the shape an older generation held is still written',
              back[7169]['f'] == 'a bare fingerprint from before the reload')
        # What matters is not which empty it round-trips to but what that
        # empty means: nothing is known about the devices, so nothing is
        # protected, and the vehicle is recorded again on its next change.
        check('and the vehicle it names is simply unprotected until it changes',
              not loadouts.demounted(_with_devices(7169, ['rammer']), back[7169]))
        check('unprotected against a crew that left, too',
              not loadouts.uncrewed({'tankId': 7169, 'crew': []}, back[7169]))

        # A withdrawal has to survive both a failed request and a closed game,
        # so it lives in the same file and must not be written over by the
        # fingerprints, nor they by it.
        check('nothing is owed to a player who never asked', not loadouts.load_withdraw())
        loadouts.save_withdraw(True)
        check('an unticked box is remembered', loadouts.load_withdraw())
        loadouts.save_sent({7169: {'f': 'abc', 'd': set(), 'c': 5}})
        check('and survives a sweep saving over the same file', loadouts.load_withdraw())
        loadouts.save_withdraw(False)
        check('until the server confirms it', not loadouts.load_withdraw())
        check('which leaves the fingerprints alone',
              loadouts.load_sent() == {7169: {'f': 'abc', 'd': set(), 'c': 5}})
    finally:
        loadouts.STORE = store


def _with_devices(tank, names, extra=None):
    """A record carrying these optional devices in its active setup."""
    record = {
        'tankId': tank,
        'setups': {'devices': {'active': 0, 'layouts': [{'optDevices': list(names),
                                                         'boosters': []}]}},
    }
    if extra:
        record.update(extra)
    return record


def check_demounting():
    """A vehicle stripped to equip another must not lose its build on the page."""
    from unicum.loadouts.reading import fingerprint, mounted
    from unicum.loadouts.store import changed

    full = _with_devices(7169, ['rammer', 'vents', 'stabilizer'])
    stripped = _with_devices(7169, ['rammer', 'vents', None])
    swapped = _with_devices(7169, ['rammer', 'vents', 'optics'])
    emptied = _with_devices(7169, [None, None, None])

    check('the devices of a setup are read off the active layout',
          mounted(full) == set(['rammer', 'vents', 'stabilizer']))
    check('an empty slot is not a device', mounted(stripped) == set(['rammer', 'vents']))

    sent = {7169: {'f': fingerprint(full), 'd': mounted(full)}}
    check('a vehicle stripped of one device keeps the build it was played with',
          changed([stripped], sent, set([7169])) == [])
    check('a vehicle stripped bare keeps it too',
          changed([emptied], sent, set([7169])) == [])
    # The point of the subset test: taking away is refused, replacing is not.
    check('swapping one device for another is a decision, and is recorded',
          [r['tankId'] for r in changed([swapped], sent, set([7169]))] == [7169])
    check('adding a device is recorded',
          [r['tankId'] for r in changed(
              [_with_devices(7169, ['rammer', 'vents', 'stabilizer', 'turbo'])],
              sent, set([7169]))] == [7169])

    # A store written before the devices were kept: nothing to compare against,
    # so nothing is protected and the change goes through rather than sticking.
    old = {7169: {'f': 'whatever', 'd': None}}
    check('a vehicle we know nothing about the devices of is still sent',
          [r['tankId'] for r in changed([stripped], old, set([7169]))] == [7169])


def _with_crew(tank, count, skill='repair'):
    """A record whose crew has this many members."""
    return {'tankId': tank,
            'crew': [{'role': 'commander', 'skills': [skill]} for _ in range(count)]}


class _Tankman(object):
    """Just enough of a tankman for the reader: a role, perks, and whether he is gone."""

    def __init__(self, role, skills, dismissed=False):
        self.role = role
        self.skills = [type('S', (object,), {'name': name})() for name in skills]
        self.bonusSkills = {}
        self.isDismissed = dismissed


class _CrewVehicle(object):
    """A vehicle with some seats filled and a crew that last fought it."""

    def __init__(self, roles, seated, last=None):
        self.crew = list(enumerate(seated))
        self.lastCrew = list(range(len(last or ())))
        self.descriptor = type('D', (object,), {
            'type': type('T', (object,), {'crewRoles': roles})()})()
        self._last = list(last or ())

    def cache(self):
        """The inventory `_returning` looks the last crew up in."""
        holder = self._last
        return type('I', (object,), {
            'getTankman': staticmethod(
                lambda invID: holder[invID] if invID < len(holder) else None)})()


def check_crew_from_last_battle():
    """A crew off driving another vehicle still describes the one it left."""
    from unicum.loadouts.reading import _crew

    roles = (('commander',), ('gunner',), ('driver',))
    away = [_Tankman('commander', ['brotherhood']),
            _Tankman('gunner', ['deadeye']),
            _Tankman('driver', ['smooth_driving'])]

    seated = _CrewVehicle(roles, [_Tankman('commander', ['repair']), None, None], away)
    read = _crew(seated, seated.cache())
    check('whoever is actually sitting there wins over the last crew',
          read[0] == {'role': 'commander', 'skills': ['repair']})
    check('and the empty seats are filled from the crew that last fought it',
          [member['skills'] for member in read[1:]] == [['deadeye'], ['smooth_driving']])

    # The case the player described: the whole crew is in another vehicle.
    empty = _CrewVehicle(roles, [None, None, None], away)
    check('a vehicle whose whole crew left is read as it is played',
          [member['role'] for member in _crew(empty, empty.cache())]
          == ['commander', 'gunner', 'driver'])

    # A crew the player disbanded is genuinely absent, and saying so is the point.
    dismissed = _CrewVehicle(roles, [None, None, None],
                             [_Tankman('commander', ['brotherhood'], dismissed=True)])
    check('a dismissed crew is not brought back', _crew(dismissed, dismissed.cache()) == [])

    # Nothing to return from: the vehicle has never been to battle.
    fresh = _CrewVehicle(roles, [None, None, None])
    check('and a vehicle that never fought has no last crew to read',
          _crew(fresh, fresh.cache()) == [])


def check_crew_away():
    """One crew driving several vehicles must not empty the ones it left."""
    from unicum.loadouts.reading import crewed, fingerprint
    from unicum.loadouts.store import changed, uncrewed

    full = _with_crew(7169, 5)
    gone = _with_crew(7169, 0)
    partial = _with_crew(7169, 2)
    retrained = _with_crew(7169, 5, skill='brotherhood')

    check('a record knows how many seats it has somebody in', crewed(full) == 5)
    check('and an absent crew is none of them', crewed(gone) == 0)

    sent = {7169: {'f': fingerprint(full), 'd': None, 'c': crewed(full)}}
    check('a vehicle whose crew went to drive another keeps the one it is played with',
          changed([gone], sent, set([7169])) == [])
    check('so does one the crew only partly left',
          changed([partial], sent, set([7169])) == [])
    # The point of the count: losing members is refused, changing them is not.
    check('a crew taught different perks is a decision, and is recorded',
          [r['tankId'] for r in changed([retrained], sent, set([7169]))] == [7169])
    check('so is a seat that was empty and is now filled',
          [r['tankId'] for r in changed([_with_crew(7169, 6)], sent, set([7169]))] == [7169])
    check('and the rule says nothing about a vehicle we never recorded a crew for',
          not uncrewed(gone, {'f': 'whatever', 'd': None, 'c': None}))


class _Recorder(object):
    """A session that writes down what was asked of it and answers on command.

    Deliberately not the fake client's own session: that one performs real
    HTTP, and the request under test here deletes a player's rows.
    """

    def __init__(self):
        self.calls = []
        self.answer = None

    def callback(self, delay, func):
        func()

    def subscribe(self, *args):
        pass

    def fetch(self, url, callback, headers=None, timeout=10.0, method='GET', post_data=''):
        self.calls.append((url, method))
        if self.answer is not None:
            callback(self.answer)


class _Switch(object):
    """Settings reduced to the one box this is about."""

    def __init__(self, on=True):
        self.on = on
        self.listeners = []

    def sends_loadouts(self):
        return self.on

    def on_change(self, listener):
        self.listeners.append(listener)

    def set(self, on):
        self.on = on
        for listener in self.listeners:
            listener()


def check_withdrawal():
    """Unticking the box has to take the player off the site, not freeze them there."""
    import os
    import tempfile
    from unicum.loadouts import store as loadouts
    from unicum.loadouts.uploader import Uploader

    folder = tempfile.mkdtemp()
    store, loadouts.STORE = loadouts.STORE, os.path.join(folder, 'loadouts.json')
    try:
        session, switch = _Recorder(), _Switch(on=True)
        link = type('L', (object,), {'secret': 'a-linked-client'})()
        uploader = Uploader(session, switch, link)
        uploader._sent = {7169: {'f': 'abc', 'd': set(), 'c': 5}}
        loadouts.save_sent(uploader._sent)

        switch.set(True)
        check('a setting that did not change asks for nothing', session.calls == [])

        # Refused: the rows are still published, so the ask must survive.
        session.answer = type('R', (object,), {'responseCode': 502, 'body': ''})()
        switch.set(False)
        check('unticking the box asks the server to forget the account',
              len(session.calls) == 1 and session.calls[0][1] == 'DELETE')
        check('and it is the loadouts endpoint it asks',
              session.calls[0][0].endswith('/api/game/loadouts'))
        check('a refusal leaves the withdrawal owed', loadouts.load_withdraw())
        check('and leaves the fingerprints alone, so nothing is silently re-sent',
              loadouts.load_sent() != {})

        # The retry, as a new garage would make it, and this time it lands.
        session.answer = type('R', (object,), {'responseCode': 200, 'body': '{}'})()
        uploader._withdraw()
        check('a confirmed withdrawal is no longer owed', not loadouts.load_withdraw())
        check('and the fingerprints go with it', loadouts.load_sent() == {})
        check('so that re-ticking the box uploads the carousel afresh',
              uploader._sent == {} and uploader._held is None)

        # Ticking it back on is not a second withdrawal.
        before = len(session.calls)
        switch.set(True)
        check('ticking the box back on asks the server for nothing',
              len(session.calls) == before)
    finally:
        loadouts.STORE = store


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


class _Vehicle(object):
    """A garage vehicle, as `fleet_garage` reads one."""

    def __init__(self, intCD, **flags):
        self.intCD = intCD
        for name, value in flags.items():
            setattr(self, name, value)


class _Items(object):
    """The client's item cache, holding one inventory."""

    def __init__(self, vehicles):
        self._vehicles = vehicles

    def getVehicles(self, criteria=None):
        return dict((vehicle.intCD, vehicle) for vehicle in self._vehicles)


def check_garage_statement():
    """The inventory as a statement: what counts as owned, and when it is sent.

    This exists because Wargaming cannot answer the question at all. A vehicle
    bought and never taken into a battle has no stats record, so it has no row
    in `wot/tanks/stats` and no token makes one appear. Measured on one
    account: 80 vehicles out of about 206, and they are the collection pieces.
    The client knows them and nothing else does.
    """
    import os
    import tempfile
    from unicum.loadouts import store as loadouts
    from unicum.loadouts.reading import fleet_garage

    held = _Vehicle(7169)
    rented = _Vehicle(7170, isRented=True)
    event = _Vehicle(1311569, isOnlyForEventBattles=True)
    hunter = _Vehicle(1331969, isOnlyForBattleRoyaleBattles=True)
    training = _Vehicle(1343521, isOnlyForMapsTrainingBattles=True)
    globalmap = _Vehicle(1344081, isOnlyForClanWarsBattles=True)
    observer = _Vehicle(1345089, isObserver=True)

    garage = fleet_garage(_Items([held, rented, event, hunter, training,
                                  globalmap, observer]))
    check('only what the player really owns is stated', garage == [7169])

    # Frontline is played in the player's own tier 8 vehicles, so the flag
    # marks a mode a vehicle may enter, not a vehicle the mode lent out. A
    # rented one is caught by `isRented` instead.
    epic = _Vehicle(7171, isOnlyForEpicBattles=True)
    check('a vehicle merely allowed into a mode is still owned',
          fleet_garage(_Items([epic])) == [7171])

    # A property that raises is a client change, not an answer: the vehicle is
    # kept, because this list decides what to leave OUT and a failure here
    # must never silently empty a garage.
    class _Broken(object):
        intCD = 7172

        @property
        def isRented(self):
            raise RuntimeError('a client patch moved this')

    check('a flag that cannot be read keeps the vehicle',
          fleet_garage(_Items([_Broken()])) == [7172])
    check('sorted, so the same garage hashes the same',
          fleet_garage(_Items([_Vehicle(99), _Vehicle(7), _Vehicle(50)]))
          == [7, 50, 99])

    folder = tempfile.mkdtemp()
    store, loadouts.STORE = loadouts.STORE, os.path.join(folder, 'loadouts.json')
    try:
        check('nothing has been accepted yet', loadouts.load_garage_hash() is None)
        loadouts.save_garage_hash(loadouts.garage_hash([7169, 7170]))
        check('an unchanged garage costs no request',
              loadouts.garage_hash([7169, 7170]) == loadouts.load_garage_hash())
        check('and the order it is read in does not make it changed',
              loadouts.garage_hash([7170, 7169]) == loadouts.load_garage_hash())
        check('a purchase makes it worth sending',
              loadouts.garage_hash([7169, 7170, 7171]) != loadouts.load_garage_hash())
        check('a sale too',
              loadouts.garage_hash([7169]) != loadouts.load_garage_hash())
    finally:
        loadouts.STORE = store

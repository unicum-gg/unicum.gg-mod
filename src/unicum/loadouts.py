"""How the player has set their vehicles up, sent to unicum.gg.

Wargaming publishes none of this about anyone: their API answers battles and
damage, never the equipment on a gun or the perks a commander trained. So a
loadout on a player's page exists only because that player runs this mod, and
this module is the whole of that path.

What it sends, and what proves it
---------------------------------
Only ever this account's own vehicles, and the account is PROVEN rather than
claimed. The client can mint a WGNI web token, the one the game uses for its
own shop and portal, without asking the player anything; unicum.gg hands it to
Wargaming, which answers with the account id it is bound to. A nickname in the
body would be a claim, and the value of a published loadout rests entirely on
nobody being able to invent builds under a good player's name.

Why it sends so little
----------------------
A full carousel is a few hundred vehicles and about a quarter of a megabyte,
of which almost nothing moves between two garage visits. So the mod keeps a
fingerprint per vehicle and sends only what changed, reconciled against what
the server says it already holds, which makes the steady state nearly free and
leaves the whole payload for the first upload alone.

Measured on a 209-vehicle garage: 0.15 seconds of client time to read the lot,
1231 bytes a vehicle. The reading is not the cost here, the sending is.

The garage only
---------------
Reading a vehicle costs nothing but it is still work, and none of it is urgent.
It runs a moment after the garage is up, never in battle, never while the
client is starting.
"""
import hashlib
import json
import logging
import os
import time

from unicum import config

_logger = logging.getLogger('unicum.loadouts')

# Vehicles per pass, so a sweep never holds the frame the garage is drawn on.
_CHUNK = 25
_CHUNK_PAUSE = 0.1

# Vehicles per request. The endpoint accepts far more, but a request carrying
# a whole carousel is a quarter of a megabyte on a connection we know nothing
# about, and a failure throws all of it away rather than a fifth of it.
_BATCH = 50

# How long after the garage appears the sweep starts, and the least time
# between two of them. A player who keeps stepping in and out of the garage
# must not upload on every step.
_START_DELAY = 8.0
_MIN_INTERVAL = 900.0

# Which fingerprints were last accepted, so a second sweep sends nothing.
STORE = os.path.join('mods', 'configs', 'unicum', 'loadouts.json')

# Two setup groups, from the client's own post_progression_common: shells
# travel with consumables, optional devices with directives. Each has its own
# active index and at most two layouts.
_AMMO = 1
_DEVICES = 2


def _names(items):
    return [item.name if item is not None else None for item in items]


def _shells(collection):
    """Every shell of one setup, with how many the player loads."""
    shells = []
    for shell in collection:
        if shell is None:
            continue
        shells.append({
            # intCD as the key: a shell's name is scoped to its nation and two
            # nations can hold the same one. The name rides along as a label.
            'id': shell.intCD,
            'name': shell.name,
            # What an aggregate actually asks of this: how much gold does the
            # player carry. Derivable from the gun, but the client has it here.
            'type': shell.type,
            'premium': bool(shell.isPremium),
            'count': shell.count,
        })
    return shells


def _setup_group(vehicle, group):
    """{'active': index, 'layouts': [...]} for one of the client's two groups."""
    if group == _AMMO:
        first, second = vehicle.shells, vehicle.consumables
        keys = ('shells', 'consumables')
    else:
        first, second = vehicle.optDevices, vehicle.battleBoosters
        keys = ('optDevices', 'boosters')
    layouts = []
    for index in sorted(first.setupLayouts.setups):
        layouts.append({
            keys[0]: (_shells(first.setupLayouts.setupByIndex(index) or ())
                      if group == _AMMO else
                      _names(first.setupLayouts.setupByIndex(index) or ())),
            keys[1]: _names(second.setupLayouts.setupByIndex(index) or ()),
        })
    return {'active': first.setupLayouts.layoutIndex, 'layouts': layouts}


def _crew(vehicle):
    """Skills per crew member, in the site's member order. Skills only.

    Nothing else about the member: a level and a training percentage describe
    the tankman rather than the build, and a column nobody reads is a column
    that still has to be kept true.
    """
    from unicum.build import crew_member_indexes
    indexes = crew_member_indexes(vehicle.descriptor.type.crewRoles)
    members = {}
    for slot, tankman in vehicle.crew:
        if tankman is None or slot not in indexes:
            continue
        skills = [skill.name for skill in tankman.skills]
        for bonus in tankman.bonusSkills.values():
            skills.extend(skill.name for skill in bonus if skill is not None)
        members[indexes[slot]] = {
            'role': vehicle.descriptor.type.crewRoles[slot][0],
            'skills': skills,
        }
    return [members[key] for key in sorted(members)]


def _progression(vehicle):
    """Field modifications, or the skill tree a tier XI vehicle has instead."""
    from unicum.build import _PAIR_SIDES
    progression = vehicle.postProgression
    if progression is None or not progression.isExists():
        return None
    steps = [step for step in progression.iterUnorderedSteps() if step.isReceived()]
    if not steps:
        return None
    if progression.isVehSkillTree():
        return {'tree': sorted(step.stepID for step in steps)}
    pairs = []
    for step in steps:
        action = step.action
        if action.isMultiAction() and action.isPurchased():
            side = _PAIR_SIDES.get(action.getPurchasedIdx())
            if side:
                pairs.append({'name': action.getTechName(), 'side': side})
    return {'level': max(step.getLevel() for step in steps), 'pairs': pairs}


def _modules(vehicle):
    parts = {'gun': vehicle.gun, 'engine': vehicle.engine,
             'chassis': vehicle.chassis, 'radio': vehicle.radio}
    if vehicle.hasTurrets:
        parts['turret'] = vehicle.turret
    return dict((key, {'id': item.intCD, 'name': item.name})
                for key, item in parts.items() if item is not None)


def loadout(vehicle):
    """One vehicle's whole setup, in the shape unicum.gg stores."""
    return {
        'tankId': vehicle.intCD,
        'modules': _modules(vehicle),
        'crew': _crew(vehicle),
        'progression': _progression(vehicle),
        'setups': {
            'ammo': _setup_group(vehicle, _AMMO),
            'devices': _setup_group(vehicle, _DEVICES),
        },
    }


def fingerprint(record):
    """What identifies this loadout, so an unchanged one is never sent twice."""
    return hashlib.md5(json.dumps(record, sort_keys=True)).hexdigest()


def load_sent():
    """{tank id: fingerprint} last accepted by the server, empty if unusable."""
    if not os.path.isfile(STORE):
        return {}
    try:
        with open(STORE, 'rb') as handle:
            stored = json.load(handle)
    except (IOError, ValueError):
        _logger.warning('could not read %s, sending everything', STORE)
        return {}
    sent = stored.get('sent') if isinstance(stored, dict) else None
    return dict((int(key), value) for key, value in sent.items()) if isinstance(sent, dict) else {}


def save_sent(sent):
    try:
        directory = os.path.dirname(STORE)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(STORE, 'wb') as handle:
            json.dump({'sent': sent}, handle)
    except (IOError, OSError):
        _logger.warning('could not write %s; the next sweep sends again', STORE, exc_info=True)


def _keep_rejected(code, batch):
    """Leave a refused batch on disk, beside the fingerprints.

    Kept rather than removed once it had done its job. The shape of a loadout
    is a contract between this mod, a game client nobody here controls and a
    server in another repository, and the two bugs it has already found were
    both a vehicle the schema had not imagined: one with nothing to say about
    its post progression, and one whose main armament is a machine gun
    carrying 2700 rounds. Neither was visible from the log, and neither could
    be reproduced without the batch that carried it.

    Only what the server refused outright, never a network failure, and always
    the same file: this is a diagnosis, not a history.
    """
    if not (400 <= (code or 0) < 500):
        return
    try:
        with open(os.path.join('mods', 'configs', 'unicum', 'loadouts-rejected.json'), 'wb') as handle:
            json.dump(batch, handle)
    except (IOError, OSError):
        _logger.debug('could not write the refused batch down', exc_info=True)


def changed(records, sent, held):
    """The records worth sending: new, altered, or absent from the server.

    `held` is what the server says it already has. A fingerprint alone is not
    enough to decide: this file survives a reinstall of the site's database,
    and a vehicle we believe we sent but that the server does not hold would
    otherwise never be sent again.
    """
    out = []
    for record in records:
        tank = record['tankId']
        if sent.get(tank) != fingerprint(record) or (held is not None and tank not in held):
            out.append(record)
    return out


class Uploader(object):
    """Reads the carousel when the garage appears, and sends what changed.

    One object for the whole path, because the three halves only make sense
    together: a sweep that does not know what was already sent would upload a
    quarter of a megabyte on every garage entry, and a sender that does not
    know when the sweep finished would send half a carousel.
    """

    def __init__(self, session, settings, link):
        self._session = session
        self._settings = settings
        self._link = link
        self._sent = load_sent()
        # What the server says it holds, read once a session before the first
        # upload. None until then, which `changed` reads as "do not second
        # guess the fingerprints".
        self._held = None
        self._last_sweep = 0.0
        self._busy = False

    def install(self):
        try:
            from PlayerEvents import g_playerEvents
            self._session.subscribe(g_playerEvents.onAccountShowGUI, self._on_garage)
        except ImportError:
            _logger.exception('no player events; loadouts are never swept')
            return
        # The garage may already be up: the event fires when it appears, and
        # a mod installed after that would otherwise say nothing until the
        # player next came back from a battle. `sweep` refuses anywhere else,
        # so this costs nothing while the client is still starting, which is
        # when it normally runs.
        self._session.callback(_START_DELAY, self.sweep)
        _logger.info('installed')

    def _on_garage(self, *args):
        # Not on the spot: the garage has a sign-in, a carousel and every
        # other feature of this mod to draw first, and none of this is urgent.
        self._session.callback(_START_DELAY, self.sweep)

    def sweep(self):
        """Read every owned vehicle, then send what the server does not have."""
        if self._busy or not self._wanted():
            return
        now = time.time()
        if now - self._last_sweep < _MIN_INTERVAL:
            return
        vehicles = self._vehicles()
        if not vehicles:
            return
        self._busy = True
        self._last_sweep = now
        _Sweep(self, vehicles).step()

    def _wanted(self):
        """Whether the player is at the garage and has not turned this off."""
        try:
            from helpers import isPlayerAccount
            if not isPlayerAccount():
                return False
        except ImportError:
            return False
        try:
            return self._settings.sends_loadouts()
        except Exception:
            _logger.exception('could not read the loadout setting')
            return False

    @staticmethod
    def _vehicles():
        try:
            from gui.shared.utils.requesters import REQ_CRITERIA
            from helpers import dependency
            from skeletons.gui.shared import IItemsCache
            items = dependency.instance(IItemsCache).items
            return list(items.getVehicles(REQ_CRITERIA.INVENTORY).values())
        except Exception:
            _logger.exception('could not list the vehicles')
            return []

    def later(self, delay, func):
        """Schedule the sweep's next chunk on this session's own clock."""
        self._session.callback(delay, func)

    def swept(self, records):
        """Every vehicle read. Reconcile with the server, then send."""
        if self._held is None:
            self._read_held(lambda: self._send(records))
        else:
            self._send(records)

    def _send(self, records):
        pending = changed(records, self._sent, self._held)
        # A vehicle the player parted with: we hold a fingerprint for it and
        # it is no longer in the carousel.
        owned = set(record['tankId'] for record in records)
        sold = [tank for tank in self._sent if tank not in owned]
        if not pending and not sold:
            self._busy = False
            _logger.info('nothing to send: %d vehicles, all of them unchanged', len(records))
            return
        _logger.info('sending %d of %d vehicles, and %d sold', len(pending), len(records), len(sold))
        self._post(pending, sold)

    def _post(self, pending, sold, at=0):
        """One batch, then the next. Stops at the first failure."""
        batch = pending[at:at + _BATCH]
        if not batch and (at > 0 or not sold):
            self._busy = False
            save_sent(self._sent)
            return
        body = json.dumps({'loadouts': batch, 'sold': sold if at == 0 else []})

        def answered(response):
            code = getattr(response, 'responseCode', None)
            if code != 200:
                # Stop rather than push on: a quota answer (429) means the
                # rest of the batches would be refused too, and any other
                # failure is as likely to hit them. What was accepted is
                # remembered, so the next sweep carries on where this left.
                self._busy = False
                save_sent(self._sent)
                _logger.warning('loadout upload stopped on HTTP %s after %d vehicle(s)', code, at)
                _keep_rejected(code, batch)
                return
            for record in batch:
                self._sent[record['tankId']] = fingerprint(record)
            if at == 0:
                for tank in sold:
                    self._sent.pop(tank, None)
            self._post(pending, sold, at + _BATCH)

        self._request('%s/api/game/loadouts' % config.API_BASE.rstrip('/'), answered,
                      method='POST', post_data=body)

    def _read_held(self, then):
        """What the server already holds, so a lost database is refilled."""

        def answered(response):
            payload = None
            if getattr(response, 'responseCode', None) == 200:
                try:
                    payload = json.loads(response.body)
                except (TypeError, ValueError):
                    payload = None
            tanks = payload.get('tanks') if isinstance(payload, dict) else None
            self._held = set(int(key) for key in tanks) if isinstance(tanks, dict) else set()
            then()

        self._request('%s/api/game/loadouts' % config.API_BASE.rstrip('/'), answered)

    def _request(self, url, answered, method='GET', post_data=''):
        """Signed with whatever proves this account, and nothing if neither does.

        The link's secret when the player has one, because it costs the server
        no call to Wargaming. Otherwise the client's own WGNI web token, which
        the game mints without asking the player anything and which unicum.gg
        has Wargaming confirm. Either way the account is proven rather than
        claimed: a nickname in the body would let anyone publish a loadout
        under somebody else's name, and the whole value of this rests on that
        being impossible.
        """
        secret = getattr(self._link, 'secret', None)
        if secret:
            self._fetch(url, answered, {'Authorization': 'Bearer %s' % secret},
                        method, post_data)
            return

        def with_token(response):
            if not (response and response.isValid()):
                _logger.info('no web token; loadouts wait for the next garage')
                self._busy = False
                return
            self._fetch(url, answered, {
                'X-Wargaming-Token': str(response.getToken()),
                'X-Wargaming-Region': config.REGION,
            }, method, post_data)

        try:
            from constants import TOKEN_TYPE
            from gui.shared.utils.requesters import getTokenRequester
            requester = getTokenRequester(TOKEN_TYPE.WGNI)
            if requester.isInProcess():
                self._busy = False
                return
            requester.request(timeout=10.0)(with_token)
        except Exception:
            _logger.exception('could not ask for a web token')
            self._busy = False

    def _fetch(self, url, answered, headers, method, post_data):
        headers = dict(headers)
        headers['Content-Type'] = 'application/json'
        self._session.fetch(url, answered, headers=headers,
                            timeout=config.API_TIMEOUT, method=method,
                            post_data=post_data)


class _Sweep(object):
    """One pass over the carousel, a chunk at a time.

    Chunked because the client draws the garage on the thread this runs on.
    A few hundred vehicles is 0.15 seconds of work measured end to end, which
    is not much and is still a dropped frame if it lands in one go.
    """

    def __init__(self, uploader, vehicles):
        self._uploader = uploader
        self._left = vehicles
        self._records = []

    def step(self):
        chunk, self._left = self._left[:_CHUNK], self._left[_CHUNK:]
        for vehicle in chunk:
            try:
                self._records.append(loadout(vehicle))
            except Exception:
                # One unreadable vehicle is not worth losing the carousel
                # over, and a client patch is exactly how one appears.
                _logger.exception('could not read the loadout of %s',
                                  getattr(vehicle, 'name', '?'))
        if self._left:
            self._uploader.later(_CHUNK_PAUSE, self.step)
        else:
            self._uploader.swept(self._records)


def install(session, settings, link):
    uploader = Uploader(session, settings, link)
    uploader.install()
    return uploader

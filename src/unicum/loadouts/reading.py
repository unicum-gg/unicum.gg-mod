"""What one vehicle is, read out of the client's own item cache.

Pure reading: an item in, a dict out. The shapes here are the part that keeps
breaking when Wargaming moves something, so each reader says what it looked
for and what it does when that is missing, and none of them raise: a vehicle
whose crew cannot be read still goes up with its modules.
"""
from __future__ import absolute_import

import hashlib
import json
import logging

from unicum import build

_logger = logging.getLogger('unicum.loadouts.reading')

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

def _skills(tankman):
    """Every perk this tankman carries, taught or granted."""
    names = [skill.name for skill in tankman.skills]
    for bonus in tankman.bonusSkills.values():
        names.extend(skill.name for skill in bonus if skill is not None)
    return names

def _returning(vehicle, items=None):
    """{role: [skills, ...]} of the crew that last FOUGHT this vehicle.

    A player runs one crew across several vehicles: the commander comes off
    the IS-7 to drive the Leopard, and the IS-7 sits there with empty seats.
    Those seats are not how the IS-7 is played, and reading them as an absent
    crew is the crew half of the demount problem.

    The client already keeps the answer. `vehicle.lastCrew` holds the
    inventory ids of the crew that took this vehicle into battle last: it is
    what the garage's own "return crew" button and its auto-return read, and
    the game offers neither until the vehicle has fought, so the list means
    "last used" rather than "last mounted". A tankman sitting in another
    vehicle still resolves out of the inventory, so his perks are readable
    from here even while he is away.

    Grouped by role rather than by seat because `lastCrew` carries no slot
    index, and a role names a seat well enough: a second loader is a loader.
    """
    last = getattr(vehicle, 'lastCrew', None)
    if not last:
        return {}
    if items is None:
        items = inventory()
    if items is None:
        return {}
    waiting = {}
    for invID in last:
        tankman = items.getTankman(invID)
        # Dismissed, or gone from the inventory altogether: a crew the player
        # disbanded is genuinely absent, and saying so is the point.
        if tankman is None or tankman.isDismissed:
            continue
        waiting.setdefault(tankman.role, []).append(_skills(tankman))
    return waiting

def _crew(vehicle, items=None):
    """Skills per crew member, in the site's member order. Skills only.

    Nothing else about the member: a level and a training percentage describe
    the tankman rather than the build, and a column nobody reads is a column
    that still has to be kept true.

    An empty seat is filled from `_returning`, so a vehicle whose crew is off
    driving another one shows the crew it is played with rather than nothing.
    """
    from unicum.build import crew_member_indexes
    roles = vehicle.descriptor.type.crewRoles
    indexes = crew_member_indexes(roles)
    members = {}
    empty = []
    for slot, tankman in vehicle.crew:
        if slot not in indexes:
            continue
        if tankman is None:
            empty.append(slot)
            continue
        members[indexes[slot]] = {'role': roles[slot][0], 'skills': _skills(tankman)}
    if empty:
        # Whoever is actually sitting there wins: a crew put in since the last
        # battle is the current build, and `lastCrew` is then out of date.
        waiting = _returning(vehicle, items)
        for slot in empty:
            role = roles[slot][0]
            away = waiting.get(role)
            if away:
                members[indexes[slot]] = {'role': role, 'skills': away.pop(0)}
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

def inventory():
    """The client's item cache, or None.

    Resolved once for a whole sweep and handed down, rather than looked up
    per vehicle: a carousel is a few hundred vehicles and this runs on the
    thread that draws the garage, so a service lookup in that loop is a few
    hundred lookups nobody asked for.
    """
    try:
        from helpers import dependency
        from skeletons.gui.shared import IItemsCache
        return dependency.instance(IItemsCache).items
    except Exception:
        _logger.exception('could not reach the inventory')
        return None

def loadout(vehicle, items=None):
    """One vehicle's whole setup, in the shape unicum.gg stores."""
    record = {
        'tankId': vehicle.intCD,
        'modules': _modules(vehicle),
        'crew': _crew(vehicle, items),
        'progression': _progression(vehicle),
        'setups': {
            'ammo': _setup_group(vehicle, _AMMO),
            'devices': _setup_group(vehicle, _DEVICES),
        },
    }
    # The marks of excellence, which belong in the record and therefore in the
    # fingerprint. That is deliberate: the percent moves every time the tank is
    # played, so a tank that was played comes back as changed and is sent
    # again, which is exactly how the progress gets followed. A tank nobody
    # touched hashes the same and still costs nothing.
    #
    # Written only when there is something to write, so a fleet of three
    # hundred untouched tanks does not grow two null fields each.
    marks, percent = build.mark_record(vehicle, items)
    if marks:
        record['marks'] = marks
    if percent is not None:
        record['markPercent'] = percent
    return record

def fingerprint(record):
    """What identifies this loadout, so an unchanged one is never sent twice."""
    return hashlib.md5(json.dumps(record, sort_keys=True)).hexdigest()

def mounted(record):
    """The optional devices bolted to this vehicle, as a set of names.

    The active setup only, and devices only. Consumables and directives are
    bought and spent rather than moved between vehicles, so they are not what
    the demount rule below is about.
    """
    devices = (record.get('setups') or {}).get('devices') or {}
    layouts = devices.get('layouts') or []
    if not layouts:
        return set()
    layout = layouts[devices.get('active', 0)] if devices.get('active', 0) < len(layouts) else layouts[0]
    return set(name for name in (layout.get('optDevices') or []) if name)

def crewed(record):
    """How many seats this record has somebody in."""
    return len(record.get('crew') or ())

def entry_of(value):
    """One store entry, whatever shape it arrives in.

    Two shapes reach this. A file written by an older build holds a bare
    fingerprint, with nothing said about what was mounted. And a reload can
    hand it the OTHER old shape from memory: a network callback outlives the
    generation that made it, so an answer still in flight calls whatever
    `save_sent` the module holds NOW with the `_sent` the previous one built.
    That is the orphan this mod has been bitten by before, and a serialiser is
    the worst place to meet it: it runs inside a fetch callback, where raising
    loses the whole store and reports an error the player can do nothing with.
    """
    if isinstance(value, dict):
        return {'f': value.get('f'), 'd': value.get('d'), 'c': value.get('c')}
    return {'f': value if isinstance(value, basestring) else None, 'd': None, 'c': None}

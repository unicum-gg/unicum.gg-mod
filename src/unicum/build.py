"""The selected vehicle's setup as unicum.gg's `setup` token.

A tank page reads `?setup=<token>` and opens its configurator on that build.
The token is the site's own format (apps/web/src/components/tanks/detail/
specifications/config-url.ts in unicum-gg/unicum.gg): base64url, unpadded,
of a compact query string. What is written here, and where the client keeps
it:

  s  the shell: its index in the gun's shots, for the first shell of the
     ammo layout
  m  gun, turret, engine, chassis, radio intCDs; the turret left empty on a
     vehicle without one, or the site finds no configuration and opens stock
  e  optional device names per slot, empty for a free slot
  r  the role slot's index and category, when that slot is active
  c  consumable names, three slots
  d  directive names
  f  the highest field modification level received
  p  field modification pairs chosen, "name:first" or "name:second"
  u  skill tree steps received, for a tier XI tree instead of f and p
  k  crew skills, "memberIndex:skill"; the site numbers members in the order
     of the vehicle's crew definition with same-role members grouped

Left out: the crew level (the client no longer has one below 100, which is
the site's default) and the driving mode, which a garage setup does not hold.
Every field is read on its own, and one the client cannot give is skipped: the
site opens on whatever parts of a token it understands.
"""
import base64
import logging

_logger = logging.getLogger('unicum.build')

_PAIR_SIDES = {0: 'first', 1: 'second'}


def setup_token(vehicle):
    """The token for this gui Vehicle, or None for a stock, empty setup."""
    parts = []
    for key, reader in (('s', _shell), ('m', _modules), ('e', _equipment), ('r', _role_slot),
                        ('c', _consumables), ('d', _directives), ('f', _field_mod_level),
                        ('p', _field_mod_pairs), ('u', _skill_tree), ('k', _crew_skills)):
        try:
            value = reader(vehicle)
        except Exception:
            _logger.exception('could not read the %s part of the setup', key)
            continue
        if value:
            parts.append('%s=%s' % (key, value))
    if not parts:
        return None
    return base64.urlsafe_b64encode('&'.join(parts)).rstrip('=')


def _csv(values):
    return ','.join('' if value is None else str(value) for value in values)


def _shell(vehicle):
    shells = [shell for shell in vehicle.shells.installed if shell is not None]
    if not shells:
        return None
    shots = [shot.shell.compactDescr for shot in vehicle.descriptor.gun.shots]
    index = shots.index(shells[0].intCD) if shells[0].intCD in shots else 0
    return str(index) if index else None


def _modules(vehicle):
    turret = vehicle.turret.intCD if vehicle.hasTurrets else None
    return _csv([vehicle.gun.intCD, turret, vehicle.engine.intCD, vehicle.chassis.intCD, vehicle.radio.intCD])


def _names(items):
    names = [item.name if item is not None else None for item in items]
    return names if any(names) else None


def _equipment(vehicle):
    names = _names(vehicle.optDevices.installed)
    return _csv(names) if names else None


def _role_slot(vehicle):
    slot_type = vehicle.optDevices.dynSlotType
    if slot_type is None or not vehicle.isRoleSlotActive:
        return None
    categories = list(slot_type.categories)
    return '%d:%s' % (vehicle.optDevices.dynSlotTypeIdx, categories[0]) if categories else None


def _consumables(vehicle):
    names = _names(list(vehicle.consumables.installed)[:3])
    return _csv(names) if names else None


def _directives(vehicle):
    return ','.join(item.name for item in vehicle.battleBoosters.installed if item is not None)


def _received_steps(vehicle):
    progression = vehicle.postProgression
    if progression is None or not progression.isExists():
        return progression, []
    return progression, [step for step in progression.iterUnorderedSteps() if step.isReceived()]


def _field_mod_level(vehicle):
    progression, steps = _received_steps(vehicle)
    if not steps or progression.isVehSkillTree():
        return None
    return str(max(step.getLevel() for step in steps))


def _field_mod_pairs(vehicle):
    progression, steps = _received_steps(vehicle)
    if not steps or progression.isVehSkillTree():
        return None
    pairs = []
    for step in steps:
        action = step.action
        if action.isMultiAction() and action.isPurchased():
            side = _PAIR_SIDES.get(action.getPurchasedIdx())
            if side:
                pairs.append('%s:%s' % (action.getTechName(), side))
    return ','.join(pairs)


def _skill_tree(vehicle):
    progression, steps = _received_steps(vehicle)
    if not steps or not progression.isVehSkillTree():
        return None
    return ','.join(str(step.stepID) for step in steps)


def crew_member_indexes(crew_roles):
    """Slot index -> the site's member index.

    The site reads a vehicle's crew definition with same-role members
    grouped under their first role, in order of first appearance: a radioman
    listed apart from the other comes right after it. Only two vehicles have
    such a split, but for them the plain slot order is off by one.
    """
    order = []
    for slot, roles in enumerate(crew_roles):
        first = roles[0]
        group = next((g for g in order if g[0] == first), None)
        if group is None:
            order.append((first, [slot]))
        else:
            group[1].append(slot)
    indexes = {}
    for _, slots in order:
        for slot in slots:
            indexes[slot] = len(indexes)
    return indexes


def _crew_skills(vehicle):
    indexes = crew_member_indexes(vehicle.descriptor.type.crewRoles)
    skills = []
    for slot, tankman in vehicle.crew:
        if tankman is None or slot not in indexes:
            continue
        names = [skill.name for skill in tankman.skills]
        for bonus in tankman.bonusSkills.values():
            names.extend(skill.name for skill in bonus if skill is not None)
        for name in names:
            entry = '%d:%s' % (indexes[slot], name)
            if entry not in skills:
                skills.append(entry)
    return ','.join(skills)

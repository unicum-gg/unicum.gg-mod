"""Checks for the hangar tank menu: its links and the setup token."""

import base64
import urlparse

from checks.common import check


class _Item(object):
    def __init__(self, **fields):
        self.__dict__.update(fields)


def _vehicle():
    """A vehicle with something in every part of the setup."""
    shot = lambda cd: _Item(shell=_Item(compactDescr=cd))
    step = lambda level, action=None: _Item(
        isReceived=lambda: True, getLevel=lambda: level, stepID=level * 10,
        action=action or _Item(isMultiAction=lambda: False, isPurchased=lambda: False))
    pair = _Item(isMultiAction=lambda: True, isPurchased=lambda: True,
                 getPurchasedIdx=lambda: 1, getTechName=lambda: 'role_heavyTank_pair_1')
    progression = _Item(isExists=lambda: True, isVehSkillTree=lambda: False,
                        iterUnorderedSteps=lambda: iter([step(1), step(3, pair), step(2)]))
    skill = lambda name: _Item(name=name)
    tankman = lambda *names: _Item(skills=[skill(n) for n in names], bonusSkills={'radioman': [None]})
    return _Item(
        intCD=5137, userName=u'Tiger II',
        descriptor=_Item(gun=_Item(shots=[shot(100), shot(101), shot(102)]),
                         type=_Item(crewRoles=(('commander',), ('radioman',), ('gunner',), ('radioman',)))),
        shells=_Item(installed=[_Item(intCD=101), _Item(intCD=100)]),
        hasTurrets=True, gun=_Item(intCD=1), turret=_Item(intCD=2), engine=_Item(intCD=3),
        chassis=_Item(intCD=4), radio=_Item(intCD=5),
        optDevices=_Item(installed=[_Item(name='improvedVentilation_tier1'), None, None],
                         dynSlotType=_Item(categories={'firepower'}), dynSlotTypeIdx=2),
        isRoleSlotActive=True,
        consumables=_Item(installed=[_Item(name='largeRepairkit'), None, _Item(name='autoExtinguishers')]),
        battleBoosters=_Item(installed=[None, _Item(name='turbochargerBattleBooster')]),
        postProgression=progression,
        crew=[(0, tankman('commander_tutor')), (1, tankman('repair')), (2, None), (3, tankman('camouflage'))])


def check_tank_menu():
    from unicum.build import crew_member_indexes, setup_token
    from unicum.tank_button import item_url, tank_url

    check('crew members are numbered with same-role members grouped',
          crew_member_indexes((('commander',), ('radioman',), ('gunner',), ('radioman',)))
          == {0: 0, 1: 1, 3: 2, 2: 3})

    token = setup_token(_Item(shells=_Item(installed=[None]), descriptor=_Item(gun=_Item(shots=[])),
                              hasTurrets=False, gun=_Item(intCD=1), engine=_Item(intCD=3),
                              chassis=_Item(intCD=4), radio=_Item(intCD=5)))
    check('a vehicle the client cannot fully describe still gives what it can',
          base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)) == 'm=1,,3,4,5')

    token = setup_token(_vehicle())
    check('the token is unpadded base64url', '=' not in token and '+' not in token and '/' not in token)
    fields = dict(urlparse.parse_qsl(base64.urlsafe_b64decode(token + '=' * (-len(token) % 4))))
    check('the first shell of the ammo layout, as its index in the gun', fields['s'] == '1')
    check('modules in the site order', fields['m'] == '1,2,3,4,5')
    check('equipment and consumables keep their empty slots',
          fields['e'] == 'improvedVentilation_tier1,,' and fields['c'] == 'largeRepairkit,,autoExtinguishers')
    check('the active role slot and its category', fields['r'] == '2:firepower')
    check('directives, field modifications and the pair chosen',
          fields['d'] == 'turbochargerBattleBooster' and fields['f'] == '3'
          and fields['p'] == 'role_heavyTank_pair_1:second')
    check('crew skills by the site member index', fields['k'] == '0:commander_tutor,1:repair,2:camouflage')

    check('a tab opens by tank id, with its UTM content',
          tank_url(5137, 'marks', region='eu') ==
          'https://unicum.gg/eu/tanks/5137/marks?utm_source=wot-mod&utm_medium=hangar'
          '&utm_campaign=tank-menu&utm_content=marks')
    build = item_url('build', _vehicle())
    check('share build opens the tank page with the setup', build.startswith(
        'https://unicum.gg/eu/tanks/5137?setup=%s&' % token))
    check('an AI entry hands the model the Markdown twin of the page, as the site does',
          item_url('claude', _vehicle()) == 'https://claude.ai/new?q=Read+this+World+of+Tanks+stats+page'
          '+and+help+me+analyze+it%3A+https%3A%2F%2Funicum.gg%2Feu%2Ftanks%2F5137.md%3Fsetup%3D' + token
          and item_url('chatgpt', _vehicle()).startswith('https://chatgpt.com/?hints=search&prompt=Read+this'))
    check('an unknown entry opens nothing', item_url('nope', _vehicle()) is None)

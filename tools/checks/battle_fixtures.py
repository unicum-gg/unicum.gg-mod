"""The battle a captured report is read from, and the client state around it.

Shared by every check that touches a battle report: what the client posts, the
arena bonus types it numbers, the one setting the capture reads and the account
the player is logged in with. They live here rather than in one of the check
modules because three of them already need the same fixtures, and a fixture
imported out of a sibling's private names is how they drift apart.
"""

# The Wargaming account these fixtures are played on.
ACCOUNT = '500123456'


class Bonus(object):
    """The arena bonus types the mod names, as this client numbers them."""

    REGULAR = 1
    RANKED = 22
    COMP7 = 43
    COMP7_LIGHT = 49
    SORTIE_2 = 20
    EPIC_BATTLE = 27
    TRAINING = 2


def results(**overrides):
    """A ranked win, one vehicle, as the client's results dict.

    Shaped like the payload a real client posts: `arenaUniqueID` sits beside
    `common`, and the siblings the server sends are all there. It was modelled
    with the id inside `common`, which is exactly why the capture read it from
    the wrong place and dropped every battle a real client handed it. Any
    top-level key can be overridden, which is how a check asks for a payload
    missing the id.
    """
    common = {'winnerTeam': 1,
              'bonusType': 22,
              'arenaCreateTime': 1790359200,
              'duration': 600}
    common.update(overrides.pop('common', {}))
    vehicle = {'team': 1,
               'deathReason': -1,
               'xp': 1420,
               'damageDealt': 3120,
               'damageReceived': 1880,
               'kills': 3,
               'spotted': 2,
               'capturePoints': 0,
               'droppedCapturePoints': 40}
    vehicle.update(overrides.pop('vehicle', {}))
    personal = {'8721': vehicle, 'avatar': {'team': 1}}
    personal.update(overrides.pop('personal', {}))
    payload = {'arenaUniqueID': 12457893456789012345,
               'common': common,
               'personal': personal,
               'players': {},
               'vehicles': {},
               'avatars': {}}
    payload.update(overrides)
    return payload


class Settings(object):
    """The one setting the capture and the sender read."""

    def __init__(self, on):
        self._on = on

    def sends_battle_reports(self):
        return self._on


class Link(object):
    """The account the client is logged in with, as game_link follows it."""

    def __init__(self, account=ACCOUNT, secret=None):
        self.account = account
        self.secret = secret

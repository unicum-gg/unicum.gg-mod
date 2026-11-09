"""One player or clan as unicum.gg describes it, and the kinds of id."""
from unicum import config

PLAYERS = 'players'
CLANS = 'clans'
TAGS = 'tags'
VEHICLES = 'vehicles'


class Vehicle(object):
    """What one account has done on one vehicle, in one mode or in all.

    The question a battle asks and an account's rating does not answer: a
    unicum who has just bought the tank they brought reads as a unicum
    everywhere else on screen.

    A pair the server holds nothing for is an unknown record rather than a
    missing one, for the reason an unknown Entry is cached: the same thirty
    pairs are asked about on every redraw of a battle.
    """

    __slots__ = ('known', 'scope', 'mode', 'battles', 'winrate', 'damage',
                 'xp', 'survival', 'ratings', 'fetched_at')

    def __init__(self, known=False, scope=None, mode=None, battles=0,
                 winrate=None, damage=None, xp=None, survival=None,
                 ratings=None, fetched_at=0.0):
        self.known = known
        # 'mode' when the figures are the mode's, 'overall' when they are
        # every mode together, which is the answer for a mode Wargaming
        # publishes nothing per vehicle about.
        self.scope = scope
        self.mode = mode
        self.battles = battles or 0
        self.winrate = winrate
        self.damage = damage
        self.xp = xp
        self.survival = survival
        self.ratings = ratings or {}
        self.fetched_at = fetched_at

    @classmethod
    def from_api(cls, raw, fetched_at):
        return cls(known=True,
                   scope=raw.get('scope'),
                   mode=raw.get('mode'),
                   battles=raw.get('battles') or 0,
                   winrate=raw.get('winrate'),
                   damage=raw.get('avgDamage'),
                   xp=raw.get('avgXp'),
                   survival=raw.get('survival'),
                   ratings=raw.get('ratings') or {},
                   fetched_at=fetched_at)

    def rating(self, metric):
        """The WN rating of these battles for `metric`, or None.

        None for PR and WTR by design, not by omission: they are career
        account figures with no per-vehicle value, so a reader who chose one
        of them gets no number here rather than a number off another scale.
        None too for a mode the WN scales do not measure, which the server
        decides and sends as nulls.
        """
        value = self.ratings.get(metric)
        return value if isinstance(value, (int, float)) else None


class Entry(object):
    """One player or clan, as the server described it.

    An entity the server holds nothing for is an empty Entry with `known`
    false: the answer "nothing" is cached like any other, so the same
    unknown accounts are not asked for on every redraw.
    """

    __slots__ = ('known', 'name', 'clan', 'languages', 'countries', 'source',
                 'ratings', 'members', 'fetched_at')

    def __init__(self, known=False, name=None, clan=None, languages=(),
                 countries=(), source=None, ratings=None, members=None,
                 fetched_at=0.0):
        self.known = known
        self.name = name              # player nickname, or clan tag
        self.clan = clan              # a player's clan: {id, tag, color}
        self.languages = list(languages)
        self.countries = list(countries)
        self.source = source
        self.ratings = ratings or {}  # {'total': {...}, 'recent': {...}}
        self.members = members
        self.fetched_at = fetched_at

    @classmethod
    def from_api(cls, kind, raw, fetched_at):
        clan = raw.get('clan')
        return cls(
            known=True,
            name=raw.get('nickname') if kind == PLAYERS else raw.get('tag'),
            clan=clan if isinstance(clan, dict) else None,
            languages=raw.get('languages') or [],
            countries=raw.get('countries') or [],
            source=raw.get('languageSource') or raw.get('source'),
            ratings=raw.get('ratings') or {},
            members=raw.get('membersCount'),
            fetched_at=fetched_at)

    def to_store(self):
        return {'name': self.name, 'clan': self.clan,
                'languages': self.languages, 'countries': self.countries,
                'source': self.source, 'ratings': self.ratings,
                'members': self.members, 'fetchedAt': self.fetched_at}

    @classmethod
    def from_store(cls, raw):
        return cls(known=True, name=raw.get('name'), clan=raw.get('clan'),
                   languages=raw.get('languages') or [],
                   countries=raw.get('countries') or [],
                   source=raw.get('source'), ratings=raw.get('ratings') or {},
                   members=raw.get('members'),
                   fetched_at=raw.get('fetchedAt') or 0.0)

    @property
    def primary(self):
        """Country code to show when there is only room for one flag."""
        flags = self.flags
        return flags[0] if flags else None

    @property
    def flags(self):
        """Country codes to draw, in the API's order, each once, at most a few.

        `countries` is aligned with `languages` and holds null where a
        language has no published flag. Two languages can also share one
        (en and en-us both GB-UKM on EU), and a name field has room for a
        handful at most.
        """
        out = []
        for code in self.countries:
            if code and code not in out:
                out.append(code)
            if len(out) >= config.MAX_FLAGS:
                break
        return out

    def stat(self, name, window):
        """A plain figure ('battles', 'winrate') from exactly `window`, or None.

        No falling back to the other window, unlike `rating`. A rating falls
        back because a null recent value means "not computed yet" and a stale
        number still says something true about the player. These do not: a
        career total shown where the last 30 days were asked for would be off
        by three orders of magnitude, and a reader has no way to tell.
        """
        value = (self.ratings.get(window) or {}).get(name)
        return value if isinstance(value, (int, float)) else None

    def rating(self, metric, window='recent'):
        """A rating or win rate, from `window`, else lifetime; or None.

        A recent value can be null while its battles are not: the server
        fills 30-day win rates on its own schedule, so null there means "not
        computed yet", not zero. Falling back to lifetime keeps the number on
        screen meaningful instead of blank.
        """
        for name in (window, 'total'):
            value = (self.ratings.get(name) or {}).get(metric)
            if value is not None:
                return value
        return None

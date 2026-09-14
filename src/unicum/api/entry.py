"""One player or clan as unicum.gg describes it, and the kinds of id."""
from unicum import config

PLAYERS = 'players'
CLANS = 'clans'
TAGS = 'tags'


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

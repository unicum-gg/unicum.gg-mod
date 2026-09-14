"""Checks for the page script protocol and the unicum.gg client."""

import os
import sys

from checks.common import SAMPLE_CLAN, SAMPLE_CLAN_TAG, SAMPLE_PLAYERS, check


def check_browser_scope(src_root):
    """Script goes into Stronghold pages and nowhere else."""
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    from unicum.browser import (answers_script, content_script, is_stronghold_page,
                                parse_need)

    check('the page asking for tags is understood',
          parse_need('[unicum] need RASZ,TENTS') == ['RASZ', 'TENTS'])
    check('any other console output is ignored',
          parse_need('Uncaught TypeError: x is undefined') is None)
    check('a malformed tag from the page is dropped',
          parse_need('[unicum] need RASZ,<img onerror=x>') == ['RASZ'])

    # javascript: URLs are percent-decoded, and '#' would start a fragment.
    import base64
    from unicum.browser import NEED_PREFIX
    script = content_script(7)
    check('the content script survives being a URL',
          '%' not in script and '#' not in script)
    decoded = base64.b64decode(script.split("atob('", 1)[1].split("')", 1)[0])
    check('the content script carries its generation',
          decoded.startswith('(function(GENERATION){') and decoded.endswith('})(7);'))
    check('the page and python agree on how tags are asked for',
          ("'%s'" % NEED_PREFIX) in decoded)
    pushed = answers_script({
        'RASZ': {'flags': ['data:image/png;base64,iVBOR+/w=='],
                 'wnx': {'value': 1792.2, 'color': '#6D9521'}},
        'TENTS': {'flags': [], 'wnx': None}})
    check('the answers script survives being a URL, colours included',
          '%' not in pushed and '#' not in pushed)

    check('stronghold page is scripted', is_stronghold_page(
        'https://wgsh-woteu-static.wgcdn.co/auth/entry?spa_id=1&next=/%23/battlerooms'))
    check('shop page is left alone', not is_stronghold_page(
        'https://eu.wargaming.net/shop/wot/'))
    check('clan portal is left alone', not is_stronghold_page(
        'https://eu.wargaming.net/clans/wot/500198413/'))
    check('a page without a url is left alone', not is_stronghold_page(None))


def _settle(bigworld, rounds=6):
    """Let chained requests land: tag lookups, then the ids behind them."""
    for _ in range(rounds):
        bigworld.run_pending()


def check_lookup(bigworld, src_root, api_base, label):
    """Drive the resolve client against a real server.

    Returns the lookup so a caller can tell whether it had to fall back.
    """
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    from unicum import config
    from unicum.api.resolve import CLANS, Lookup, PLAYERS
    from unicum.runtime.session import Session

    print('\n-- %s against %s' % (label, api_base))
    session = Session(generation=0)
    # Its own store, so a previous run's answers cannot make this one pass.
    store = os.path.join(src_root, 'resolve-%s.json' % label.replace(' ', '-'))
    lookup = Lookup(session, region='eu', store=store, api_base=api_base)

    check('nothing is cached before a fetch',
          lookup.get(PLAYERS, SAMPLE_PLAYERS[0]) is None)

    ready = []
    fetched_before = len(bigworld.fetched)
    lookup.prefetch(players=SAMPLE_PLAYERS, clans=[SAMPLE_CLAN], tags=[SAMPLE_CLAN_TAG.lower()],
                    on_ready=lambda: ready.append(True))
    check('one request for the whole roster, tags included',
          len(bigworld.fetched) == fetched_before + 1)
    check('nothing resolved before the response lands', not ready)
    _settle(bigworld)
    if not ready:
        print('skip the API is unreachable, lookup checks not run')
        session.close()
        return None
    check('on_ready fired once everything landed', ready == [True])

    entry = lookup.get(CLANS, SAMPLE_CLAN)
    check('clan resolved', entry is not None and entry.known and bool(entry.flags))
    check('a tag, in any case, resolves to its clan id',
          lookup.clan_id(SAMPLE_CLAN_TAG) == SAMPLE_CLAN)
    for account in SAMPLE_PLAYERS:
        check('player %s resolved' % account, lookup.get(PLAYERS, account) is not None)
    if entry is not None:
        print('       clan %s -> %s (%s)' % (SAMPLE_CLAN, entry.countries, entry.source))

    before = len(bigworld.fetched)
    lookup.prefetch(players=SAMPLE_PLAYERS, clans=[SAMPLE_CLAN], tags=[SAMPLE_CLAN_TAG],
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
    lookup.prefetch(clans=[SAMPLE_CLAN])
    check('it is not asked for twice while in flight',
          not lookup.needs_fetch(CLANS, SAMPLE_CLAN))
    check('the stale answer is drawn during the refresh',
          lookup.get(CLANS, SAMPLE_CLAN) is stale)
    _settle(bigworld)
    check('the fresh answer replaces it', not lookup.needs_fetch(CLANS, SAMPLE_CLAN)
          and lookup.get(CLANS, SAMPLE_CLAN) is not stale)

    session.close()
    check('answers are written down on close', os.path.isfile(store))
    reborn = Lookup(Session(generation=1), region='eu', store=store, api_base=api_base)
    check('the next session draws from disk before any request',
          bool(reborn.get(CLANS, SAMPLE_CLAN).flags)
          and reborn.clan_id(SAMPLE_CLAN_TAG) == SAMPLE_CLAN)

    lookup.prefetch(players=[1], on_ready=lambda: ready.append(True))
    _settle(bigworld)
    check('a closed session swallows its own response', len(ready) == 2)
    return lookup


def check_entries(src_root):
    from unicum.api.resolve import Entry

    many = Entry(known=True, languages=['en', 'en-us', 'eo', 'pl', 'uk', 'de'],
                 countries=['GB-UKM', 'GB-UKM', None, 'PL', 'UA', 'DE'])
    check('flags keep the API order, skip missing and repeated ones, stop at three',
          many.flags == ['GB-UKM', 'PL', 'UA'])
    rated = Entry(known=True, ratings={'total': {'wn8': 1800, 'winrate': 52.4},
                                       'recent': {'wn8': 2200, 'winrate': None}})
    check('a recent rating is preferred', rated.rating('wn8') == 2200)
    check('a recent win rate not computed yet falls back to lifetime',
          rated.rating('winrate') == 52.4)
    check('a missing metric is None, not zero', rated.rating('wnx') is None)


def check_scales(bigworld, src_root, api_base):
    from unicum.api.scales import RatingScales
    from unicum.runtime.session import Session

    session = Session(generation=0)
    scales = RatingScales(session, store=os.path.join(src_root, 'scales.json'),
                          api_base=api_base)
    _settle(bigworld, 2)
    if scales.color('wn8', 2000) is None:
        print('skip no rating scales served by %s' % api_base)
        session.close()
        return
    check('a wn8 is painted from the served scale',
          scales.color('wn8', 2000).startswith('#'))
    check('a win rate paints the same whichever unit the caller holds it in',
          scales.color('winrate', 52.4, unit='percent') is not None
          and scales.color('winrate', 52.4, unit='percent')
          == scales.color('winrate', 0.524, unit='ratio'))
    session.close()


if __name__ == '__main__':
    main()

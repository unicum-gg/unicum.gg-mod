"""Every unicum.gg address this mod builds, and the tags on them.

One file because they share one shape and one set of UTM tags: a link opened
from the garage and the same link pasted into a chat have to be told apart on
the site, and that is the whole reason `_utm` exists rather than each caller
appending its own.

Pure, so a change to a path is a change nothing else can get wrong.
"""
from __future__ import absolute_import

import logging
import urllib

from unicum import build, config

_logger = logging.getLogger('unicum.tank_button.urls')

SITE_BASE = 'https://unicum.gg'

# Tab ids, as TankButton.js sends them, and their path on the tank's page.
TABS = {
    'specifications': '',
    'performances': '/performances',
    'marks': '/marks',
    'history': '/history',
    'videos': '/videos',
    'community': '/community',
}

# As the site builds them: the base URL, the query with the prompt under `q`,
# and whether the assistant's own reader opens a long address.
#
# The setup token carries the whole build -- every device, the crew's skills,
# the field modifications -- and runs to about 1500 characters. Scira opens
# that as it is (checked), and so does ChatGPT (checked since: it was given the
# short form while the page it was handed answered at all, which turned out to
# be a fault of the site rather than a limit of its reader). Claude's refuses
# anything past roughly 250 and answers that the URL is too long, which is no
# answer at all, so it alone is given the bare page and the build beside it in
# the prompt: the address it has to open stays short, and the build is still
# there to be read.
AI = {
    'chatgpt': ('https://chatgpt.com/', lambda q: [('hints', 'search'), ('prompt', q)], True),
    'claude': ('https://claude.ai/new', lambda q: [('q', q)], False),
    'scira': ('https://scira.ai/', lambda q: [('q', q)], True),
}

_PROMPT = 'Read this World of Tanks stats page and help me analyze it: %s'

# The same, for a reader that will not open the page with the build on it: the
# page as the vehicle comes, and the build written out beside it. In the
# client's own words rather than the site's token, which would have to be
# decoded before it said anything (build.plain_setup).
_PROMPT_WITH_SETUP = (_PROMPT + '\n\nThat page is the vehicle as it comes. Mine is set up as follows, '
                      'in the game\'s own names:\n\n%s')

def _utm(content):
    return 'utm_source=wot-mod&utm_medium=hangar&utm_campaign=tank-menu&utm_content=%s' % content

def _client():
    """`client=ct&` on the Common Test client, whose vehicles the site keeps apart."""
    try:
        from constants import IS_CT
    except ImportError:
        return ''
    return 'client=ct&' if IS_CT else ''

def tank_url(int_cd, tab='specifications', setup=None, content=None, region=config.REGION):
    """A tank page on unicum.gg, by the tank's id."""
    query = ('setup=%s&' % setup if setup else '') + _client() + _utm(content or ('build' if setup else tab))
    return '%s/%s/tanks/%d%s?%s' % (SITE_BASE, region, int_cd, TABS[tab], query)

def tank_ai_url(item, int_cd):
    """The link an AI entry opens for a tank known only by its id.

    The garage menu has the gui Vehicle and can send the player's own build
    with it (item_url); a context menu has an id and nothing else, so this is
    the vehicle as it comes. Better than resolving the id back to an item:
    that only works for a tank in the player's garage, and these menus open on
    tanks they do not own, in the tech tree and in the shop.
    """
    if item not in AI:
        return None
    base, query, _long_url = AI[item]
    prompt = _PROMPT % markdown_url(int_cd)
    return '%s?%s' % (base, urllib.urlencode(query(prompt)))

def player_url(nickname, content='player', region=config.REGION):
    """A player's page on unicum.gg, by the nickname the client shows."""
    return '%s/%s/players/%s?%s%s' % (SITE_BASE, region, urllib.quote(nickname, safe=''),
                                      _client(), _utm(content))

def player_markdown_url(nickname, region=config.REGION):
    """The Markdown twin of a player's page, for a reader rather than a browser."""
    return '%s/%s/players/%s.md' % (SITE_BASE, region, urllib.quote(nickname, safe=''))

def player_ai_url(item, nickname):
    """The link an AI entry opens for a player, or None for an unknown entry.

    No build to carry here, unlike a vehicle, so every assistant gets the same
    address and the long/short distinction does not arise.
    """
    if item not in AI:
        return None
    base, query, _long_url = AI[item]
    prompt = _PROMPT % player_markdown_url(nickname)
    return '%s?%s' % (base, urllib.urlencode(query(prompt)))

def support_url(content):
    """The unicum.gg support page, opened from `content` (which window asked)."""
    return '%s/support?%sutm_source=wot-mod&utm_medium=settings&utm_campaign=support&utm_content=%s' % (
        SITE_BASE, _client(), content)

def item_url(item, vehicle):
    """The link a menu entry opens for this gui Vehicle, or None for an unknown entry."""
    if item in TABS:
        return tank_url(vehicle.intCD, item)
    if item in ('build', 'share'):
        content = 'share-build' if item == 'share' else 'build'
        return tank_url(vehicle.intCD, setup=build.setup_token(vehicle), content=content)
    if item in AI:
        base, query, long_url = AI[item]
        written = None if long_url else build.plain_setup(vehicle)
        if written:
            prompt = _PROMPT_WITH_SETUP % (markdown_url(vehicle.intCD), written)
        else:
            # Long enough to carry it, or nothing to say: the page as it is.
            prompt = _PROMPT % markdown_url(vehicle.intCD,
                                            build.setup_token(vehicle) if long_url else None)
        return '%s?%s' % (base, urllib.urlencode(query(prompt)))
    return None

def markdown_url(int_cd, setup=None, region=config.REGION):
    """The tank page's Markdown twin, which the site serves for an id as for a slug."""
    return '%s/%s/tanks/%d.md%s' % (SITE_BASE, region, int_cd, '?setup=%s' % setup if setup else '')

"""What goes into a Stronghold page, and what comes back out of it.

The pure half of `browser.py`: the scripts handed to the embedded browser,
and the reading of what the page says on its console. No session, no lookup,
no browser. Given settings, a string; given a console line, what it asked for.

Split out when the module it came from went past the size this repo holds its
modules to. `browser` imports every name back under its own, so a caller that
asked for `browser.parse_need` still gets it there.
"""
from __future__ import absolute_import

import base64
import json

from unicum import resources

_STRONGHOLD_HOST_MARK = '://wgsh-'

NEED_PREFIX = '[unicum] need '
# The detachment preview on the right of that window asks by nickname, which
# is the only thing it prints: no account id, no clan tag. `/resolve` took
# neither until `names` was added to it for exactly this table.
PLAYER_PREFIX = '[unicum] player '
# A detachment's line-up, which the page fetches from its own endpoint and
# sends here to be rated: the unit's id, then its members' nicknames. The
# answer is one badge for the whole detachment, see `units_script`.
UNIT_PREFIX = '[unicum] unit '
# What the page says about itself when asked, which is a development thing:
# see PROBE in web/stronghold/core.js.
PROBE_PREFIX = '[unicum] probe '

# Scripts travel as javascript: URLs, which the browser percent-decodes, so
# nothing sent may contain '%' or '#'. The content script lives in its own
# file and travels base64-encoded, which has neither; the short scripts below
# and every value spliced into them -- tags, base64 -- stay clear of both.
# A package resource folder (resources.py).
_CONTENT_SCRIPT_DIR = 'web/stronghold'

# One script in several files, joined in this order: later files use what
# earlier ones define, and lifecycle.js runs the first scan.
_CONTENT_SCRIPT_FILES = ('core.js', 'cells.js', 'table.js', 'units.js',
                         'squad.js', 'sorting.js', 'flags.js', 'lifecycle.js')


def is_stronghold_page(url):
    return bool(url) and _STRONGHOLD_HOST_MARK in url


def content_script(generation, rating_title='30d WNX', show_rating=True,
                   directory=_CONTENT_SCRIPT_DIR):
    """web/stronghold/*.js, joined and ready to run as a javascript: URL.

    Read each time, so in development reopening the Stronghold window picks up
    an edit to the script without a client restart; the bootstrap only watches
    .py files. The joined body is wrapped in a function, which gives it its
    arguments and lets it `return` early. The title travels as a JSON string,
    inside the base64 like the rest.
    """
    chunks = []
    for name in _CONTENT_SCRIPT_FILES:
        data = resources.read('%s/%s' % (directory, name))
        if data is None:
            raise IOError('no %s/%s' % (directory, name))
        chunks.append(data.decode('ascii'))
    body = '\n'.join(chunks)
    source = '(function(GENERATION, RATING_TITLE, SHOW_RATING){\n%s\n})(%d, %s, %s);' % (
        body, int(generation), json.dumps(str(rating_title)), 'true' if show_rating else 'false')
    encoded = base64.b64encode(source.encode('ascii'))
    return "javascript:eval(atob('%s'));void(0);" % encoded


def answers_script(clans_by_tag):
    """Hand resolved clans to the content script.

    {tag: {'flags': [data URI, ...], 'score': {'value', 'color'} or None}}. A
    clan with no flags and no rating is still an answer, so the page stops
    asking. The JSON travels base64-encoded like the script itself: colours
    carry a '#', which would end the javascript: URL.
    """
    payload = base64.b64encode(json.dumps(clans_by_tag, sort_keys=True))
    return ("javascript:(function(){var U=window.__unicum;"
            "if(U){U.set(JSON.parse(atob('" + payload + "')));}})();void(0);")


def players_script(players_by_name):
    """Hand resolved players to the content script.

    {nickname: {'score': {'value', 'color'} or None}}. Its own entry point
    rather than a second shape through `set`: the clan path has been working
    for months and a shared payload would have both halves failing together.

    A player with no rating is still an answer, so the page stops asking.
    """
    payload = base64.b64encode(json.dumps(players_by_name, sort_keys=True))
    return ("javascript:(function(){var U=window.__unicum;"
            "if(U&&U.setPlayers){U.setPlayers(JSON.parse(atob('" + payload + "')));}})();void(0);")


def units_script(scores_by_unit):
    """Hand each detachment's line-up average to the content script.

    {unit id: {'score': {'value', 'color', 'image', ...} or None}}. A
    detachment with nobody the site knows is still an answer, so the page
    stops asking and draws a dash rather than waiting forever.
    """
    payload = base64.b64encode(json.dumps(scores_by_unit, sort_keys=True))
    return ("javascript:(function(){var U=window.__unicum;"
            "if(U&&U.setUnits){U.setUnits(JSON.parse(atob('" + payload + "')));}})();void(0);")


def parse_unit(message):
    """(unit id, [nickname, ...]) the page sent, or None for anything else.

    The id travels as the page's own string and goes back as it came: it is
    a key on both sides and nothing here does arithmetic with it. Digits
    only, and bounded, because it is spliced into a script.

    Nicknames are read by the same rule as `parse_players`, which is
    Wargaming's own: letters, digits and underscores, up to 24. The page
    checks them too; this is the side that matters, since the page is the
    one place a value could arrive from that we did not write.
    """
    if not isinstance(message, basestring) or not message.startswith(UNIT_PREFIX):
        return None
    parts = [part.strip() for part in message[len(UNIT_PREFIX):].split(',')]
    if not parts or not parts[0].isdigit() or len(parts[0]) > 12:
        return None
    names = []
    for name in parts[1:]:
        if name and len(name) <= 24 and all(c.isalnum() or c == '_' for c in name):
            names.append(name)
    return parts[0], names


def parse_players(message):
    """Nicknames asked for by the content script, or None for anything else.

    Wider than a clan tag and bounded all the same: Wargaming allows letters,
    digits and underscores, up to 24. Anything else is dropped rather than
    sent, since the page is the one place a value could arrive from that we
    did not write.
    """
    if not isinstance(message, basestring) or not message.startswith(PLAYER_PREFIX):
        return None
    names = []
    for name in message[len(PLAYER_PREFIX):].split(','):
        name = name.strip()
        if name and len(name) <= 24 and all(c.isalnum() or c == '_' for c in name):
            names.append(name)
    return names


def parse_need(message):
    """Tags asked for by the content script, or None for any other message."""
    if not isinstance(message, basestring) or not message.startswith(NEED_PREFIX):
        return None
    tags = []
    for tag in message[len(NEED_PREFIX):].split(','):
        tag = tag.strip()
        if tag and len(tag) <= 6 and all(c.isalnum() or c in '-_' for c in tag):
            tags.append(tag)
    return tags

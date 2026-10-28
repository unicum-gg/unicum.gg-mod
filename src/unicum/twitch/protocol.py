"""Twitch's IRC on the wire, and what a message looks like once read.

Tags first: Twitch sends colour, display name and badges as IRCv3 tags, and
their escaping is its own small format (`\\s` for a space, and so on) that
has to be undone before anything is drawn. Everything here is a string in and
a value out, which is what lets the checks feed it real captured lines.
"""
from __future__ import absolute_import

import collections
import json
import logging
import os
import re

from unicum.twitch_badges import parse_badges

_logger = logging.getLogger('unicum.twitch.protocol')

_MAX_TEXT = 200

_TWITCH_COLOR = '#9146FF'
_DEFAULT_NAME_COLOR = '#C8C8C8'
_TEXT_COLOR = '#FFFFFF'

# The Glitch before each message, built by tools/badges/icon.mjs. A resource
# file, so one installed into a folder the client did not know at startup
# draws from the next start; until then the word "Twitch" stands in.
ICON_RES_PATH = 'gui/maps/icons/unicum/twitch.png'
_ICON = '<IMG SRC="img://%s" width="14" height="14" vspace="-3"/>' % ICON_RES_PATH

_COLOR = re.compile(r'^#[0-9A-Fa-f]{6}$')

# IRCv3 tag value escapes.
_TAG_ESCAPES = {'\\s': ' ', '\\:': ';', '\\\\': '\\', '\\r': '\r', '\\n': '\n'}

Message = collections.namedtuple('Message', 'name color text badges login')
Message.__new__.__defaults__ = ((), '')

def parse_line(line):
    """('ping', server), ('message', Message) or None, for one IRC line."""
    tags = {}
    if line.startswith('@'):
        raw, _, line = line.partition(' ')
        for pair in raw[1:].split(';'):
            key, _, value = pair.partition('=')
            tags[key] = re.sub(r'\\[s:\\rn]', lambda m: _TAG_ESCAPES[m.group(0)], value)
    if line.startswith('PING'):
        return 'ping', line.partition(' ')[2]
    prefix = ''
    if line.startswith(':'):
        prefix, _, line = line[1:].partition(' ')
    command, _, rest = line.partition(' ')
    if command != 'PRIVMSG':
        return None
    _, _, text = rest.partition(' :')
    if text.startswith('\x01ACTION ') and text.endswith('\x01'):
        text = text[len('\x01ACTION '):-1]
    name = tags.get('display-name') or prefix.partition('!')[0]
    color = tags.get('color') if _COLOR.match(tags.get('color') or '') else None
    login = prefix.partition('!')[0].lower()
    return 'message', Message(name, color, text, parse_badges(tags.get('badges')), login)

def format_message(message, icon=False, badges=''):
    """The battle chat's HTML for a Twitch message, behind the Glitch or the word.

    `badges` is the <IMG> markup of the viewer's badges, drawn before the name.
    """
    text = message.text if len(message.text) <= _MAX_TEXT else message.text[:_MAX_TEXT - 1] + u'\u2026'
    source = _ICON if icon else u"<font color='%s'>Twitch</font>" % _TWITCH_COLOR
    return u"%s %s<font color='%s'>%s</font>: <font color='%s'>%s</font>" % (
        source, badges, message.color or _DEFAULT_NAME_COLOR, _escape(message.name), _TEXT_COLOR, _escape(text))

def _escape(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# How the player looks in their own chat, kept for the messages shown before
# Twitch echoes them: name, colour and badges only come with a message.
SELF_STORE = os.path.join('mods', 'configs', 'unicum', 'twitch_self.json')

# Before any of their own messages was seen: it is their channel.
_OWNER_BADGES = ('broadcaster/1',)
# The name on the player's own message while their channel is not known yet.
_OWN_NAME = 'You'

def own_message(appearance, channel, text):
    """The player's message as Twitch would show it, from their last seen appearance."""
    if appearance and appearance.get('login') == channel:
        return Message(appearance.get('name') or channel, appearance.get('color'), text,
                       tuple(appearance.get('badges') or ()), channel)
    return Message(channel or _OWN_NAME, None, text, _OWNER_BADGES, channel)

def appearance_of(message):
    return {'login': message.login, 'name': message.name, 'color': message.color,
            'badges': list(message.badges)}

def _load_self():
    try:
        with open(SELF_STORE) as handle:
            appearance = json.load(handle)
        return appearance if isinstance(appearance, dict) else None
    except (IOError, OSError, ValueError):
        return None

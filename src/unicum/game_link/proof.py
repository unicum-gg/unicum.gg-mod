"""What proves an account, and where that proof is kept.

The mod draws a random secret and sends only its SHA-256 along the chain the
player follows in a browser. Once the site has linked the hash, the secret is
the mod's bearer token, and the mod learns that by polling GET /api/game/me
with it. The secret itself never crosses anything but this machine and the
Authorization header.

Pure, which is the point: the hash, the URL and the reading of an answer are
all testable with no client and no network.
"""
from __future__ import absolute_import

import binascii
import hashlib
import json
import logging
import os
import random
import string
import urllib

_logger = logging.getLogger('unicum.game_link.proof')

STORE = os.path.join('mods', 'configs', 'unicum', 'account.json')

TWITCH_READY = 'ready'

ME_PATH = '%s/api/game/me'

def new_secret():
    return binascii.hexlify(os.urandom(32))

def secret_hash(secret):
    return hashlib.sha256(secret).hexdigest()

def connect_url(api_base, region, secret, account_id=None, token=None, twitch=True):
    """The page that links this client; the Wargaming web token rides in the fragment.

    Without `twitch`, the account alone is linked and the page never goes on to Twitch.
    `account` names the game's Wargaming account, which the site checks the
    browser's session against before linking.
    """
    url = '%s/api/connect/game/%s?region=%s' % (api_base.rstrip('/'), secret_hash(secret), region)
    if account_id:
        url += '&account=%s' % account_id
    if not twitch:
        url += '&twitch=0'
    if account_id and token:
        url += '#' + urllib.urlencode([('account_id', account_id), ('token', token)])
    return url

def bearer(secret):
    return {'Authorization': 'Bearer %s' % secret}

def read_me(response):
    """(name, twitch access, twitch login) from GET /api/game/me; None when not linked or unreadable."""
    if getattr(response, 'responseCode', None) != 200:
        return None
    try:
        payload = json.loads(response.body)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    login = payload.get('twitchLogin')
    login = str(login).lower() if isinstance(login, basestring) and login else None
    return payload.get('name'), payload.get('twitch'), login

def read_privacy(response):
    """(supports the site, loadouts hidden) from the same answer as `read_me`.

    Read apart from the identity rather than widened into it: the identity
    tuple is unpacked at four call sites, and growing it to carry two more
    fields would have meant changing every one of them for a switch only the
    settings window looks at.

    Both default to false, which is the safe way round. A client that cannot
    read the answer draws no switch rather than an inert one, and treats the
    loadouts as shown rather than claiming they are hidden.
    """
    if getattr(response, 'responseCode', None) != 200:
        return False, False
    try:
        payload = json.loads(response.body)
    except (TypeError, ValueError):
        return False, False
    if not isinstance(payload, dict):
        return False, False
    return bool(payload.get('supporter')), bool(payload.get('loadoutsHidden'))

def current_account_id():
    """The Wargaming account id the client is logged in with, or None (the login screen).

    The lobby answers for itself. In a battle the avatar carries no
    database id, so the arena answers instead, with the account the
    server named on the player's own vehicle. A client that starts in a
    battle, which is a reconnect after a crash or a restart, has had no
    lobby to ask and would otherwise hold no link at all until the battle
    ended: no name, no card, and a chat it could read but not write in.
    """
    try:
        import BigWorld
        account_id = getattr(BigWorld.player(), 'databaseID', None)
    except Exception:
        return None
    return str(account_id) if account_id else _arena_account_id()

def _arena_account_id():
    """The account id the arena gives the player's own vehicle, or None.

    Never a replay's: there the player's own vehicle is whoever recorded
    it, and watching one is no reason to read another account's link.
    """
    try:
        import BattleReplay
        if BattleReplay.g_replayCtrl.isPlaying:
            return None
        from helpers import dependency
        from skeletons.gui.battle_session import IBattleSessionProvider
        arena_dp = dependency.instance(IBattleSessionProvider).getArenaDP()
        account_id = arena_dp.getVehicleInfo().player.accountDBID
    except Exception:
        return None
    return str(account_id) if account_id else None

def read_store(raw):
    """(links {account id: secret}, card hidden for [account ids]) from account.json's content.

    An account.json from before links were per account holds one `secret`,
    returned under None for the first account the game logs in with.
    """
    links, hidden = {}, []
    if not isinstance(raw, dict):
        return links, hidden
    for account_id, secret in (raw.get('links') or {}).items():
        if isinstance(secret, basestring) and len(secret) == 64:
            links[str(account_id)] = str(secret)
    legacy = raw.get('secret')
    if isinstance(legacy, basestring) and len(legacy) == 64:
        links[None] = str(legacy)
    hidden = [str(account_id) for account_id in raw.get('cardHidden') or [] if account_id]
    return links, hidden

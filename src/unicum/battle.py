"""Marks battle player names with where each player comes from.

Battle names are assembled by PlayerFullNameFormatter.format, which asks
player_format.getRegionCode for a short suffix and drops it in right after
the clan tag:

    '{0:>s}[{1:>s}] {3:>s}'    name, clan, vehicle, region

That reaches AS3 as `model.region` and is assigned as `htmlText` by
CommonsBase.applyTextProps, so the field takes markup as well as text.

getRegionCode returns None for anyone on their home realm, so on EU the
field is empty for essentially everyone. A genuinely roaming player does
have a code, and it is not ours to drop: ours is appended to whatever the
client already decided.

The hard part is that getRegionCode is synchronous and the answer comes over
the network. So it never waits: it returns whatever is cached, and the
account ids it is asked about are collected and resolved in one batch just
after. Names drawn before the answer lands simply carry no marker, and pick
one up the next time they are drawn.
"""
import logging

from gui.battle_control.arena_info import player_format

from unicum import config
from unicum.api.languages import PLAYERS, LanguageLookup
from unicum.textures import FlagCache

_logger = logging.getLogger('unicum.battle')

# Flags come from the disk cache, addressed by resource path. See
# textures.py for why a URL, and a memory texture, both fail here.
_TEMPLATE = ' <IMG SRC="%s" width="12" height="9" vspace="-1"/>'

# Long enough to gather a whole team's worth of ids from the render pass,
# short enough to be back before anyone finishes reading the loading screen.
_BATCH_DELAY = 0.25


class BattleFlags(object):

    def __init__(self, session):
        self._session = session
        self._lookup = LanguageLookup(session, config.REGION)
        self._textures = FlagCache(session)
        self._pending = set()
        self._scheduled = False

    def install(self):
        # PlayerFullNameFormatter.format resolves getRegionCode as a module
        # global at call time, so replacing the attribute reaches it.
        self._session.patch(player_format, 'getRegionCode', self._wrap)
        _logger.info('installed on player_format.getRegionCode, api=%s',
                     config.API_BASE)

    def _wrap(self, original):

        def getRegionCode(accountDBID, lobbyContext=None):
            # The original is wrapped in @dependency.replace_none_kwargs,
            # which injects lobbyContext as a keyword. Forwarding our own
            # default positionally collides with that injection, so let it do
            # its job when the caller did not supply one.
            if lobbyContext is None:
                existing = original(accountDBID)
            else:
                existing = original(accountDBID, lobbyContext=lobbyContext)
            return (existing or '') + self._marker(accountDBID)

        return getRegionCode

    def _marker(self, account_id):
        if not account_id:
            return ''
        entry = self._lookup.get(PLAYERS, account_id)
        if entry is None:
            self._request(account_id)
            return ''
        if not entry.countries:
            return ''
        # One flag only: a battle row has room for a couple of characters,
        # and a player with three languages would otherwise push their own
        # name out of the field.
        source = self._textures.source(entry.countries[0])
        if source is None:
            # Still being fetched or mapped. Drawing nothing beats drawing a
            # broken image, and the next redraw picks it up.
            return ''
        return _TEMPLATE % source

    def _request(self, account_id):
        """Queue an id, and resolve the whole batch shortly after.

        Every name in a team is formatted in the same pass, so waiting a
        moment turns what would be fifteen requests into one.
        """
        self._pending.add(account_id)
        if self._scheduled:
            return
        self._scheduled = True
        self._session.callback(_BATCH_DELAY, self._flush)

    def _flush(self):
        self._scheduled = False
        if not self._pending:
            return
        batch, self._pending = sorted(self._pending), set()
        _logger.info('resolving %s players', len(batch))
        self._lookup.prefetch(players=batch,
                              on_ready=lambda: self._report(batch))

    def _report(self, batch):
        resolved = []
        for account_id in batch:
            entry = self._lookup.get(PLAYERS, account_id)
            if entry is not None and entry.countries:
                resolved.append((account_id, entry.countries[0]))
        _logger.info('resolved %s/%s: %s', len(resolved), len(batch), resolved)


def install(session):
    BattleFlags(session).install()

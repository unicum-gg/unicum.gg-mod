"""The lobby surfaces, held together and paced.

Keeps for itself what both halves need: the lookup, the redraw that every
surface ends in, and the batching that keeps a hundred names from becoming a
hundred requests.
"""
from __future__ import absolute_import

import logging
import time
import weakref

from gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room import StrongholdBattleRoom
from gui.Scaleform.daapi.view.lobby.profile.ProfileWindow import ProfileWindow
from gui.Scaleform.daapi.view.lobby.rally.rally_dps import SortieCandidatesLegionariesDP
from messenger.gui.Scaleform.data.contacts_data_provider import ContactsDataProvider
from messenger.gui.Scaleform.data.contacts_vo_converter import ContactConverter
from unicum.api.entry import PLAYERS
from unicum.lobby.profile import Profile
from unicum.lobby.rooms import Rooms

_logger = logging.getLogger('unicum.lobby.flags')

_BATCH_DELAY = 0.25

# How often the lobby view is given the contacts' markers, and checked for.
_COLUMNS_SECONDS = 0.5


class LobbyFlags(Rooms, Profile):


    def __init__(self, session, lookup, flags, badges, settings, alt=None):
        self._session = session
        self._lookup = lookup
        self._textures = flags
        self._badges = badges
        self._settings = settings
        # Whether the extended info key is held, for the surfaces that wait
        # for it. None: nothing waits, everything shows.
        self._alt = alt
        self._pending = set()
        self._scheduled = False
        # Views that drew before their languages arrived, and have to be told
        # to draw again once they do. Held weakly: tracking a view must never
        # be what keeps a closed window alive.
        self._providers = weakref.WeakSet()
        self._profiles = weakref.WeakSet()
        self._rooms = weakref.WeakSet()
        # The contacts' markers for the lobby view's right-hand column
        # (as3/src/unicum/ContactColumns.as), by account id, and whether the
        # rows are drawn that way: while the view is not loaded, the markers
        # go after the name as elsewhere.
        self._contact_markers = {}
        self._columns = False
        self._published_markers = None

    def install(self):
        self._watch_alt()
        self._session.patch(ContactConverter, 'makeBaseUserProps', self._wrap)
        self._session.patch(ProfileWindow, 'as_setInitDataS', self._wrap_profile)
        self._session.patch(ContactsDataProvider, 'buildList', self._wrap_build)
        # The skirmish room, scoped to that one view. makePlayerVO would have
        # reached it too, but it also feeds the platoon and other rally
        # windows whose rendering has not been checked -- the same over-reach
        # that once put raw <IMG> markup in the profile window title.
        self._session.patch(StrongholdBattleRoom, 'as_setMembersS',
                            self._wrap_members)
        self._session.patch(StrongholdBattleRoom, 'as_updateRallyS',
                            self._wrap_rally)
        self._session.patch(StrongholdBattleRoom, '_dispose', self._wrap_dispose)
        self._session.patch(SortieCandidatesLegionariesDP, '_makePlayerVO',
                            self._wrap_candidate)
        self._settings.on_change(self._redraw)
        self._follow_columns()
        self._session.repeat(_COLUMNS_SECONDS, self._follow_columns)
        _logger.info('installed on contacts, profile window and skirmish room')

    def _redraw(self):
        """Rebuild the views that drew while languages were still missing.

        Mirrors what the client does itself when clan members change:
        buildList, refresh, onTotalStatusChanged. Rebuilding cannot loop --
        by now every id it asks about is cached, so it queues no lookup.
        """
        for provider in list(self._providers):
            try:
                provider.buildList()
                provider.refresh()
                provider.onTotalStatusChanged()
            except Exception:
                _logger.exception('could not rebuild a contacts list')
        self._redraw_rooms()
        for view in list(self._profiles):
            try:
                if getattr(view, 'isDisposed', lambda: False)():
                    continue
                update = getattr(view, '_ProfileWindow__updateUserInfo', None)
                if update is not None:
                    update()
            except Exception:
                _logger.exception('could not refresh a profile window')

    def _marker(self, account_id, surface, rating=True):
        """The surface's flags and rating, as htmlText markup.

        `rating` is dropped where the rating has a column of its own, which
        is the skirmish room and only when `_ROOM_RATING_COLUMN` is on:
        leaving it on the name as well would show it twice and leave the
        column no room to sit in -- there are twenty pixels between the
        name's box and that column.
        """
        if not account_id or not self._settings.shows(surface) or self._waits_for_alt(surface):
            return ''
        entry = self._entry(account_id)
        marker = ''
        if self._settings.shows_flags(surface):
            marker += self._textures.markup(entry, self._settings['maxFlags'])
        if rating:
            marker += self._badges.rating(entry, self._settings, surface)
        # Written out in full here: contacts, a profile and a room list all
        # have a line's width rather than a column's.
        marker += self._badges.extras(entry, self._settings, surface)
        return marker

    def _request(self, account_id):
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
        asked_at = time.time()
        self._lookup.prefetch(players=batch,
                              on_ready=lambda: self._report(batch, asked_at))

    def _report(self, batch, asked_at=0.0):
        entries = [(account_id, self._lookup.get(PLAYERS, account_id)) for account_id in batch]
        resolved = [(account_id, entry.countries[0]) for account_id, entry in entries
                    if entry is not None and entry.countries]
        _logger.info('resolved %s/%s: %s', len(resolved), len(batch),
                     resolved[:8])
        # On any fresh answer, flags or not: a player with ratings and no
        # language still has a badge and counts in the room's average. A
        # failed lookup leaves the views as they were, so no rebuild then.
        if any(entry is not None and entry.fetched_at >= asked_at for _, entry in entries):
            self._redraw()

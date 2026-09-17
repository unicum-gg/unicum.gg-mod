"""Marks contacts with where each player comes from.

ContactConverter.makeBaseUserProps builds the `region` field of every row in
the contacts list, and that row is drawn as htmlText -- the client injects
its own status icon into the same props through makeHtmlString.

The obvious hook was LobbyContext.getRegionCode, one function feeding every
surface that shows a region. It reached too far. That value is also spliced
into flat strings for plain text fields, and the profile window title came
out reading

    Seif_Sahbouch [YONQO] <IMG SRC="img://gui/maps/.../FR.png" .../>

Markup in a shared data accessor is a bet on every consumer rendering HTML,
and that bet loses. So the patch sits on the presentation layer instead: one
per surface, each one somewhere markup is known to be honoured.

This is also where the contacts list showed that resolving every id it knows
about is not free: it asked for 3293 players at once, which is why the API
client batches.
"""
import logging
import time
import weakref

from gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room import StrongholdBattleRoom
from gui.Scaleform.daapi.view.lobby.profile.ProfileWindow import ProfileWindow
from gui.Scaleform.daapi.view.lobby.rally.rally_dps import SortieCandidatesLegionariesDP
from messenger.gui.Scaleform.data.contacts_data_provider import ContactsDataProvider
from messenger.gui.Scaleform.data.contacts_vo_converter import ContactConverter

from unicum import views
from unicum.api.entry import PLAYERS

_logger = logging.getLogger('unicum.lobby')

_BATCH_DELAY = 0.25

# The profile window title's font is taller than the lists' the markup is made
# for: with the lists' vspace="-3" the images sat below the name's middle, and
# with vspace="1" above it (both seen at 1440p); the middle lies between.
_LIST_VSPACE = 'vspace="-3"'
_TITLE_VSPACE = 'vspace="-1"'

# How often the lobby view is given the contacts' markers, and checked for.
_COLUMNS_SECONDS = 0.5


class LobbyFlags(object):

    def __init__(self, session, lookup, flags, badges, settings):
        self._session = session
        self._lookup = lookup
        self._textures = flags
        self._badges = badges
        self._settings = settings
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

    def _wrap_members(self, original):
        """Mark the detachment members, just before they reach Flash.

        Each slot's `player` VO carries `region` into the same
        UserNameField -> formatPlayerName -> htmlText chain as the contacts
        list, so the flag goes in the same field.
        """

        def as_setMembersS(room, hasRestrictions, slots):
            self._rooms.add(room)
            self._publish_members_safely(self._mark_slots(slots))
            return original(room, hasRestrictions, slots)

        return as_setMembersS

    def _wrap_rally(self, original):
        """The same members, sent again whenever the room's state changes.

        Going into battle redraws the whole detachment through this call,
        with its own freshly built slots, so without it the flags vanished
        the moment the detachment entered a battle.
        """

        def as_updateRallyS(room, data):
            self._rooms.add(room)
            if isinstance(data, dict):
                self._publish_members_safely(self._mark_slots(data.get('slots')))
            return original(room, data)

        return as_updateRallyS

    def _wrap_dispose(self, original):

        def _dispose(room, *args, **kwargs):
            try:
                self._publish_members([])
            except Exception:
                _logger.exception('could not clear the detachment ratings')
            return original(room, *args, **kwargs)

        return _dispose

    def _publish_members_safely(self, account_ids):
        """_publish_members, whose failure must not keep the room from updating."""
        try:
            self._publish_members(account_ids)
        except Exception:
            _logger.exception('could not publish the detachment ratings')

    def _publish_members(self, account_ids):
        """Hand the members' ratings to the lobby view, or clear them.

        Written to as3/src/unicum/RoomTools.as: each member's rating, which
        the rating order sorts by, and the average's badge, shown beside the
        members title, which is text the AS3 section sets itself. Called with
        every members update, so both follow arrivals, departures and ratings
        that land.
        """
        view = views.lobby_view()
        if view is None:
            return
        enabled = self._settings['enabled']
        if getattr(view, 'roomEnabled', None) != enabled:
            view.roomEnabled = enabled
        values = []
        known = []
        for account_id in account_ids:
            entry = self._entry(account_id)
            value = self._settings.rating(entry, 'skirmishRoom')
            if value is not None:
                values.append(value)
                known.append('%d:%d' % (account_id, round(value)))
        by_player = ','.join(known)
        if getattr(view, 'ratingByPlayer', None) != by_player:
            view.ratingByPlayer = by_player
        markup = ''
        if values and self._settings.shows_average('skirmishRoom'):
            average = sum(values) / float(len(values))
            badge = self._badges.markup(self._settings.metric('skirmishRoom'), average) or '%d' % round(average)
            # The badge alone: the title's embedded font has no average sign,
            # which came out in a fallback serif.
            markup = badge
        if getattr(view, 'averageHtml', None) != markup:
            view.averageHtml = markup

    def _mark_slots(self, slots):
        """Mark every member; the account ids seen, for the average."""
        account_ids = []
        try:
            for slot in slots or ():
                player = slot.get('player') if isinstance(slot, dict) else None
                if isinstance(player, dict):
                    self._mark_region(player, player.get('dbID'), 'skirmishRoom')
                    if player.get('dbID'):
                        account_ids.append(player.get('dbID'))
        except Exception:
            _logger.exception('could not mark skirmish room members')
        return account_ids

    def _wrap_candidate(self, original):
        """Mark the volunteers panel of the skirmish room."""

        def _makePlayerVO(provider, pInfo, *args, **kwargs):
            vo = original(provider, pInfo, *args, **kwargs)
            try:
                if isinstance(vo, dict):
                    self._mark_region(vo, getattr(pInfo, 'dbID', None), 'skirmishRoom')
            except Exception:
                _logger.exception('could not mark a skirmish volunteer')
            return vo

        return _makePlayerVO

    def _mark_region(self, vo, account_id, surface):
        # Appended, not assigned: a roaming player already has a region code
        # there, and it is not ours to drop. And left untouched when there is
        # nothing to add, so a None stays None -- some views type this field
        # as Object and reject an empty string.
        marker = self._marker(account_id, surface)
        if marker:
            vo['region'] = (vo.get('region') or '') + marker

    def _wrap_build(self, original):
        """Remember every contacts list that builds, so it can be rebuilt.

        The rows are made synchronously and the languages arrive over the
        network, so the first build of a list is always missing whatever was
        not cached yet. Nothing redraws it on its own: without a rebuild the
        flags only appeared after closing and reopening the panel.
        """

        def buildList(provider, *args, **kwargs):
            self._providers.add(provider)
            return original(provider, *args, **kwargs)

        return buildList

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
        for room in list(self._rooms):
            try:
                if getattr(room, 'isDisposed', lambda: False)():
                    continue
                room._updateMembersData()
                room._rebuildCandidatesDP()
            except Exception:
                _logger.exception('could not refresh a skirmish room')
        for view in list(self._profiles):
            try:
                if getattr(view, 'isDisposed', lambda: False)():
                    continue
                update = getattr(view, '_ProfileWindow__updateUserInfo', None)
                if update is not None:
                    update()
            except Exception:
                _logger.exception('could not refresh a profile window')

    def _wrap_profile(self, original):
        """The profile window title: a flag, or a language code without one.

        Window.title is plain text: an <IMG> there once rendered as its own
        source. AS3's Window does have a titleUseHtml switch, which the
        vehicle info, buy and chat windows turn on and the profile window
        never does. views.py loads a small AS3 view that turns it on; when
        that SWF is missing the title falls back to the language code.

        The switch cannot be reached from Python directly. The GFx proxy
        reads AS3 getters and `parent`, but the view's interface-typed getters
        (window, wrapper, containerContent) come back None, and walking up
        from the view stops after three levels without meeting the Window.
        Walking the display tree down from the app root crashed the client
        (access violation) -- do not try that again.
        """

        def as_setInitDataS(view, data):
            try:
                self._profiles.add(view)
                account_id = getattr(view, '_ProfileWindow__databaseID', None)
                if isinstance(data, dict) and data.get('fullName') and self._settings.shows('profile'):
                    if views.html_titles():
                        marker = self._marker(account_id, 'profile').replace(_LIST_VSPACE, _TITLE_VSPACE)
                    elif self._settings.shows_flags('profile'):
                        code = self._language_code(account_id)
                        marker = ' ' + code if code else ''
                    else:
                        marker = ''
                    if marker:
                        data['fullName'] = data['fullName'] + marker
            except Exception:
                _logger.exception('could not mark profile title')
            return original(view, data)

        return as_setInitDataS

    def _language_code(self, account_id):
        """Language, not country: text gets languages, images get countries.

        A country code only exists to name a flag file, and 'GB-UKM' spelled
        out in a title means nothing.
        """
        entry = self._entry(account_id) if account_id else None
        if entry is None or not entry.languages:
            return None
        return entry.languages[0].upper()

    def _entry(self, account_id):
        """What is known about a player now, asking for more if it is due.

        An old answer is still returned: it is drawn while the fresh one is
        on its way, rather than the name going blank in between.
        """
        if self._lookup.needs_fetch(PLAYERS, account_id):
            self._request(account_id)
        return self._lookup.get(PLAYERS, account_id)

    def _follow_columns(self):
        """Give the lobby view the contacts' markers, and switch the rows' way of drawing them.

        When the view comes or goes, the lists are built again the other way,
        so no row keeps its markers in both places or in neither.
        """
        view = views.lobby_view()
        columns = view is not None
        if columns != self._columns:
            self._columns = columns
            self._published_markers = None
            self._redraw()
        if view is None:
            return
        text = '\n'.join('%s\t%s' % (account_id, markup)
                          for account_id, markup in sorted(self._contact_markers.items()) if markup)
        # By view too: a reloaded view starts with none.
        if self._published_markers is not None and self._published_markers[0] is view and \
                self._published_markers[1] == text:
            return
        try:
            view.contactMarkers = text
            self._published_markers = (view, text)
        except Exception:
            # A view whose class predates the property, until the client restarts.
            _logger.debug('the lobby view has no contactMarkers yet', exc_info=True)

    def _wrap(self, original):

        def makeBaseUserProps(cls, contact):
            props = original(contact)
            try:
                if self._columns:
                    self._contact_markers[contact.getID()] = self._marker(contact.getID(), 'contacts').strip()
                else:
                    self._mark_region(props, contact.getID(), 'contacts')
            except Exception:
                # A contacts list that fails to build is worse than one
                # without flags, and this runs for every row.
                _logger.exception('could not mark contact')
            return props

        # Returned as a classmethod so the attribute keeps the shape the
        # class declared; the callers invoke it off the class.
        return classmethod(makeBaseUserProps)

    def _marker(self, account_id, surface):
        """The surface's flags and rating, as htmlText markup."""
        if not account_id or not self._settings.shows(surface):
            return ''
        entry = self._entry(account_id)
        marker = ''
        if self._settings.shows_flags(surface):
            marker += self._textures.markup(entry, self._settings['maxFlags'])
        marker += self._badges.rating(entry, self._settings, surface)
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


def install(session, lookup, flags, badges, settings):
    LobbyFlags(session, lookup, flags, badges, settings).install()

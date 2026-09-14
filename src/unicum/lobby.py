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
import weakref

from gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room import StrongholdBattleRoom
from gui.Scaleform.daapi.view.lobby.profile.ProfileWindow import ProfileWindow
from gui.Scaleform.daapi.view.lobby.rally.rally_dps import SortieCandidatesLegionariesDP
from messenger.gui.Scaleform.data.contacts_data_provider import ContactsDataProvider
from messenger.gui.Scaleform.data.contacts_vo_converter import ContactConverter

from unicum import titles
from unicum.api.resolve import PLAYERS

_logger = logging.getLogger('unicum.lobby')

_BATCH_DELAY = 0.25


class LobbyFlags(object):

    def __init__(self, session, lookup, flags, scales):
        self._session = session
        self._lookup = lookup
        self._textures = flags
        self._scales = scales
        self._pending = set()
        self._scheduled = False
        # Views that drew before their languages arrived, and have to be told
        # to draw again once they do. Held weakly: tracking a view must never
        # be what keeps a closed window alive.
        self._providers = weakref.WeakSet()
        self._profiles = weakref.WeakSet()
        self._rooms = weakref.WeakSet()

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
        self._session.patch(SortieCandidatesLegionariesDP, '_makePlayerVO',
                            self._wrap_candidate)
        _logger.info('installed on contacts, profile window and skirmish room')

    def _wrap_members(self, original):
        """Mark the detachment members, just before they reach Flash.

        Each slot's `player` VO carries `region` into the same
        UserNameField -> formatPlayerName -> htmlText chain as the contacts
        list, so the flag goes in the same field.
        """

        def as_setMembersS(room, hasRestrictions, slots):
            self._rooms.add(room)
            self._mark_slots(slots)
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
                self._mark_slots(data.get('slots'))
            return original(room, data)

        return as_updateRallyS

    def _mark_slots(self, slots):
        try:
            for slot in slots or ():
                player = slot.get('player') if isinstance(slot, dict) else None
                if isinstance(player, dict):
                    self._mark_region(player, player.get('dbID'), rating=True)
        except Exception:
            _logger.exception('could not mark skirmish room members')

    def _wrap_candidate(self, original):
        """Mark the volunteers panel of the skirmish room."""

        def _makePlayerVO(provider, pInfo, *args, **kwargs):
            vo = original(provider, pInfo, *args, **kwargs)
            try:
                if isinstance(vo, dict):
                    self._mark_region(vo, getattr(pInfo, 'dbID', None), rating=True)
            except Exception:
                _logger.exception('could not mark a skirmish volunteer')
            return vo

        return _makePlayerVO

    def _mark_region(self, vo, account_id, rating=False):
        # Appended, not assigned: a roaming player already has a region code
        # there, and it is not ours to drop. And left untouched when there is
        # nothing to add, so a None stays None -- some views type this field
        # as Object and reject an empty string.
        marker = self._marker(account_id, rating)
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
        never does. titles.py loads a small AS3 view that turns it on; when
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
                if isinstance(data, dict) and data.get('fullName'):
                    if titles.html_titles():
                        marker = self._marker(account_id)
                    else:
                        code = self._language_code(account_id)
                        marker = ' ' + code if code else ''
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

    def _wrap(self, original):

        def makeBaseUserProps(cls, contact):
            props = original(contact)
            try:
                self._mark_region(props, contact.getID())
            except Exception:
                # A contacts list that fails to build is worse than one
                # without flags, and this runs for every row.
                _logger.exception('could not mark contact')
            return props

        # Returned as a classmethod so the attribute keeps the shape the
        # class declared; the callers invoke it off the class.
        return classmethod(makeBaseUserProps)

    def _marker(self, account_id, rating=False):
        """Flags, and with `rating` the player's WNx, as htmlText markup.

        The WNx goes only where there is room for it, the skirmish room for
        now: contact rows and the profile title stay flags only.
        """
        if not account_id:
            return ''
        entry = self._entry(account_id)
        marker = self._textures.markup(entry)
        if rating and entry is not None:
            marker += self._rating_markup(entry)
        return marker

    def _rating_markup(self, entry):
        """' <FONT COLOR="#...">1792</FONT>', painted with the site's scale.

        The recent WNx, or the lifetime one while the recent is not
        computed. Unpainted rather than missing when the scale has not been
        fetched yet.
        """
        wnx = entry.rating('wnx')
        if wnx is None:
            return ''
        text = '%d' % round(wnx)
        color = self._scales.color('wnx', wnx)
        if color:
            return ' <FONT COLOR="%s">%s</FONT>' % (color, text)
        return ' ' + text

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
        self._lookup.prefetch(players=batch,
                              on_ready=lambda: self._report(batch))

    def _report(self, batch):
        resolved = []
        for account_id in batch:
            entry = self._lookup.get(PLAYERS, account_id)
            if entry is not None and entry.countries:
                resolved.append((account_id, entry.countries[0]))
        _logger.info('resolved %s/%s: %s', len(resolved), len(batch),
                     resolved[:8])
        # Only when something came back: a failed lookup leaves the views
        # exactly as they were, so rebuilding them would be pure cost.
        if resolved:
            self._redraw()


def install(session, lookup, flags, scales):
    LobbyFlags(session, lookup, flags, scales).install()

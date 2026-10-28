"""The detachment room: its member list, its slots, its candidates.

The hardest surface in the mod to draw on, because the client rebuilds the
whole list on almost any change and each rebuild throws away what was grafted
on. So every one of these wraps a call the client makes itself, and
`_publish_members_safely` exists because a failure in here must not take the
room's own list down with it.

A mixin, for the reason the battles package gives.
"""
from __future__ import absolute_import

import logging

from unicum import views

_logger = logging.getLogger('unicum.lobby.rooms')

# Whether a detachment member's rating is drawn in a column of its own,
# beside the room's Rating, instead of riding on the member's name.
#
# OFF, and deliberately: the Python side is finished and the AS3 side is not.
# It is handed its seven members and draws none of them, and the one probe
# that would have said why fired on a frame where the column was legitimately
# empty. Rather than release a column that may draw nothing, this holds it and
# the badge stays on the name, which is where it is on every other garage
# surface and where it was before any of this.
#
# Not a setting: turning it on is a decision about an unfinished thing, not a
# preference, and a preference would need a name on screen.
#
# The sort order does not depend on it. The numbers it sorts by are published
# either way; only the drawing is held.
_ROOM_RATING_COLUMN = False


class Rooms(object):
    """The detachment room and its member lists."""

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
        the rating order sorts by; each member's BADGE, drawn in a column of
        its own beside the room's own Rating; and the average's badge, shown
        beside the members title, which is text the AS3 section sets itself.
        Called with every members update, so all three follow arrivals,
        departures and ratings that land.

        The badges travel apart from the numbers because they cannot share
        their encoding: a badge is `<IMG SRC="img://...png" .../>`, which
        carries both of the separators the numbers use. Tab and newline are
        the two characters markup never holds.
        """
        view = views.lobby_view()
        if view is None:
            return
        enabled = self._settings['enabled']
        if getattr(view, 'roomEnabled', None) != enabled:
            view.roomEnabled = enabled
        metric = self._settings.metric('skirmishRoom')
        # The column is a drawn thing, so it answers to the surface's own
        # switch and to the extended info key; the numbers behind the sort
        # order are not drawn and keep working either way.
        drawn = (_ROOM_RATING_COLUMN
                 and self._settings.shows('skirmishRoom')
                 and not self._waits_for_alt('skirmishRoom'))
        values = []
        known = []
        badges = []
        for account_id in account_ids:
            entry = self._entry(account_id)
            value = self._settings.rating(entry, 'skirmishRoom')
            if value is not None:
                values.append(value)
                known.append('%d:%d' % (account_id, round(value)))
                if drawn:
                    badge = self._badges.markup(metric, value)
                    if badge:
                        badges.append(u'%d\t%s' % (account_id, badge))
        by_player = ','.join(known)
        if getattr(view, 'ratingByPlayer', None) != by_player:
            view.ratingByPlayer = by_player
        badge_by_player = u'\n'.join(badges)
        if getattr(view, 'ratingHtmlByPlayer', None) != badge_by_player:
            view.ratingHtmlByPlayer = badge_by_player
        header = self._settings.label('skirmishRoom') if drawn else u''
        if getattr(view, 'ratingHeader', None) != header:
            view.ratingHeader = header
        markup = ''
        if values and self._settings.shows_average('skirmishRoom') and not self._waits_for_alt('skirmishRoom'):
            average = sum(values) / float(len(values))
            badge = self._badges.markup(metric, average) or '%d' % round(average)
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
                    # The rating sits on the name unless it has a column of
                    # its own to sit in; see _ROOM_RATING_COLUMN.
                    self._mark_region(player, player.get('dbID'), 'skirmishRoom',
                                      rating=not _ROOM_RATING_COLUMN)
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

    def _mark_region(self, vo, account_id, surface, rating=True):
        # Appended, not assigned: a roaming player already has a region code
        # there, and it is not ours to drop. And left untouched when there is
        # nothing to add, so a None stays None -- some views type this field
        # as Object and reject an empty string.
        marker = self._marker(account_id, surface, rating)
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

    def _redraw_rooms(self):
        for room in list(self._rooms):
            try:
                if getattr(room, 'isDisposed', lambda: False)():
                    continue
                room._updateMembersData()
                room._rebuildCandidatesDP()
            except Exception:
                _logger.exception('could not refresh a skirmish room')

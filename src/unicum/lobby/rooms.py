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
import time

from unicum import views

_logger = logging.getLogger('unicum.lobby.rooms')

# Whether a detachment member's rating is drawn in the room's own Rating
# column instead of riding on the member's name.
#
# ON. The column is TAKEN OVER, not added beside: this window has no room to
# add anything. Every position in it is baked into a Flash symbol -- the
# window sizes nothing, the room view sizes nothing, the row renderer sizes
# nothing -- so a column of our own could only be squeezed out of the name's
# width, which is what was pushing the names out of the list in the first
# place. The column that is there holds Wargaming's personal rating, which is
# the one figure on the row nobody reads.
#
# The trade is the same one the Stronghold page makes, and it was asked for.
#
# Not a setting: it is a decision about where a figure lives, not a
# preference, and a preference would need a name on screen.
#
# The sort order does not depend on it. The numbers it sorts by are published
# either way; only the drawing follows this.
_ROOM_RATING_COLUMN = True


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
        # The flags travel the same way as the badges, and for the same
        # reason as the column: a flag that rides on the name sits wherever
        # that name ends, so a list of them is a ragged edge. Placed by the
        # view instead, they end where the ratings begin and read as a
        # column. `_mark_slots` leaves them off the name for exactly this.
        shows_flags = (self._settings.shows_flags('skirmishRoom')
                       and self._settings.shows('skirmishRoom')
                       and not self._waits_for_alt('skirmishRoom'))
        values = []
        known = []
        badges = []
        flags = []
        for account_id in account_ids:
            entry = self._entry(account_id)
            if shows_flags:
                drawn_flags = self._textures.markup(entry, self._settings['maxFlags']).strip()
                if drawn_flags:
                    flags.append(u'%d\t%s' % (account_id, drawn_flags))
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
        flags_by_player = u'\n'.join(flags)
        if getattr(view, 'flagsHtmlByPlayer', None) != flags_by_player:
            view.flagsHtmlByPlayer = flags_by_player
        # The column's name as the chip the mod names a figure with
        # everywhere else, rather than as words: this is a column of badges
        # and its name is the marking those badges wear. The words stay as
        # the fallback, for a chip the client cannot draw.
        header = u''
        if drawn:
            label = self._settings.label('skirmishRoom')
            # Shouted, because a chip's glyphs are capitals and a letter it
            # has none for simply does not draw: "30d WNX" came out as
            # "30 WNX", missing its d and saying nothing about the period.
            header = self._badges.chip_markup(label.upper()) or label
        if getattr(view, 'ratingHeader', None) != header:
            view.ratingHeader = header
        self._say_column(enabled, drawn, badges, header, view)
        markup = ''
        if values and self._settings.shows_average('skirmishRoom') and not self._waits_for_alt('skirmishRoom'):
            average = sum(values) / float(len(values))
            badge = self._badges.markup(metric, average) or '%d' % round(average)
            # The badge alone: the title's embedded font has no average sign,
            # which came out in a fallback serif.
            markup = badge
        if getattr(view, 'averageHtml', None) != markup:
            view.averageHtml = markup

    def _say_column(self, enabled, drawn, badges, header, view):
        """Both halves of the room's column, in one line, when they change.

        What Python sent and what the view found, together: either on its
        own says nothing. The last attempt at this column was given up on
        because "it draws none of them" was all anybody knew, and that is
        true of a column nobody sends badges to as much as of one that
        cannot find its rows.
        """
        state = (enabled, drawn, len(badges), header)
        now = time.time()
        if getattr(self, '_column_said', None) == state and \
                now - getattr(self, '_column_said_at', 0) < 5.0:
            return
        self._column_said = state
        self._column_said_at = now
        try:
            found = view.takeRoomReport()
        except Exception:
            found = 'the view has no report'
        _logger.info('room column: enabled=%s drawn=%s sent=%s header=%r -- %s',
                     enabled, drawn, len(badges), header, found)

    def _view_draws_flags(self):
        """Whether the loaded view draws the detachment's flags itself.

        Asked of the view rather than assumed from this module's own switch,
        because the two halves of the mod do not arrive together: Python
        reloads the moment a file is saved, the view only at the next client
        start. Taking the flags off the names while the running view cannot
        draw them yet is a list with no flags at all for the rest of the
        session, which is what a developer saving a file in the middle of
        somebody's evening would otherwise do to them.

        A view too old to answer raises, and raising means no.
        """
        view = views.lobby_view()
        if view is None:
            return False
        try:
            return bool(view.takesFlags())
        except Exception:
            return False

    def _mark_slots(self, slots):
        """Mark every member; the account ids seen, for the average."""
        account_ids = []
        try:
            for slot in slots or ():
                player = slot.get('player') if isinstance(slot, dict) else None
                if isinstance(player, dict):
                    # Neither the rating nor the flags ride on a member's
                    # name: both have a place of their own in this list now,
                    # and a flag on the name sits wherever that name happens
                    # to end. The volunteers' panel still carries both, it
                    # has no column to put them in.
                    self._mark_region(player, player.get('dbID'), 'skirmishRoom',
                                      rating=not _ROOM_RATING_COLUMN,
                                      flags=not self._view_draws_flags())
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

    def _mark_region(self, vo, account_id, surface, rating=True, flags=True):
        """Both of this window's lists: the detachment, and the volunteers.

        Without the win rate and the battle count, which is the one place in
        the mod where they are dropped. This window holds the narrowest name
        in the game: a row is a kick button, a voice icon, a clan emblem,
        the flags and then whatever is left, and three badges on top of that
        left ONE letter of the name -- "N..", "a..", "S..". The figure being
        read here is the rating, and it has a column of its own now; a win
        rate and a count belong where a line has a line's width, which is
        the contacts list and a profile.
        """
        # Appended, not assigned: a roaming player already has a region code
        # there, and it is not ours to drop. And left untouched when there is
        # nothing to add, so a None stays None -- some views type this field
        # as Object and reject an empty string.
        marker = self._marker(account_id, surface, rating, extras=False, flags=flags)
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

"""The profile page, the contacts list, and waiting for Alt.

Two surfaces that share one problem: the client draws them from a model it
builds once, so a rating added later has to go in before that model is read,
not after it is drawn. The Alt key is here because it decides, per surface,
whether anything is drawn at all.

A mixin, for the reason given in `rooms`.
"""
from __future__ import absolute_import

import logging

from unicum import views
from unicum.api.entry import PLAYERS

_logger = logging.getLogger('unicum.lobby.profile')

# The profile window title's font is taller than the lists' the markup is made
# for: with the lists' vspace="-3" the images sat below the name's middle, and
# with vspace="1" above it (both seen at 1440p); the middle lies between.
_LIST_VSPACE = 'vspace="-3"'
_TITLE_VSPACE = 'vspace="-1"'


class Profile(object):
    """The profile page, the contacts, and the Alt key."""

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

    def _watch_alt(self):
        """Follow the extended info key while a surface here waits for it.

        Only the skirmish room does, and only when its setting says so; the
        key is read in the garage only while it is asked for. A change
        redraws the room, which is what puts the ratings in or takes them out.
        """
        if self._alt is None:
            return
        self._alt.watch_outside_battle()
        self._alt.on_change(self._on_alt)
        self._settings.on_change(self._on_alt)

    def _on_alt(self):
        if not self._settings.alt_only('skirmishRoom'):
            return
        self._redraw_rooms()

    def _waits_for_alt(self, surface):
        from unicum.extended_info import waits
        return waits(self._alt, self._settings, surface)

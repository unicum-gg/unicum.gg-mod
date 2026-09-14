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

from gui.Scaleform.daapi.view.lobby.profile.ProfileWindow import ProfileWindow
from messenger.gui.Scaleform.data.contacts_data_provider import ContactsDataProvider
from messenger.gui.Scaleform.data.contacts_vo_converter import ContactConverter

from unicum.api.languages import PLAYERS

_logger = logging.getLogger('unicum.lobby')

# 12x9 rather than the 16x12 the source PNG is, and nudged up with vspace.
# An image sets the line height, and these rows are a fixed height, so a
# taller one makes Flash squash the whole line -- long names like
# Sofia_Lauren_de_Michelle[LOOTA] lose the most. The client's own emblem
# template leans on vspace the same way, at 24x24 vspace=-10.
_TEMPLATE = ' <IMG SRC="%s" width="12" height="9" vspace="-1"/>'
_BATCH_DELAY = 0.25


class LobbyFlags(object):

    def __init__(self, session, lookup, flags):
        self._session = session
        self._lookup = lookup
        self._textures = flags
        self._pending = set()
        self._scheduled = False
        # Views that drew before their languages arrived, and have to be told
        # to draw again once they do. Held weakly: tracking a view must never
        # be what keeps a closed window alive.
        self._providers = weakref.WeakSet()
        self._profiles = weakref.WeakSet()

    def install(self):
        self._session.patch(ContactConverter, 'makeBaseUserProps', self._wrap)
        self._session.patch(ProfileWindow, 'as_setInitDataS', self._wrap_profile)
        self._session.patch(ContactsDataProvider, 'buildList', self._wrap_build)
        _logger.info('installed on ContactConverter, ContactsDataProvider '
                     'and ProfileWindow')

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
        """The profile window title, which takes a language code, not a flag.

        Window.title is plain text: an <IMG> there once rendered as its own
        source. AS3's Window does have a titleUseHtml switch, which the
        vehicle info, buy and chat windows turn on and the profile window
        never does. It cannot be reached from Python though: the view's
        flashObject.window reads as None both when the title data arrives and
        a moment later, so the GFx proxy does not expose it. The only other
        way to a flag here is editing the SWF, which would not hot reload and
        would break on every client update.
        """

        def as_setInitDataS(view, data):
            try:
                self._profiles.add(view)
                account_id = getattr(view, '_ProfileWindow__databaseID', None)
                if isinstance(data, dict) and data.get('fullName'):
                    code = self._language_code(account_id)
                    if code:
                        data['fullName'] = '%s %s' % (data['fullName'], code)
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
                props['region'] = (props.get('region') or '') + self._marker(
                    contact.getID())
            except Exception:
                # A contacts list that fails to build is worse than one
                # without flags, and this runs for every row.
                _logger.exception('could not mark contact')
            return props

        # Returned as a classmethod so the attribute keeps the shape the
        # class declared; the callers invoke it off the class.
        return classmethod(makeBaseUserProps)

    def _marker(self, account_id):
        if not account_id:
            return ''
        entry = self._entry(account_id)
        if entry is None or not entry.countries:
            return ''
        source = self._textures.source(entry.countries[0])
        if source is None:
            return ''
        return _TEMPLATE % source

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


def install(session, lookup, flags):
    LobbyFlags(session, lookup, flags).install()

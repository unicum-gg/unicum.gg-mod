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

from gui.Scaleform.daapi.view.lobby.profile.ProfileWindow import ProfileWindow
from messenger.gui.Scaleform.data.contacts_vo_converter import ContactConverter

from unicum import config
from unicum.api.languages import PLAYERS, LanguageLookup
from unicum.textures import FlagCache

_logger = logging.getLogger('unicum.lobby')

# 12x9 rather than the 16x12 the source PNG is, and nudged up with vspace.
# An image sets the line height, and these rows are a fixed height, so a
# taller one makes Flash squash the whole line -- long names like
# Sofia_Lauren_de_Michelle[LOOTA] lose the most. The client's own emblem
# template leans on vspace the same way, at 24x24 vspace=-10.
_TEMPLATE = ' <IMG SRC="%s" width="12" height="9" vspace="-1"/>'
_BATCH_DELAY = 0.25


class LobbyFlags(object):

    def __init__(self, session):
        self._session = session
        self._lookup = LanguageLookup(session, config.REGION)
        self._textures = FlagCache(session)
        self._pending = set()
        self._scheduled = False

    def install(self):
        self._session.patch(ContactConverter, 'makeBaseUserProps', self._wrap)
        self._session.patch(ProfileWindow, 'as_setInitDataS', self._wrap_profile)
        _logger.info('installed on ContactConverter and ProfileWindow')

    def _wrap_profile(self, original):
        """The profile window title, which takes text and not markup.

        Window(window).title is a plain TextField -- an <IMG> there renders
        as its own source, which is how the over-reaching patch announced
        itself. A country code says the same thing in a field that can hold
        it.
        """

        def as_setInitDataS(view, data):
            try:
                account_id = getattr(view, '_ProfileWindow__databaseID', None)
                code = self._language(account_id)
                if code and isinstance(data, dict) and data.get('fullName'):
                    data['fullName'] = '%s %s' % (data['fullName'], code)
            except Exception:
                _logger.exception('could not mark profile title')
            return original(view, data)

        return as_setInitDataS

    def _language(self, account_id):
        """Language code for a text field, not the country code.

        Countries only exist here to name a flag file. Spelled out they are
        meaningless or wrong -- 'GB-UKM' is a Flagpack filename, and it is
        the language that was actually inferred. So images get countries and
        text gets languages.
        """
        if not account_id:
            return None
        entry = self._lookup.get(PLAYERS, account_id)
        if entry is None:
            self._request(account_id)
            return None
        return entry.languages[0].upper() if entry.languages else None

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
        entry = self._lookup.get(PLAYERS, account_id)
        if entry is None:
            self._request(account_id)
            return ''
        if not entry.countries:
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
        _logger.info('resolved %s/%s: %s', len(resolved), len(batch), resolved)


def install(session):
    LobbyFlags(session).install()

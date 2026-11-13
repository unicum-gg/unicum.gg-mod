"""The unicum.gg tab of the game's own settings window, in the garage and in battle.

The tab is drawn by the mod's AS3 views (as3/src/unicum/SettingsTab.as, added
to the window by SettingsTabs.as), with the game's own controls, in sub-tabs:
Garage, Battle and Twitch. It holds the very settings of the modsSettingsApi
page (settings_window/page.py), the same variables with the same choices, and both
write settings.json, so either shows what the other changed.

The views are handed the page as text (settings_window.page.native_page) in their
`settingsTab` property, again whenever the settings or the Twitch link change.
What the player changes waits in the tab until Apply or OK, as the window's
own settings do, then comes back in `settingsTabOut` (settings_window.codec.read_native),
taken on the next tick and applied as the modsSettingsApi page's are; Cancel or
the window's cross drop it. The buttons act at once: Connect, and the ones
that only open a page.
"""
import logging

from unicum import views
from unicum.settings import Settings, validate
from unicum.settings.validating import _merge
from unicum.settings_window import codec, labels, page, window

_logger = logging.getLogger('unicum.settings_tab')

_TICK_SECONDS = 0.5


class SettingsTab(object):

    def __init__(self, session, settings, link=None):
        self._session = session
        self._settings = settings
        self._link = link
        self._chat = None
        self._published = {}  # view name -> page it was last handed
        self._drawing = None  # (badges, flag textures, settings), once built
        # Window values changed but not yet applied, so the preview can show
        # them. Never saved: `_take` keeps them apart from what it applies.
        self._peek = {}
        self._failed = set()  # views whose properties could not be reached, logged once

    def install(self):
        self._session.repeat(_TICK_SECONDS, self._tick)
        _logger.info('installed')

    def follow_badges(self, badges, textures):
        """Hand over what the preview draws with. See the API window's own.

        Nothing else to do: the tab republishes whenever the page text
        changes, and a preview that appears makes it change.
        """
        self._drawing = (badges, textures, self._settings)

    def follow_twitch(self, chat):
        """Show the channel `chat` follows on the Twitch sub-tab."""
        self._chat = chat

    def _previewing(self):
        """What the preview draws with: the store, or a shadow of it.

        A shadow while something is pending. It is a Settings with another
        values dict and nothing else -- no file, no session, no listeners --
        because every question the preview asks is answered out of that
        dict. It is never saved and never notifies: the moment Apply or
        Cancel settles the choice, `_peek` empties and this goes away.
        """
        if not self._peek or not self._drawing:
            return self._drawing
        try:
            merged = self._settings.values()
            _merge(merged, codec.from_window(self._peek))
            shadow = Settings.__new__(Settings)
            shadow._values = validate(merged)
            badges, textures, _ = self._drawing
            return (badges, textures, shadow)
        except Exception:
            _logger.exception('could not preview the pending settings')
            return self._drawing

    def _page(self):
        link = self._link
        linked = bool(link is not None and link.secret)
        channel = self._chat.channel if self._chat is not None else u''
        card_shown = not (link is not None and link.card_hidden)
        return page.native_page(
            self._settings.values(), channel, linked and link.twitch == 'ready', card_shown,
            supporter=bool(link is not None and link.supporter),
            loadouts_hidden=bool(link is not None and link.loadouts_hidden),
            battles_hidden=link.battles_hidden if linked else None,
            drawing=self._previewing())

    def _tick(self):
        try:
            page = self._page()
        except Exception:
            _logger.exception('could not describe the settings tab')
            return
        for name, flash in (('lobby', views.lobby_view()), ('battle', views.battle_view())):
            if flash is None:
                self._published.pop(name, None)
                continue
            try:
                self._take(flash)
                if self._published.get(name) != page:
                    flash.settingsTab = page
                    self._published[name] = page
            except Exception:
                # A view of an older build, without the tab's properties.
                if name not in self._failed:
                    self._failed.add(name)
                    _logger.exception('no settings tab in the %s view', name)

    def _take(self, flash):
        # A call, not a property: the view's proxy reads a property once and
        # answers with that value ever after, so the tab's messages would
        # never arrive. The call hands them over and leaves none behind.
        try:
            text = flash.takeSettingsTabOut()
        except Exception:
            # A view of an older build: its property answers once per load.
            text = flash.settingsTabOut
        if not text:
            return
        # A line for the log from the tab's AS3, which cannot write to it.
        for line in text.split(u'\n'):
            if line.startswith(u'log\tl\t'):
                _logger.info('tab: %s', line[len(u'log\tl\t'):])
        peeked = codec.read_peek(text)
        if peeked or u'peek\t\t\t' in text:
            # A settling line answers {}, which is the whole point of it.
            self._peek = dict(self._peek, **peeked) if peeked else {}
        raw, buttons = codec.read_native(text)
        if raw:
            # Applied for real, so nothing is pending any more: the tab says
            # so too, but the order the two lines arrive in is not worth
            # relying on.
            self._peek = {}
            codec.apply_window(raw, self._settings, self._link)
        # Each button once, however many times the message names it.
        for var in dict.fromkeys(buttons):
            window.handle_button(var, self._settings, 'settings-tab')
        if labels.CONNECT_VAR in buttons and self._link is not None:
            self._link.connect(labels.linked_notice)


def install(session, settings, link=None):
    tab = SettingsTab(session, settings, link)
    tab.install()
    return tab

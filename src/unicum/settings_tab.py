"""The unicum.gg tab of the game's own settings window, in the garage and in battle.

The tab is drawn by the mod's AS3 views (as3/src/unicum/SettingsTab.as, added
to the window by SettingsTabs.as), with the game's own controls, in sub-tabs:
Garage, Battle and Twitch. It holds the very settings of the modsSettingsApi
page (settings_window.py), the same variables with the same choices, and both
write settings.json, so either shows what the other changed.

The views are handed the page as text (settings_window.native_page) in their
`settingsTab` property, again whenever the settings or the Twitch link change.
What the player changes waits in the tab until Apply or OK, as the window's
own settings do, then comes back in `settingsTabOut` (settings_window.read_native),
taken on the next tick and applied as the modsSettingsApi page's are; Cancel or
the window's cross drop it. The buttons, Connect and Support, act at once.
"""
import logging

from unicum import settings_window, views

_logger = logging.getLogger('unicum.settings_tab')

_TICK_SECONDS = 0.5


class SettingsTab(object):

    def __init__(self, session, settings, link=None):
        self._session = session
        self._settings = settings
        self._link = link
        self._chat = None
        self._published = {}  # view name -> page it was last handed
        self._failed = set()  # views whose properties could not be reached, logged once

    def install(self):
        self._session.repeat(_TICK_SECONDS, self._tick)
        _logger.info('installed')

    def follow_twitch(self, chat):
        """Show the channel `chat` follows on the Twitch sub-tab."""
        self._chat = chat

    def _page(self):
        link = self._link
        linked = bool(link is not None and link.secret)
        channel = self._chat.channel if self._chat is not None else u''
        card_shown = not (link is not None and link.card_hidden)
        return settings_window.native_page(self._settings.values(), channel,
                                           linked and link.twitch == 'ready', card_shown)

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
        # Reading takes the lines: the view hands them over and keeps none.
        # Writing the property back would be worse than useless, since a value
        # written to a view's property is the one read from it ever after.
        text = flash.settingsTabOut
        if not text:
            return
        # A line for the log from the tab's AS3, which cannot write to it.
        for line in text.split(u'\n'):
            if line.startswith(u'log\tl\t'):
                _logger.info('tab: %s', line[len(u'log\tl\t'):])
        raw, buttons = settings_window.read_native(text)
        if raw:
            settings_window.apply_window(raw, self._settings, self._link)
        if settings_window.SUPPORT_VAR in buttons:
            settings_window.open_support('settings-tab')
        if settings_window.CONNECT_VAR in buttons and self._link is not None:
            self._link.connect(settings_window._linked_notice)


def install(session, settings, link=None):
    tab = SettingsTab(session, settings, link)
    tab.install()
    return tab

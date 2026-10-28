"""The window itself: registering it, drawing it, and reading it back.

The only part here that touches the client. Everything the page says is in
`labels`, everything it looks like is in `page`, and everything it means is
in `codec`.
"""
from __future__ import absolute_import

import json
import logging

from unicum.settings_window.codec import apply_window, read_native, to_window
from unicum.settings_window.labels import (linked_notice, CONNECT_VAR,
                                           DISCORD_URL, DISCORD_VAR, LINKAGE,
                                           LINKS, RESET_VAR, SOURCE_URL,
                                           SOURCE_VAR, SUPPORT_VAR)
from unicum.settings_window.page import channel_label, native_page, template

_logger = logging.getLogger('unicum.settings_window.window')

def reset_defaults(settings):
    """Every setting back to its default, and a system message saying so."""
    from unicum.settings import DEFAULTS
    settings.update(json.loads(json.dumps(DEFAULTS)))
    _logger.info('the settings were put back to their defaults')
    try:
        from gui import SystemMessages
        from gui.shared.notifications import NotificationPriorityLevel
        SystemMessages.pushMessage(u'unicum.gg: the settings are back to their defaults.',
                                   type=SystemMessages.SM_TYPE.Information,
                                   priority=NotificationPriorityLevel.MEDIUM)
    except Exception:
        _logger.debug('could not say that the settings were reset', exc_info=True)

def handle_button(var, settings, content):
    """What a button of either page does, apart from Twitch's Connect."""
    if var == RESET_VAR:
        reset_defaults(settings)
        return True
    return open_link(var, content)

def link_url(var, content):
    """Where a link button goes, or None for a variable that is not one."""
    from unicum import tank_button
    if var == SUPPORT_VAR:
        return tank_button.support_url(content)
    return {DISCORD_VAR: DISCORD_URL, SOURCE_VAR: SOURCE_URL}.get(var)

def open_link(var, content):
    """A link button's page in the player's browser; True if it was one."""
    url = link_url(var, content)
    if url is None:
        return False
    from unicum import tank_button
    tank_button.open_url(url)
    return True


class SettingsWindow(object):


    def __init__(self, session, settings, link=None):
        self._session = session
        self._settings = settings
        self._link = link
        self._chat = None
        # (channel followed, Twitch chat writable, game linked, account name,
        # card shown, supports the site, loadouts hidden) as the page shows
        # them. It has to match what `_register` unpacks and what
        # `_check_state` builds: `install` registers off this one, before the
        # link has answered anything.
        self._state = (u'', False, False, None, True, False, False)
        self._alive = True
        self._api = None

    def install(self):
        try:
            from gui.modsSettingsApi import g_modsSettingsApi
        except ImportError:
            _logger.info('modsSettingsApi not installed, settings.json only')
            return
        self._api = g_modsSettingsApi
        self._register()
        self._session.on_close(self._remove)
        self._settings.on_change(self._on_settings)
        _logger.info('registered in modsSettingsApi as %s', LINKAGE)

    def follow_twitch(self, chat):
        """Show the channel `chat` follows, and the account link, as they change."""
        self._chat = chat
        if self._api is not None:
            self._session.repeat(2.0, self._check_state)

    def _check_state(self):
        link = self._link
        linked = bool(link is not None and link.secret)
        state = (self._chat.channel if self._chat is not None else u'',
                 linked and link.twitch == 'ready', linked, link.name if linked else None,
                 self._card_shown(), self._supporter(), self._hidden())
        if state == self._state:
            return
        self._state = state
        # A new template replaces the page; its callbacks are added again, so
        # the ones already on the API's events come off first.
        self._unregister()
        self._register()

    def _card_shown(self):
        return not (self._link is not None and self._link.card_hidden)

    def _supporter(self):
        return bool(self._link is not None and self._link.supporter)

    def _hidden(self):
        return bool(self._link is not None and self._link.loadouts_hidden)

    def _register(self):
        channel, writable, linked, name, card_shown, supporter, hidden = self._state
        self._api.setModTemplate(LINKAGE, template(self._settings.values(), channel, writable, card_shown,
                                                   supporter, hidden),
                                 self._on_window, self._on_button)
        # The API keeps its own copy of every value and sends it back as the
        # player's choice. For the card that copy can be stale (the card's
        # cross changes the truth without going through the window), and an
        # old "shown" coming back would undo the cross: so it is set to the
        # truth first.
        self._api.updateModSettings(LINKAGE, to_window(self._settings.values(), card_shown, hidden))

    def _on_window(self, linkage, raw):
        if not self._alive or linkage != LINKAGE or not isinstance(raw, dict):
            return
        apply_window(raw, self._settings, self._link)

    def _on_button(self, linkage, var_name, value=None):
        if not self._alive or linkage != LINKAGE:
            return
        if handle_button(var_name, self._settings, 'mods-list'):
            return
        if self._link is not None and var_name == CONNECT_VAR:
            self._link.connect(linked_notice)

    def _on_settings(self):
        """Keep the window in step with a hand edit of settings.json."""
        # The API answers with onSettingsChanged, which lands in _on_window
        # with values that change nothing.
        self._api.updateModSettings(LINKAGE, to_window(self._settings.values(), self._card_shown()))

    def _remove(self):
        self._alive = False
        self._unregister()

    def _unregister(self):
        instance = getattr(self._api, '_ModsSettingsApi__instance', None)
        for name, handler in (('onSettingsChanged', self._on_window), ('onButtonClicked', self._on_button)):
            event = getattr(instance, name, None)
            try:
                event -= handler
            except Exception:
                _logger.debug('could not unregister %s', name, exc_info=True)

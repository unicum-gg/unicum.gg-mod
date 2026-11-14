"""Flags next to clan tags on the Stronghold pages of the embedded browser.

The Stronghold "Clan Battles" window is not Flash. BrowserController loads
the WGSH single-page app from wgsh-woteu-static.wgcdn.co into an embedded
CEF view, so the detachment list is DOM and no Python view model is
involved. Reaching it means running script in the page.

WebBrowser.executeJavascript is dead code in this build: it forwards to a
native method the provider does not have. The provider does have loadURL,
and a `javascript:` URL runs in the current document. The page talks back
through the provider's onConsoleMessage event.

So the work is split across that channel:

  page    web/stronghold/ finds every [TAG] leaf, keeps finding them as
          React re-renders, and reports the tags it has no answer for as
          `[unicum] need RASZ,TENTS`. It also folds the detachment list's
          redundant "Places" column into "Members", adds a column for the
          rating chosen in the settings and sorts by rating or by it. The
          details are there.
  python  asks the resolve endpoint for all the tags in one request, which
          answers with each clan, and sends back its flags as data: URIs
          and its rating with the site's colour for it.

data: URIs rather than unicum.gg's flag URLs, because those sit behind a bot
challenge that an <img> request cannot pass. The PNGs are already on disk.

Only Stronghold pages are touched. The same controller hosts every embedded
browser in the client -- the shop, the clan portal, event pages -- and none
of them are ours to script.
"""
import base64
import json
import logging
import weakref

from helpers import dependency
from skeletons.gui.game_control import IBrowserController

from unicum.browser_scripts import (NEED_PREFIX, PLAYER_PREFIX, PROBE_PREFIX,
                                    answers_script, content_script,
                                    is_stronghold_page, parse_need,
                                    parse_players, players_script)
from unicum.api.entry import CLANS, PLAYERS

_logger = logging.getLogger('unicum.browser')

# Every Stronghold page observed so far is served from a wgsh-* host, e.g.
# https://wgsh-woteu-static.wgcdn.co/auth/entry?...next=/#/battlerooms
# Before asking again for tags whose request failed: past the lookup's own
# retry delay, which would otherwise answer from nothing.
_RETRY_SECONDS = 65.0

_STOP_SCRIPT = (
    "javascript:(function(){var U=window.__unicum;"
    "if(U&&U.stop){U.stop();}})();void(0);"
)


class BrowserBridge(object):
    """Keeps the content script running in every Stronghold page."""

    def __init__(self, session, lookup, flags, scales, settings, alt=None):
        self._session = session
        self._lookup = lookup
        self._flags = flags
        self._scales = scales
        self._settings = settings
        # Whether the extended info key is held, when the page waits for it.
        self._alt = alt
        # Bumped by every settings change, so the page sees a new version.
        self._revision = 0
        # What the page's script was last built from, so a change that
        # cannot reach it does not tear it down. See `_on_settings`.
        self._script_at = None
        self._controller = dependency.instance(IBrowserController)
        self._attached = {}
        session.on_close(self._remove_scripts)

    def install(self):
        self._session.subscribe(self._controller.onBrowserAdded, self._on_added)
        # Browsers open before this load are not announced again, so whatever
        # is on screen right now has to be picked up directly. During
        # development that is the normal case: the window under test is
        # already open when the reload lands.
        for browser_id in list(self._controller.getAllBrowsers()):
            self._attach(browser_id)
        self._settings.on_change(self._on_settings)
        if self._alt is not None:
            # The key is read outside a battle only while something asks for
            # it, and a page put up or taken down is a settings change here.
            self._alt.watch_outside_battle()
            self._alt.on_change(self._on_settings)

    def _script_state(self):
        """Everything the page's script is built from, as one value."""
        from unicum.extended_info import waits
        return (self._settings.shows('stronghold'),
                waits(self._alt, self._settings, 'stronghold'),
                self._settings.label('stronghold') or '',
                self._settings.metric('stronghold') is not None)

    def _on_settings(self):
        """Stop the page's script, and start one with the new settings.

        Only when something the script reads has actually moved. This is
        wired to the extended info key as well as to settings.json, and that
        key changes state every time it is pressed anywhere in the garage.
        A teardown per press threw away everything the page had resolved:
        the clans, the players, and the record of what had been asked for.
        So every answer was asked for again a moment after it arrived --
        the same twenty-seven clans and seven players, three times in five
        seconds -- and the preview panel spent its life being painted and
        then re-rendered over before anything could stick.

        A key that gates nothing on this surface now changes nothing here,
        which is what it always meant.
        """
        state = self._script_state()
        if state == self._script_at:
            return
        self._script_at = state
        self._revision += 1
        for ref in list(self._attached.values()):
            self._run(ref, _STOP_SCRIPT)
            browser = ref()
            if browser is not None:
                self._inject(ref, browser.baseUrl)

    def _on_added(self, browser_id, *args):
        self._attach(browser_id)

    def _attach(self, browser_id):
        if browser_id in self._attached:
            return
        browser = self._controller.getBrowser(browser_id)
        if browser is None or not is_stronghold_page(getattr(browser, 'baseUrl', None)):
            return
        native = getattr(browser, '_WebBrowser__browser', None)
        script = getattr(native, 'script', None)
        if native is None or script is None:
            return
        # A weak reference to the Python WebBrowser, not to the native
        # provider: a native object need not accept weak references at all,
        # and the provider is looked up again at the moment it is used.
        ref = weakref.ref(browser)
        self._attached[browser_id] = ref
        _logger.info('attaching to browser %s: %s', browser_id, browser.baseUrl)

        # Once per browser. Subscribing on every page load, as the first
        # version did, stacked a handler per navigation.
        self._session.subscribe(
            script.onConsoleMessage,
            lambda *args: self._on_console(ref, *args))
        self._session.subscribe(
            browser.onReadyToShowContent,
            lambda url: self._inject(ref, url))
        # Already-loaded pages will not fire the event again.
        self._inject(ref, browser.baseUrl)

    def _inject(self, ref, url):
        # Checked again on every load: a browser that started on a Stronghold
        # page can navigate somewhere else.
        from unicum.extended_info import waits
        if not is_stronghold_page(url) or not self._settings.shows('stronghold'):
            return
        if waits(self._alt, self._settings, 'stronghold'):
            return
        generation = self._session.generation * 1000 + self._revision
        metric = self._settings.metric('stronghold')
        self._run(ref, content_script(generation, self._settings.label('stronghold') or '',
                                     metric is not None))

    def _on_console(self, ref, *args):
        # The native event passes (level, message, lineNumber, source, viewId).
        message = args[1] if len(args) > 1 else None
        if isinstance(message, basestring) and message.startswith(PROBE_PREFIX):
            _logger.info('page classes: %s', message[len(PROBE_PREFIX):])
            return
        names = parse_players(message)
        if names:
            _logger.info('page needs %s players: %s', len(names), ','.join(names))
            self._lookup.prefetch(
                names=names, on_ready=lambda: self._answer_players(ref, names))
            return
        tags = parse_need(message)
        if not tags:
            return
        _logger.info('page needs %s clans: %s', len(tags), ','.join(tags))
        # One /resolve?tags= answers the whole list: each tag's clan id and
        # the clan itself.
        self._lookup.prefetch(tags=tags, on_ready=lambda: self._answer(ref, tags))

    def _answer(self, ref, tags):
        # A tag the server never answered, because the request failed, is not
        # "no clan": the page would take an empty answer as final and never
        # ask again. It is asked for again later instead.
        failed = [tag for tag in tags if not self._lookup.knows_tag(tag)]
        if failed:
            _logger.info('no answer for %s clans, asking again in %ds', len(failed), _RETRY_SECONDS)
            self._session.callback(_RETRY_SECONDS, lambda: self._lookup.prefetch(
                tags=failed, on_ready=lambda: self._answer(ref, failed)))
        answers = {}
        for tag in tags:
            if tag in failed:
                continue
            clan_id = self._lookup.clan_id(tag)
            entry = self._lookup.get(CLANS, clan_id) if clan_id else None
            codes = []
            if entry is not None and self._settings.shows_flags('stronghold'):
                codes = entry.flags[:self._settings['maxFlags']]
            uris = [self._flags.data_uri(code) for code in codes]
            answers[tag] = {
                'flags': [uri for uri in uris if uri],
                'score': self._score(self._settings.rating(entry, 'stronghold')),
            }
        if not answers:
            return
        _logger.info('sending %s clans, %s with %s', len(answers),
                     sum(1 for a in answers.values() if a['score']), self._settings.label('stronghold'))
        self._run(ref, answers_script(answers))

    def _score(self, value):
        """A rating as this page should draw it: the mod's own badge, inlined.

        The same PNG the client draws in the skirmish room and over the
        tanks, handed over as bytes the way a flag is. Not a shape built in
        CSS beside it: that was the imitation, and an imitation of a 12px
        badge inherits the page's type and comes out half again as big in
        one panel and right in the other, which is what sent me measuring
        font sizes instead of sending the badge.

        `value` and `color` ride along so a page that cannot show the image
        still has something true to draw.
        """
        if value is None:
            return None
        metric = self._settings.metric('stronghold')
        color = self._scales.color(metric, value)
        if not color:
            return None
        score = {'value': value, 'color': color}
        try:
            from unicum import badge_png
            whole = int(round(value))
            data = badge_png.png(whole, color)
            score['image'] = 'data:image/png;base64,' + base64.b64encode(data)
            score['width'] = badge_png.width_of(whole)
            score['height'] = badge_png.HEIGHT
        except Exception:
            # The figure and its band still travel. A page drawing the
            # number on its colour is worse than the badge and much better
            # than nothing.
            _logger.exception('could not draw a badge for the page')
        return score

    def _answer_players(self, ref, names):
        """The same bargain `_answer` makes for clans, for the preview panel.

        A name the server never answered is not "no such player": the page
        would take an empty answer as final and never ask again, so it is
        asked for again later, exactly as a tag is.
        """
        failed = [name for name in names if not self._lookup.knows_name(name)]
        if failed:
            _logger.info('no answer for %s players, asking again in %ds',
                         len(failed), _RETRY_SECONDS)
            self._session.callback(_RETRY_SECONDS, lambda: self._lookup.prefetch(
                names=failed, on_ready=lambda: self._answer_players(ref, failed)))
        answers = {}
        for name in names:
            if name in failed:
                continue
            account_id = self._lookup.account_id(name)
            entry = self._lookup.get(PLAYERS, account_id) if account_id else None
            answers[name] = {'score': self._score(
                self._settings.rating(entry, 'stronghold'))}
        if not answers:
            return
        _logger.info('sending %s players, %s with %s', len(answers),
                     sum(1 for a in answers.values() if a['score']),
                     self._settings.label('stronghold'))
        self._run(ref, players_script(answers))

    def _remove_scripts(self):
        """Take the observer and every flag back out of the page on unload."""
        for ref in list(self._attached.values()):
            self._run(ref, _STOP_SCRIPT)
        self._attached.clear()

    @staticmethod
    def _run(ref, script):
        browser = ref()
        native = getattr(browser, '_WebBrowser__browser', None)
        if native is None:
            return
        try:
            native.loadURL(script)
        except Exception:
            _logger.exception('could not run script in the page')


def install(session, lookup, flags, scales, settings, alt=None):
    BrowserBridge(session, lookup, flags, scales, settings, alt).install()

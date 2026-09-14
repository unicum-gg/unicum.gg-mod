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

  page    web/stronghold.js finds every [TAG] leaf, keeps finding them as
          React re-renders, and reports the tags it has no answer for as
          `[unicum] need RASZ,TENTS`. It also folds the detachment list's
          redundant "Places" column into "Members". The details are there.
  python  asks the resolve endpoint for all the tags in one request, which
          answers with each clan, and sends its flags back as data: URIs.

data: URIs rather than unicum.gg's flag URLs, because those sit behind a bot
challenge that an <img> request cannot pass. The PNGs are already on disk.

Only Stronghold pages are touched. The same controller hosts every embedded
browser in the client -- the shop, the clan portal, event pages -- and none
of them are ours to script.
"""
import base64
import json
import logging
import os
import weakref

from helpers import dependency
from skeletons.gui.game_control import IBrowserController

from unicum.api.resolve import CLANS

_logger = logging.getLogger('unicum.browser')

# Every Stronghold page observed so far is served from a wgsh-* host, e.g.
# https://wgsh-woteu-static.wgcdn.co/auth/entry?...next=/#/battlerooms
_STRONGHOLD_HOST_MARK = '://wgsh-'

NEED_PREFIX = '[unicum] need '

# Scripts travel as javascript: URLs, which the browser percent-decodes, so
# nothing sent may contain '%' or '#'. The content script lives in its own
# file and travels base64-encoded, which has neither; the short scripts below
# and every value spliced into them -- tags, base64 -- stay clear of both.
_CONTENT_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), 'web', 'stronghold.js')

_STOP_SCRIPT = (
    "javascript:(function(){var U=window.__unicum;"
    "if(U&&U.stop){U.stop();}})();void(0);"
)


def is_stronghold_page(url):
    return bool(url) and _STRONGHOLD_HOST_MARK in url


def content_script(generation, path=_CONTENT_SCRIPT_PATH):
    """web/stronghold.js, ready to run as a javascript: URL.

    Read from disk each time, so reopening the Stronghold window picks up an
    edit to the script without a client restart; the bootstrap only watches
    .py files. The file body is wrapped in a function, which gives it its
    GENERATION argument and lets it `return` early.
    """
    with open(path, 'rb') as handle:
        body = handle.read().decode('ascii')
    source = '(function(GENERATION){\n%s\n})(%d);' % (body, int(generation))
    encoded = base64.b64encode(source.encode('ascii'))
    return "javascript:eval(atob('%s'));void(0);" % encoded


def flags_script(flags_by_tag):
    """Hand resolved flags to the content script: {tag: [data URI, ...]}.

    An empty list is still an answer, "no flag", so the page stops asking.
    """
    payload = json.dumps(flags_by_tag, sort_keys=True)
    return ("javascript:(function(){var U=window.__unicum;"
            "if(U){U.set(" + payload + ");}})();void(0);")


def parse_need(message):
    """Tags asked for by the content script, or None for any other message."""
    if not isinstance(message, basestring) or not message.startswith(NEED_PREFIX):
        return None
    tags = []
    for tag in message[len(NEED_PREFIX):].split(','):
        tag = tag.strip()
        if tag and len(tag) <= 6 and all(c.isalnum() or c in '-_' for c in tag):
            tags.append(tag)
    return tags


class BrowserBridge(object):
    """Keeps the content script running in every Stronghold page."""

    def __init__(self, session, lookup, flags):
        self._session = session
        self._lookup = lookup
        self._flags = flags
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
        if not is_stronghold_page(url):
            return
        self._run(ref, content_script(self._session.generation))

    def _on_console(self, ref, *args):
        # The native event passes (level, message, lineNumber, source, viewId).
        message = args[1] if len(args) > 1 else None
        tags = parse_need(message)
        if not tags:
            return
        _logger.info('page needs %s clans: %s', len(tags), ','.join(tags))
        # One /resolve?tags= answers the whole list: each tag's clan id and
        # the clan itself.
        self._lookup.prefetch(tags=tags, on_ready=lambda: self._answer(ref, tags))

    def _answer(self, ref, tags):
        flags = {}
        for tag in tags:
            clan_id = self._lookup.clan_id(tag)
            entry = self._lookup.get(CLANS, clan_id) if clan_id else None
            codes = entry.flags if entry is not None else []
            uris = [self._flags.data_uri(code) for code in codes]
            flags[tag] = [uri for uri in uris if uri]
        _logger.info('sending %s flags for %s clans',
                     sum(len(v) for v in flags.values()), len(flags))
        self._run(ref, flags_script(flags))

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


def install(session, lookup, flags):
    BrowserBridge(session, lookup, flags).install()

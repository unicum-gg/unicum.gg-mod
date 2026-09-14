"""Runs script inside the Stronghold pages of the embedded browser.

The Stronghold "Clan Battles" window is not Flash. BrowserController loads
the WGSH single-page app from wgsh-woteu-static.wgcdn.co into an embedded
CEF view, so the detachment list and its member panel are both DOM, and no
Python view model is involved. Reaching them means running script in the
page.

WebBrowser.executeJavascript is dead code in this build: it forwards to a
native method the provider does not have. The native provider does have
loadURL, and a `javascript:` URL runs in the current document. The page's
console comes back through the provider's onConsoleMessage event, which is
the return channel: inject, read the log, adjust, save. No restart.

Only Stronghold pages are touched. The same controller hosts every embedded
browser in the client -- the shop, the clan portal, event pages -- and none
of them are ours to script.
"""
import logging

from helpers import dependency
from skeletons.gui.game_control import IBrowserController

_logger = logging.getLogger('unicum.browser')

TAG = '[unicum]'

# Every Stronghold page observed so far is served from a wgsh-* host, e.g.
# https://wgsh-woteu-static.wgcdn.co/auth/entry?...next=/#/battlerooms
_STRONGHOLD_HOST_MARK = '://wgsh-'


def is_stronghold_page(url):
    return bool(url) and _STRONGHOLD_HOST_MARK in url

# Travels as a URL, so it stays on one line and avoids characters that a URL
# parser could take an interest in. No regex either: a clan tag is just a
# short leaf whose text is wrapped in brackets, and plain string tests are
# one less thing that can be mangled in transit.
#
# Reports where clan tags live in the DOM, with each hit's tag name, class and
# parent class, which is what the real injection needs to target.
_PROBE_JS = (
    "javascript:(function(){"
    "var all=document.getElementsByTagName('*'),hits=[],i,el,t,p;"
    "for(i=0;i<all.length;i++){"
    "el=all[i];"
    "if(el.children.length>0)continue;"
    "t=(el.textContent||'').replace(/^\\s+|\\s+$/g,'');"
    "if(t.length<3)continue;"
    "if(t.charAt(0)!=='[')continue;"
    "if(t.charAt(t.length-1)!==']')continue;"
    "if(t.length>9)continue;"
    "p=el;"
    "var d=0,attrs='',j,a;"
    "while(p&&d<5){"
    "for(j=0;j<p.attributes.length;j++){"
    "a=p.attributes[j];"
    "if(a.name==='class')continue;"
    "attrs+=' d'+d+':'+a.name+'='+a.value;"
    "}"
    "p=p.parentNode;d++;"
    "}"
    "hits.push(t+' >>'+attrs);"
    "if(hits.length>2)break;"
    "}"
    "console.log('%s rows='+hits.length+' :: '+hits.join(' || '));"
    "})();void(0);"
) % TAG


class BrowserBridge(object):
    """Keeps script running in every embedded browser the client opens."""

    def __init__(self, session):
        self._session = session
        self._controller = dependency.instance(IBrowserController)

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
        browser = self._controller.getBrowser(browser_id)
        if browser is None:
            return
        url = getattr(browser, 'baseUrl', None)
        if not is_stronghold_page(url):
            return
        _logger.info('attaching to browser %s: %s', browser_id, url)
        self._session.subscribe(
            browser.onReadyToShowContent,
            lambda url, b=browser: self._inject(b, url))
        # Already-loaded pages will not fire the event again.
        self._inject(browser, url)

    def _inject(self, browser, url):
        # Checked again on every load: a browser that started on a
        # Stronghold page can navigate somewhere else.
        if not is_stronghold_page(url):
            return
        native = getattr(browser, '_WebBrowser__browser', None)
        if native is None:
            return

        # The page's console is the only way to see what ran. Subscribing to
        # the native event gives it to us under our own logger name, instead
        # of mixed into the client's [WebBrowser (webapp)] noise.
        script = getattr(native, 'script', None)
        if script is not None and hasattr(script, 'onConsoleMessage'):
            self._session.subscribe(script.onConsoleMessage, _on_console)

        # WebBrowser.executeJavascript forwards to a native method this build
        # does not have, so it is dead code. loadURL is present though, and a
        # `javascript:` URL runs in the current document. The trailing
        # void(0) matters: an expression that returns a value would have its
        # result replace the page.
        try:
            native.loadURL(_PROBE_JS)
            _logger.info('loadURL(javascript:) accepted for %s', url)
        except Exception as error:
            _logger.info('loadURL(javascript:) rejected: %s', error)


def _on_console(*args):
    """Native console hook. Its arity is unverified, so take what comes."""
    _logger.info('page console: %s', ' | '.join(repr(a) for a in args))


def install(session):
    BrowserBridge(session).install()

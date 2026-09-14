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

  page    a content script finds every [TAG] leaf, and keeps finding them:
          the app is React, rows are re-rendered, and anything added once is
          gone at the next render, so a MutationObserver rescans. React also
          reuses a row for another clan by changing only its text, which
          would leave our flag next to the wrong tag and add another on
          every render, so each scan first prunes any flag that is not
          directly after the tag it was made for. Tags it has
          no answer for are reported as `[unicum] need RASZ,TENTS`.
  python  resolves each tag to a clan id, the id to its languages, the
          language to a flag, and sends the flags back as data: URIs.

data: URIs rather than unicum.gg's flag URLs, because those sit behind a bot
challenge that an <img> request cannot pass. The PNGs are already on disk.

Only Stronghold pages are touched. The same controller hosts every embedded
browser in the client -- the shop, the clan portal, event pages -- and none
of them are ours to script.
"""
import json
import logging
import urllib
import weakref

from helpers import dependency
from skeletons.gui.game_control import IBrowserController

from unicum import config
from unicum.api.languages import CLANS

_logger = logging.getLogger('unicum.browser')

# Every Stronghold page observed so far is served from a wgsh-* host, e.g.
# https://wgsh-woteu-static.wgcdn.co/auth/entry?...next=/#/battlerooms
_STRONGHOLD_HOST_MARK = '://wgsh-'

NEED_PREFIX = '[unicum] need '

# Scripts travel as javascript: URLs, which the browser percent-decodes. So
# they stay on one line and never contain '%' or '#'. Every value spliced in
# later -- tags, base64 -- is drawn from characters that are safe there.
#
# __GEN__ is the session generation. A reload injects a new script, which
# finds the previous one by its older generation and tears it down first, so
# there is never more than one observer and one set of flags in the page.
_CONTENT_SCRIPT = (
    "javascript:(function(){"
    "var G=__GEN__,U=window.__unicum;"
    "if(U&&U.v===G){U.scan();return;}"
    "if(U&&U.stop){U.stop();}"
    "var flags={},asked={},timer=null;"
    "function tagOf(el){"
    "if(el.children.length>0)return null;"
    "var t=(el.textContent||'').replace(/^\\s+|\\s+$/g,'');"
    "if(t.length<4||t.length>8)return null;"
    "if(t.charAt(0)!=='['||t.charAt(t.length-1)!==']')return null;"
    "return t.substring(1,t.length-1);"
    "}"
    "function prune(){"
    "var imgs=document.querySelectorAll('img[data-unicum-flag]'),i,img,prev;"
    "for(i=0;i<imgs.length;i++){"
    "img=imgs[i];prev=img.previousSibling;"
    "if(prev&&prev.nodeType===1&&prev.tagName==='SPAN'"
    "&&tagOf(prev)===img.getAttribute('data-unicum-flag'))continue;"
    "img.parentNode.removeChild(img);"
    "}"
    "}"
    "function scan(){"
    "prune();"
    "var spans=document.getElementsByTagName('span'),need=[],i,el,tag,next,img;"
    "for(i=0;i<spans.length;i++){"
    "el=spans[i];tag=tagOf(el);"
    "if(!tag)continue;"
    "if(!(tag in flags)){if(!asked[tag]){asked[tag]=1;need.push(tag);}continue;}"
    "if(!flags[tag])continue;"
    "next=el.nextSibling;"
    "if(next&&next.nodeType===1&&next.getAttribute('data-unicum-flag')===tag)continue;"
    "img=document.createElement('img');"
    "img.setAttribute('data-unicum-flag',tag);"
    "img.src=flags[tag];"
    "img.style.cssText='width:16px;height:12px;margin:0 0 0 4px;"
    "vertical-align:middle;display:inline-block';"
    "el.parentNode.insertBefore(img,next);"
    "}"
    "if(need.length){console.log('" + NEED_PREFIX + "'+need.join(','));}"
    "}"
    "var obs=new MutationObserver(function(){"
    "if(timer)return;"
    "timer=setTimeout(function(){timer=null;scan();},150);"
    "});"
    "obs.observe(document.body,{childList:true,subtree:true,characterData:true});"
    "window.__unicum={v:G,scan:scan,"
    "set:function(m){for(var k in m){flags[k]=m[k];}scan();},"
    "stop:function(){obs.disconnect();"
    "var old=document.querySelectorAll('img[data-unicum-flag]'),j;"
    "for(j=0;j<old.length;j++){old[j].parentNode.removeChild(old[j]);}"
    "window.__unicum=null;}};"
    "scan();"
    "})();void(0);"
)

_STOP_SCRIPT = (
    "javascript:(function(){var U=window.__unicum;"
    "if(U&&U.stop){U.stop();}})();void(0);"
)


def is_stronghold_page(url):
    return bool(url) and _STRONGHOLD_HOST_MARK in url


def content_script(generation):
    return _CONTENT_SCRIPT.replace('__GEN__', str(int(generation)))


def flags_script(flags_by_tag):
    """Hand resolved flags to the content script. '' means "no flag"."""
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


class ClanResolver(object):
    """Clan tag to clan id, the one thing the page does not carry.

    The languages endpoint is keyed by id, and a detachment row shows only
    the tag -- five ancestors up from it there is no id at all. Until the
    endpoint accepts tags, each one goes through GET /{region}/clans/{tag}
    once, and the answer is kept: a tag belongs to the same clan for as long
    as this session lasts.
    """

    def __init__(self, session, region):
        self._session = session
        self._region = region
        self._ids = {}
        self._waiting = {}

    def resolve(self, tags, on_ready):
        """Call on_ready({tag: clan id or None}) once every tag is known."""
        unknown = [t for t in tags if t not in self._ids]
        remaining = set(unknown)

        def finish():
            on_ready(dict((t, self._ids.get(t)) for t in tags))

        if not remaining:
            finish()
            return

        def settled(tag):
            remaining.discard(tag)
            if not remaining:
                finish()

        for tag in unknown:
            listeners = self._waiting.get(tag)
            if listeners is not None:
                listeners.append(settled)
                continue
            self._waiting[tag] = [settled]
            self._fetch(tag)

    def _fetch(self, tag):
        url = '%s/api/%s/clans/%s' % (config.API_BASE, self._region,
                                      urllib.quote(tag))

        def received(response):
            code = getattr(response, 'responseCode', None)
            if code == 200:
                self._ids[tag] = self._parse_id(tag, response)
            elif code == 404:
                self._ids[tag] = None
            else:
                # Not an answer about the clan: a timeout, a 403 from the bot
                # challenge, a 5xx. Remembering it as "no such clan" would keep
                # that clan flagless for the rest of the session, so it is left
                # unknown and asked for again next time the page needs it.
                _logger.warning('clan lookup for %s failed with HTTP %s', tag, code)
            for listener in self._waiting.pop(tag, ()):
                listener(tag)

        self._session.fetch(url, received, timeout=config.API_TIMEOUT)

    @staticmethod
    def _parse_id(tag, response):
        try:
            clan = json.loads(response.body).get('clan') or {}
            return int(clan['id'])
        except (TypeError, ValueError, KeyError):
            _logger.warning('no clan id in the answer for %s', tag)
            return None


class BrowserBridge(object):
    """Keeps the content script running in every Stronghold page."""

    def __init__(self, session, lookup, flags):
        self._session = session
        self._lookup = lookup
        self._flags = flags
        self._controller = dependency.instance(IBrowserController)
        self._resolver = ClanResolver(session, config.REGION)
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
        self._resolver.resolve(tags, lambda ids: self._answer(ref, ids))

    def _answer(self, ref, ids):
        clan_ids = [i for i in ids.values() if i]

        def ready():
            flags = {}
            for tag, clan_id in ids.items():
                entry = self._lookup.get(CLANS, clan_id) if clan_id else None
                code = entry.countries[0] if entry is not None and entry.countries else None
                flags[tag] = (self._flags.data_uri(code) if code else None) or ''
            _logger.info('sending %s flags for %s clans',
                         sum(1 for v in flags.values() if v), len(flags))
            self._run(ref, flags_script(flags))

        self._lookup.prefetch(clans=clan_ids, on_ready=ready)

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

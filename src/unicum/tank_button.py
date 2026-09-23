"""A unicum.gg button in the hangar's vehicle menu, with links for the tank.

The row of hexagons above the crew is Gameface, so the button is a module of
our own (res/gui/gameface/mods/unicum/TankButton/) that openwg_gameface
injects into the hangar, the way skill4ltu adds its own button there:

  res_map   res/mods/configs/res_map/unicum.json declares the layout
            UnicumTankButton; openwg_gameface adds it to the client's
            resource map at startup and restarts the client once when the
            map changes
  view      a child of VehicleMenuPresenter, added through its
            _getChildComponents, with a model that carries the injection
            (gf_mod_inject), the onItemClick command, and the menu's code
  code      the injected TankButton.js only loads web/hangar/tank_menu.js
            and .css, which this module puts in the model and puts again
            when either changes on disk: the menu hot reloads like the rest
  click     the button opens a menu; an entry opens its link in the player's
            browser

Links go to https://unicum.gg/<region>/tanks/<intCD>[/<tab>]: the site
redirects an id to the tank's page, keeping the path and the query. Each
carries UTM parameters, since a page opened from another application has no
Referer. "Open build" adds the vehicle's setup as the site's `setup` token
(build.py); "Share build" copies that link instead of opening it, tagged
apart so a shared link's visits can be told from the player's own. The AI
entries do what the site's own "Open in" menu does
(apps/web/src/components/page-ai-actions.tsx in unicum-gg/unicum.gg): every
page has a Markdown twin at <path>.md, and the model is handed that, with the
setup too, which the twin renders.

The same loader runs the garage's Twitch chat panel and the unicum.gg
account card above it (twitch_panel.py): their scripts and styles are put in
the model after the menu's, each script wrapped in a function of its own, and
their state rides in the model's `twitch` string.

Optional: without openwg_gameface, or before the client has restarted with
the layout in its resource map, there is no button and nothing else changes.

A hangar view outlives a reload of this package, so the command's handler
holds no code of it: like mods_list.py, it is eval of a string importing the
current module at click time, with the command's arguments as its locals.
Its models are kept on VehicleMenuPresenter for the same reason: a reload
finds the buttons already on screen and gives them the current code.
"""
import base64
import functools
import json
import logging
import urllib
import weakref
import zlib

import BigWorld
from CurrentVehicle import g_currentVehicle
from frameworks.wulf import ViewModel
from gui.impl.gen_utils import INVALID_RES_ID
from gui.impl.lobby.hangar.presenters.vehicle_menu_presenter import VehicleMenuPresenter
from gui.impl.pub.view_component import ViewComponent

from unicum import build, config, resources

_logger = logging.getLogger('unicum.tank_button')

FEATURE = 'UnicumTankButton'
_MODULE = 'coui://gui/gameface/mods/unicum/TankButton/TankButton.js'

# Package resources (resources.py): beside the code in development, inside the .wotmod once released.
_SOURCES = 'web/hangar'
_SCRIPT = _SOURCES + '/tank_menu.js'
_STYLE = _SOURCES + '/tank_menu.css'
_PANEL_SCRIPT = _SOURCES + '/twitch_panel.js'
_PANEL_STYLE = _SOURCES + '/twitch_panel.css'
_CARD_SCRIPT = _SOURCES + '/account_card.js'
_CARD_STYLE = _SOURCES + '/account_card.css'
_ICONS = _SOURCES + '/icons'
_ICONS_MARK = '__MENU_ICONS__'
_PANEL_ICONS = _SOURCES + '/panel_icons'
_PANEL_ICONS_MARK = '__PANEL_ICONS__'
_CHECK_SECONDS = 1.0

# Where live button models are kept across reloads of this package.
_REGISTRY = '_unicumTankButtonModels'

SITE_BASE = 'https://unicum.gg'

# Tab ids, as TankButton.js sends them, and their path on the tank's page.
TABS = {
    'specifications': '',
    'performances': '/performances',
    'marks': '/marks',
    'history': '/history',
    'videos': '/videos',
    'community': '/community',
}

# As the site builds them: the base URL, the query with the prompt under `q`,
# and whether the assistant's own reader opens a long address.
#
# The setup token carries the whole build -- every device, the crew's skills,
# the field modifications -- and runs to about 1500 characters. Scira opens
# that as it is (checked). Claude's reader refuses anything past roughly 250
# and answers that the URL is too long, which is no answer at all, so it is
# given the bare page and the token beside it, in the prompt: the address it
# has to open stays short, and the build is still there to be read. ChatGPT is
# given the same, not having been checked.
AI = {
    'chatgpt': ('https://chatgpt.com/', lambda q: [('hints', 'search'), ('prompt', q)], False),
    'claude': ('https://claude.ai/new', lambda q: [('q', q)], False),
    'scira': ('https://scira.ai/', lambda q: [('q', q)], True),
}

_PROMPT = 'Read this World of Tanks stats page and help me analyze it: %s'

# The same, for a reader that will not open the page with the build on it: the
# page as the vehicle comes, and the build written out beside it. In the
# client's own words rather than the site's token, which would have to be
# decoded before it said anything (build.plain_setup).
_PROMPT_WITH_SETUP = (_PROMPT + '\n\nThat page is the vehicle as it comes. Mine is set up as follows, '
                      'in the game\'s own names:\n\n%s')

# The command's arguments are the eval's locals: {'item': ..., 'text': ...}.
_ON_ITEM = functools.partial(
    eval, "__import__('unicum.tank_button', None, None, ['on_item']).on_item(locals())", {})

# Property indexes; gf_mod_inject adds ModInjectModel first.
_ENABLED = 1
_REVISION = 2
_SCRIPT_TEXT = 3
_STYLE_TEXT = 4
_TWITCH = 5


def _utm(content):
    return 'utm_source=wot-mod&utm_medium=hangar&utm_campaign=tank-menu&utm_content=%s' % content


def tank_url(int_cd, tab='specifications', setup=None, content=None, region=config.REGION):
    """A tank page on unicum.gg, by the tank's id."""
    query = ('setup=%s&' % setup if setup else '') + _client() + _utm(content or ('build' if setup else tab))
    return '%s/%s/tanks/%d%s?%s' % (SITE_BASE, region, int_cd, TABS[tab], query)


def support_url(content):
    """The unicum.gg support page, opened from `content` (which window asked)."""
    return '%s/support?%sutm_source=wot-mod&utm_medium=settings&utm_campaign=support&utm_content=%s' % (
        SITE_BASE, _client(), content)


def open_url(url):
    """A link in the player's own browser."""
    _logger.info('opening %s', url)
    BigWorld.wg_openWebBrowser(url)


def _client():
    """`client=ct&` on the Common Test client, whose vehicles the site keeps apart."""
    try:
        from constants import IS_CT
    except ImportError:
        return ''
    return 'client=ct&' if IS_CT else ''


def item_url(item, vehicle):
    """The link a menu entry opens for this gui Vehicle, or None for an unknown entry."""
    if item in TABS:
        return tank_url(vehicle.intCD, item)
    if item in ('build', 'share'):
        content = 'share-build' if item == 'share' else 'build'
        return tank_url(vehicle.intCD, setup=build.setup_token(vehicle), content=content)
    if item in AI:
        base, query, long_url = AI[item]
        written = None if long_url else build.plain_setup(vehicle)
        if written:
            prompt = _PROMPT_WITH_SETUP % (markdown_url(vehicle.intCD), written)
        else:
            # Long enough to carry it, or nothing to say: the page as it is.
            prompt = _PROMPT % markdown_url(vehicle.intCD,
                                            build.setup_token(vehicle) if long_url else None)
        return '%s?%s' % (base, urllib.urlencode(query(prompt)))
    return None


def markdown_url(int_cd, setup=None, region=config.REGION):
    """The tank page's Markdown twin, which the site serves for an id as for a slug."""
    return '%s/%s/tanks/%d.md%s' % (SITE_BASE, region, int_cd, '?setup=%s' % setup if setup else '')


def on_item(args):
    """A message from the menu or the Twitch panel: an entry picked, or a line for the log."""
    # Called from the hangar's command handler, which must never see our errors.
    try:
        _on_item(args)
    except Exception:
        _logger.exception('could not handle %r from the hangar', args)


def _on_item(args):
    item = args.get('item') if isinstance(args, dict) else None
    if item == 'log':
        _logger.info('menu: %s', args.get('text'))
        return
    if isinstance(item, basestring) and item.startswith(('twitch', 'account')):
        from unicum import twitch_panel
        twitch_panel.on_item(args)
        return
    open_item(item)


def live_models():
    """The loader models on screen, including those made by an earlier load of this package."""
    models = getattr(VehicleMenuPresenter, _REGISTRY, None)
    return list(models) if models is not None else []


def set_twitch(model, text):
    """Hand the Twitch panel its state; False on a model older than the property."""
    try:
        model._setString(_TWITCH, text)
        return True
    except Exception:
        _logger.debug('a loader model without the twitch property', exc_info=True)
        return False


def compose(parts):
    """One loader script from several, each in its own function, stopped together."""
    body = [u'var __parts = [];']
    for name, script in parts:
        body.append(u'try { __parts.push(["%s", (function () {\n%s\n})()]); } '
                    u'catch (error) { api.report("%s: " + error + " " + (error && error.stack)); }'
                    % (name, script, name))
    body.append(u'return { stop: function () { __parts.forEach(function (part) { '
                u'try { if (part[1]) { part[1].stop(); } } catch (error) { api.report(part[0] + " stop: " + error); } '
                u'}); } };')
    return u'\n'.join(body)


def panel_sources():
    """The files the Twitch panel is made of, to tell when it changed."""
    return [_PANEL_SCRIPT, _PANEL_STYLE] + _pngs(_PANEL_ICONS)


def panel_code():
    """The Twitch panel alone, as a loader runs it: (script, style)."""
    panel = _read(_PANEL_SCRIPT).replace(_PANEL_ICONS_MARK, json.dumps(_data_uris(_pngs(_PANEL_ICONS))))
    return compose([('twitch panel', panel)]), _read(_PANEL_STYLE)


def open_item(item):
    """What a menu entry does: its link for the selected tank, in the browser."""
    if not g_currentVehicle.isPresent():
        _logger.info('no tank selected, nothing to open')
        return
    url = item_url(item, g_currentVehicle.item)
    if url is None:
        _logger.warning('unknown tank menu entry %r', item)
        return
    if item == 'share':
        _share(url)
        return
    open_url(url)


def _share(url):
    """The build link in the clipboard, and a system message saying so."""
    from gui import SystemMessages
    from gui.shared.notifications import NotificationPriorityLevel
    from gui.shared.utils import copyToClipboard
    copyToClipboard(url)
    _logger.info('copied %s', url)
    # Medium, as the game's own information messages: without a priority the
    # message only lands in the notification centre, with no popup.
    SystemMessages.pushMessage(u'unicum.gg: build link copied to the clipboard.',
                               type=SystemMessages.SM_TYPE.Information,
                               priority=NotificationPriorityLevel.MEDIUM)


class TankButtonModel(ViewModel):
    __slots__ = ('onItemClick', )

    def __init__(self, properties=6, commands=1):
        super(TankButtonModel, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(TankButtonModel, self)._initialize()
        from openwg_gameface import gf_mod_inject
        gf_mod_inject(self, FEATURE, modules=[_MODULE])
        self._addBoolProperty('enabled', True)
        self._addNumberProperty('revision', 0)
        self._addStringProperty('script', '')
        self._addStringProperty('style', '')
        self._addStringProperty('twitch', '')
        self.onItemClick = self._addCommand('onItemClick')


class TankButton(object):

    def __init__(self, session, settings):
        self._session = session
        self._settings = settings
        self._stamps = None
        self._revision = 0
        self._script = self._style = ''

    def install(self):
        try:
            from openwg_gameface import res_id_by_key
        except ImportError:
            _logger.info('openwg_gameface not installed, no tank page button')
            return
        self._layout = res_id_by_key(FEATURE)
        if self._layout == INVALID_RES_ID:
            _logger.info('%s not in the resource map yet; there is a button after the next client start',
                         FEATURE)
            return
        self._session.patch(VehicleMenuPresenter, '_getChildComponents', self._wrap)
        self._settings.on_change(self._on_settings)
        self._check_sources()
        self._session.repeat(_CHECK_SECONDS, self._check_sources)
        _logger.info('installed in the hangar vehicle menu')

    @staticmethod
    def _models():
        models = getattr(VehicleMenuPresenter, _REGISTRY, None)
        if models is None:
            models = weakref.WeakSet()
            setattr(VehicleMenuPresenter, _REGISTRY, models)
        return models

    def _check_sources(self):
        """Put the menu's code in every button when it or its icons change on disk."""
        icons = _pngs(_ICONS)
        panel_icons = _pngs(_PANEL_ICONS)
        paths = [_SCRIPT, _STYLE, _PANEL_SCRIPT, _PANEL_STYLE, _CARD_SCRIPT, _CARD_STYLE] + icons + panel_icons
        # Inside a release every stamp is None, and the code is read once.
        stamps = tuple((path, resources.stamp(path)) for path in paths)
        if stamps == self._stamps:
            return
        self._stamps = stamps
        menu = _read(_SCRIPT).replace(_ICONS_MARK, json.dumps(_data_uris(icons)))
        uris = json.dumps(_data_uris(panel_icons))
        panel = _read(_PANEL_SCRIPT).replace(_PANEL_ICONS_MARK, uris)
        card = _read(_CARD_SCRIPT).replace(_PANEL_ICONS_MARK, uris)
        self._script = compose([('tank menu', menu)] + [(name, script) for name, script in
                                                        (('account card', card), ('twitch panel', panel)) if script])
        self._style = u'\n'.join((_read(_STYLE), _read(_CARD_STYLE), _read(_PANEL_STYLE)))
        # From the content, not the files' times: the icons can change what
        # the script says while its own file stays untouched.
        self._revision = zlib.crc32((self._script + self._style).encode('utf-8')) & 0x3fffffff
        for model in list(self._models()):
            self._load_code(model)

    def _load_code(self, model):
        try:
            model._setString(_SCRIPT_TEXT, self._script)
            model._setString(_STYLE_TEXT, self._style)
            model._setNumber(_REVISION, self._revision)
        except Exception:
            _logger.exception('could not update a tank menu button')

    def _wrap(self, original):

        def _getChildComponents(presenter):
            children = original(presenter)
            try:
                children = dict(children)
                children[self._layout] = self._make_view
            except Exception:
                _logger.exception('could not add the tank menu button')
            return children

        return _getChildComponents

    def _make_view(self):
        view = ViewComponent(layoutID=self._layout, model=TankButtonModel)
        model = view.getViewModel()
        model._setBool(_ENABLED, self._settings.shows_tank_button())
        self._load_code(model)
        model.onItemClick += _ON_ITEM
        self._models().add(model)
        return view

    def _on_settings(self):
        shown = self._settings.shows_tank_button()
        for model in list(self._models()):
            try:
                model._setBool(_ENABLED, shown)
            except Exception:
                _logger.exception('could not update a tank page button')


def _pngs(folder):
    return ['%s/%s' % (folder, name) for name in resources.listdir(folder) if name.endswith('.png')]


def _read(path):
    data = resources.read(path)
    return data.decode('utf-8') if data is not None else u''


def _data_uris(paths):
    """{name: data URI} for the menu's own icons, inlined in its script."""
    uris = {}
    for path in paths:
        data = resources.read(path)
        if data is not None:
            uris[path.rsplit('/', 1)[-1][:-len('.png')]] = 'data:image/png;base64,' + base64.b64encode(data)
    return uris


def install(session, settings):
    TankButton(session, settings).install()

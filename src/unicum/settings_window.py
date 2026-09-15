"""The settings in izeberg's modsSettingsApi window, when that mod is installed.

Optional: without gui.modsSettingsApi this does nothing, and settings.json
stays the way to change anything. With it, the window shows a page for the
mod (in CHAMPi's settings window too, which reads the same API), and every
change there is written to settings.json, the one source of truth.

The window only knows flat values, so each surface's switches are spelled
<surface>Flags, <surface>Rating and <surface>Average.

Two behaviours of the API (1.7.0) shape this:

  - setModTemplate resets the window's saved values whenever the template
    differs from the last one registered. The template is built from the
    current settings, so a reset lands on what settings.json already says.
  - Callbacks are added to an event and never removed by the API, so every
    reload of this package would stack one. The session removes its own on
    close, and a callback that outlives its session does nothing.
"""
import logging

from unicum.settings import AVERAGED, MAX_FLAGS, METRICS, SURFACES, WINDOWS

_logger = logging.getLogger('unicum.settings_window')

LINKAGE = 'gg.unicum'

_WINDOW_LABELS = {'recent': 'Last 30 days', 'total': 'Overall'}
_SURFACE_LABELS = {
    'contacts': 'Contacts list',
    'profile': 'Profile window title',
    'skirmishRoom': 'Skirmish room',
    'battle': 'Battle',
    'stronghold': 'Stronghold detachment list',
}

# The API has no sections, only labels and spacers in two columns. So a
# column per kind of setting, each surface named once on its own control,
# rather than a block per surface repeating "Flags" and "Rating".
_SPACER = 12

# Nor any rule, so a heading draws its own with em dashes: box-drawing
# characters are missing from the window's font and drew nothing.
_RULE = u'\u2014' * 16


def _heading(templates, text):
    return templates.createLabel(u'%s  %s' % (text.upper(), _RULE))


def template(values):
    """The API's page for these settings, showing `values`."""
    from gui.modsSettingsApi import templates
    window = to_window(values)
    period_tooltip = ('{HEADER}Rating period{/HEADER}{BODY}Last 30 days falls back to '
                      'overall while the 30-day value is not computed yet.{/BODY}')
    ratings = [
        _heading(templates, 'Ratings'),
        templates.createDropdown('Rating', 'metric', [metric.upper() for metric in METRICS], window['metric']),
        templates.createDropdown('Period', 'window', [_WINDOW_LABELS[w] for w in WINDOWS],
                                 window['window'], tooltip=period_tooltip),
        templates.createEmpty(_SPACER),
    ] + [
        templates.createCheckbox(_SURFACE_LABELS[surface], surface + 'Rating', window[surface + 'Rating'])
        for surface in SURFACES
    ] + [
        templates.createEmpty(_SPACER),
        _heading(templates, 'Averages'),
    ] + [
        templates.createCheckbox(_SURFACE_LABELS[surface], surface + 'Average', window[surface + 'Average'])
        for surface in AVERAGED
    ]
    flags = [
        _heading(templates, 'Flags'),
        templates.createNumericStepper('Per player or clan', 'maxFlags', window['maxFlags'], 1, MAX_FLAGS, 1),
        templates.createEmpty(_SPACER),
    ] + [
        templates.createCheckbox(_SURFACE_LABELS[surface], surface + 'Flags', window[surface + 'Flags'])
        for surface in SURFACES
    ]
    return {'modDisplayName': 'unicum.gg', 'enabled': values['enabled'],
            'column1': ratings, 'column2': flags}


def to_window(values):
    """What the window stores for these settings: flat, dropdowns by index."""
    window = {'enabled': values['enabled'], 'maxFlags': values['maxFlags'],
              'metric': METRICS.index(values['metric']), 'window': WINDOWS.index(values['window'])}
    for surface in SURFACES:
        window[surface + 'Flags'] = values[surface]['flags']
        window[surface + 'Rating'] = values[surface]['rating']
        if surface in AVERAGED:
            window[surface + 'Average'] = values[surface]['average']
    return window


def from_window(raw):
    """settings.json changes from what the window sends back."""
    changes = {}
    if isinstance(raw.get('enabled'), bool):
        changes['enabled'] = raw['enabled']
    if _index(raw.get('metric'), METRICS) is not None:
        changes['metric'] = METRICS[raw['metric']]
    if _index(raw.get('window'), WINDOWS) is not None:
        changes['window'] = WINDOWS[raw['window']]
    if isinstance(raw.get('maxFlags'), (int, float)) and not isinstance(raw.get('maxFlags'), bool):
        changes['maxFlags'] = int(raw['maxFlags'])
    for surface in SURFACES:
        section = {}
        for key in ('flags', 'rating', 'average'):
            value = raw.get(surface + key.capitalize())
            if isinstance(value, bool) and (key != 'average' or surface in AVERAGED):
                section[key] = value
        if section:
            changes[surface] = section
    return changes


def _index(value, options):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < len(options):
        return int(value)
    return None


class SettingsWindow(object):

    def __init__(self, session, settings):
        self._session = session
        self._settings = settings
        self._alive = True
        self._api = None

    def install(self):
        try:
            from gui.modsSettingsApi import g_modsSettingsApi
        except ImportError:
            _logger.info('modsSettingsApi not installed, settings.json only')
            return
        self._api = g_modsSettingsApi
        g_modsSettingsApi.setModTemplate(LINKAGE, template(self._settings.values()), self._on_window)
        self._session.on_close(self._remove)
        self._settings.on_change(self._on_settings)
        _logger.info('registered in modsSettingsApi as %s', LINKAGE)

    def _on_window(self, linkage, raw):
        if not self._alive or linkage != LINKAGE or not isinstance(raw, dict):
            return
        self._settings.update(from_window(raw))

    def _on_settings(self):
        """Keep the window in step with a hand edit of settings.json."""
        # The API answers with onSettingsChanged, which lands in _on_window
        # with values that change nothing.
        self._api.updateModSettings(LINKAGE, to_window(self._settings.values()))

    def _remove(self):
        self._alive = False
        instance = getattr(self._api, '_ModsSettingsApi__instance', None)
        event = getattr(instance, 'onSettingsChanged', None)
        try:
            event -= self._on_window
        except Exception:
            _logger.debug('could not unregister the settings callback', exc_info=True)


def install(session, settings):
    SettingsWindow(session, settings).install()

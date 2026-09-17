"""The settings in izeberg's modsSettingsApi window, when that mod is installed.

Optional: without gui.modsSettingsApi this does nothing, and settings.json
stays the way to change anything. With it, the window shows a page for the
mod (in CHAMPi's settings window too, which reads the same API), and every
change there is written to settings.json, the one source of truth.

The window only knows flat values, so each surface's switches are spelled
<surface>Flags, <surface>Rating and <surface>Average, and each battle mode's
mode<Mode>Allies and mode<Mode>Enemies.

Two behaviours of the API (1.7.0) shape this:

  - setModTemplate resets the window's saved values whenever the template
    differs from the last one registered. The template is built from the
    current settings, so a reset lands on what settings.json already says.
  - Callbacks are added to an event and never removed by the API, so every
    reload of this package would stack one. The session removes its own on
    close, and a callback that outlives its session does nothing.
"""
import logging

from unicum.settings import AVERAGED, MAX_FLAGS, METRICS, MODES, SURFACES, WINDOWS

_logger = logging.getLogger('unicum.settings_window')

LINKAGE = 'gg.unicum'

_WINDOW_LABELS = {'recent': 'Last 30 days', 'total': 'Overall'}
_MODE_LABELS = {
    'random': 'Random battles',
    'ranked': 'Ranked battles',
    'onslaught': 'Onslaught',
    'stronghold': 'Stronghold',
    'frontline': 'Frontline',
    'training': 'Training rooms',
    'other': 'Other modes',
}
# The API has no sections, only labels and spacers in two columns, one control
# a line. So the page is laid out by place: a block per screen of the game
# holding its own switches, the lobby's screens in the first column, the
# battle, the garage and Twitch in the second.
_SPACER = 12

_SURFACE_HEADINGS = {
    'contacts': 'Contacts list',
    'profile': 'Profile',
    'skirmishRoom': 'Skirmish room',
    'stronghold': 'Stronghold',
    'battleResults': 'Battle results',
}

# Nor any rule, so a heading draws its own with em dashes: box-drawing
# characters are missing from the window's font and drew nothing.
_RULE = u'\u2014' * 16


def _heading(templates, text):
    return templates.createLabel(u'%s  %s' % (text.upper(), _RULE))


# The line carrying a button: the Twitch section's Connect. Linking the account
# alone is the garage's account card (account_card.js).
CONNECT_VAR = 'twitchConnect'

_CONNECT_TOOLTIP = ('{HEADER}Twitch{/HEADER}{BODY}The channel is the one linked to your unicum.gg account. '
                    'Connect links this game to that account and your Twitch channel, in your browser: nothing '
                    'to type, you only confirm. Then the battle chat has a TO TWITCH receiver, and the garage '
                    'panel a field to write in your chat.{/BODY}')


def channel_label(channel, linked):
    """The Twitch section's channel line."""
    if not channel:
        return u'Channel: not linked'
    return u'Channel: %s' % channel if linked else u'Channel: %s (Connect to write in it)' % channel


def _button_line(templates, text, var, button, tooltip=None):
    # A label with a button: the API draws one on any component that names a
    # varName, which is what the button's callback reports.
    return dict(templates.createLabel(text, tooltip=tooltip), varName=var,
                button=templates.createButton(width=90, height=24, text=button))


def template(values, channel=u'', linked=False):
    """The API's page for these settings, showing `values` and the Twitch channel followed.

    `linked` is whether the Twitch chat can be written to.
    """
    from gui.modsSettingsApi import templates
    window = to_window(values)

    def checkbox(label, var, tooltip=None):
        return templates.createCheckbox(label, var, window[var], tooltip=tooltip)

    def surface_block(surface, average_label='Average'):
        block = [_heading(templates, _SURFACE_HEADINGS.get(surface, surface)),
                 checkbox('Rating', surface + 'Rating'), checkbox('Flags', surface + 'Flags')]
        if surface in AVERAGED:
            block.append(checkbox(average_label, surface + 'Average'))
        return block + [templates.createEmpty(_SPACER)]

    lobby = [
        _heading(templates, 'Stats'),
        templates.createDropdown('Rating', 'metric', [metric.upper() for metric in METRICS], window['metric']),
        templates.createDropdown('Period', 'window', [_WINDOW_LABELS[w] for w in WINDOWS], window['window'],
                                 tooltip='{HEADER}Rating period{/HEADER}{BODY}Last 30 days falls back to '
                                         'overall while the 30-day value is not computed yet.{/BODY}'),
        templates.createNumericStepper('Flags per player or clan', 'maxFlags', window['maxFlags'], 1, MAX_FLAGS, 1),
        templates.createEmpty(_SPACER),
    ]
    for surface in ('contacts', 'profile', 'skirmishRoom', 'stronghold', 'battleResults'):
        block = surface_block(surface)
        if surface == 'battleResults':
            block.insert(-1, checkbox('Only while Alt is held', 'altOnlyResults'))
        lobby.extend(block)

    battle = [
        _heading(templates, 'Battle'),
        checkbox('Rating', 'battleRating'),
        checkbox('Flags', 'battleFlags'),
        checkbox('Team average', 'battleAverage'),
        checkbox('Above tanks: only while Alt is held', 'altOnlyMarkers'),
        checkbox('Players list: only while Alt is held', 'altOnlyPanel'),
        checkbox('Tab screen: only while Alt is held', 'altOnlyTab',
                 tooltip='{HEADER}Tab screen{/HEADER}{BODY}Press Tab first, then Alt: Alt then Tab switches '
                         'windows. The random battles\' Tab screen shows no ratings either way.{/BODY}'),
        checkbox('Loading screen: only while Alt is held', 'altOnlyLoading'),
        templates.createEmpty(_SPACER / 2),
        templates.createLabel('Whose stats to show, per mode',
                              tooltip='{HEADER}Whose stats to show, per mode{/HEADER}{BODY}Untick enemies to '
                                      'hide the other team\'s ratings and flags in a mode, in ranked battles '
                                      'for instance. It applies everywhere in battle: players list, Tab, '
                                      'loading screen and above tanks.{/BODY}'),
    ]
    for mode in MODES:
        battle.extend([
            checkbox('%s: allies' % _MODE_LABELS[mode], _mode_key(mode, 'allies')),
            checkbox('%s: enemies' % _MODE_LABELS[mode], _mode_key(mode, 'enemies')),
        ])
    battle.extend([
        templates.createEmpty(_SPACER / 2),
        checkbox('Announce reloading', 'autoReload',
                 tooltip='{HEADER}Announce reloading{/HEADER}{BODY}Sends the "Reloading!" message to your team '
                         'by itself, as F8 does: after each shot, or once a magazine is empty. Reloads shorter '
                         'than the 5-second limit of the chat are not announced.{/BODY}'),
        templates.createEmpty(_SPACER),
        _heading(templates, 'Garage'),
        checkbox('Tank menu button', 'tankButton',
                 tooltip='{HEADER}Tank menu button{/HEADER}{BODY}A unicum.gg button beside the vehicle menu, '
                         'with links for the selected tank: its unicum.gg tabs, AI assistants and its '
                         'build.{/BODY}'),
        templates.createEmpty(_SPACER),
        _heading(templates, 'Twitch'),
        # Connect only while it has something to do: once the chat can be
        # written to, the line only says which channel it is.
        (templates.createLabel(channel_label(channel, linked), tooltip=_CONNECT_TOOLTIP) if linked else
         _button_line(templates, channel_label(channel, linked), CONNECT_VAR, 'Connect', _CONNECT_TOOLTIP)),
        checkbox('Chat in battle', 'twitchBattleChat'),
        checkbox('Chat panel in the garage', 'twitchGarage'),
    ])
    return {'modDisplayName': 'unicum.gg', 'enabled': values['enabled'],
            'column1': lobby, 'column2': battle}


def to_window(values):
    """What the window stores for these settings: flat, dropdowns by index."""
    window = {'enabled': values['enabled'], 'maxFlags': values['maxFlags'], 'tankButton': values['tankButton'],
              'autoReload': values['autoReload'],
              'altOnlyMarkers': values['altOnly']['markers'], 'altOnlyPanel': values['altOnly']['panel'],
              'altOnlyTab': values['altOnly']['tab'], 'altOnlyLoading': values['altOnly']['loading'],
              'altOnlyResults': values['altOnly']['results'],
              'twitchChannel': values['twitch']['channel'], 'twitchBattleChat': values['twitch']['battleChat'],
              'twitchGarage': values['twitch']['garage'],
              'metric': METRICS.index(values['metric']), 'window': WINDOWS.index(values['window'])}
    for mode in MODES:
        for team in ('allies', 'enemies'):
            window[_mode_key(mode, team)] = values['modes'][mode][team]
    for surface in SURFACES:
        window[surface + 'Flags'] = values[surface]['flags']
        window[surface + 'Rating'] = values[surface]['rating']
        if surface in AVERAGED:
            window[surface + 'Average'] = values[surface]['average']
    return window


def from_window(raw):
    """settings.json changes from what the window sends back."""
    changes = {}
    for key in ('enabled', 'tankButton', 'autoReload'):
        if isinstance(raw.get(key), bool):
            changes[key] = raw[key]
    alt_only = dict((key, raw['altOnly' + key.capitalize()]) for key in ('markers', 'panel', 'tab', 'loading', 'results')
                    if isinstance(raw.get('altOnly' + key.capitalize()), bool))
    if alt_only:
        changes['altOnly'] = alt_only
    twitch = {}
    if isinstance(raw.get('twitchChannel'), basestring):
        twitch['channel'] = raw['twitchChannel']
    if isinstance(raw.get('twitchBattleChat'), bool):
        twitch['battleChat'] = raw['twitchBattleChat']
    if isinstance(raw.get('twitchGarage'), bool):
        twitch['garage'] = raw['twitchGarage']
    if twitch:
        changes['twitch'] = twitch
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
    modes = {}
    for mode in MODES:
        teams = dict((team, raw[_mode_key(mode, team)]) for team in ('allies', 'enemies')
                     if isinstance(raw.get(_mode_key(mode, team)), bool))
        if teams:
            modes[mode] = teams
    if modes:
        changes['modes'] = modes
    return changes


def _mode_key(mode, team):
    return 'mode%s%s' % (mode[0].upper() + mode[1:], team.capitalize())


def _index(value, options):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < len(options):
        return int(value)
    return None


class SettingsWindow(object):

    def __init__(self, session, settings, link=None):
        self._session = session
        self._settings = settings
        self._link = link
        self._chat = None
        # (channel followed, Twitch chat writable, game linked, account name) as the page shows them.
        self._state = (u'', False, False, None)
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
                 linked and link.twitch == 'ready', linked, link.name if linked else None)
        if state == self._state:
            return
        self._state = state
        # A new template replaces the page; its callbacks are added again, so
        # the ones already on the API's events come off first.
        self._unregister()
        self._register()

    def _register(self):
        channel, writable, linked, name = self._state
        self._api.setModTemplate(LINKAGE, template(self._settings.values(), channel, writable),
                                 self._on_window, self._on_button)

    def _on_window(self, linkage, raw):
        if not self._alive or linkage != LINKAGE or not isinstance(raw, dict):
            return
        self._settings.update(from_window(raw))

    def _on_button(self, linkage, var_name, value=None):
        if not self._alive or linkage != LINKAGE or self._link is None:
            return
        if var_name == CONNECT_VAR:
            self._link.connect(_linked_notice)

    def _on_settings(self):
        """Keep the window in step with a hand edit of settings.json."""
        # The API answers with onSettingsChanged, which lands in _on_window
        # with values that change nothing.
        self._api.updateModSettings(LINKAGE, to_window(self._settings.values()))

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


def _linked_notice(name, twitch):
    """Tell the player, in the garage notifications, how linking ended."""
    from gui import SystemMessages
    if name is None:
        SystemMessages.pushMessage('unicum.gg: the game could not be linked. Try Connect again.',
                                   type=SystemMessages.SM_TYPE.Warning)
    else:
        SystemMessages.pushMessage('unicum.gg: linked to %s. Start a battle chat message with !t to write '
                                   'in your Twitch chat.' % name, type=SystemMessages.SM_TYPE.Information)


def install(session, settings, link=None):
    window = SettingsWindow(session, settings, link)
    window.install()
    return window

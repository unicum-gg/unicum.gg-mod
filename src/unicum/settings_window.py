"""The settings in izeberg's modsSettingsApi window, when that mod is installed.

Optional: without gui.modsSettingsApi this does nothing, and settings.json
stays the way to change anything. With it, the window shows a page for the
mod (in CHAMPi's settings window too, which reads the same API), and every
change there is written to settings.json, the one source of truth.

The window only knows flat values, each choice by the index of its option:
what a screen shows is <surface>Show (SHOW_CHOICES), whose stats a battle
mode shows mode<Mode> (TEAM_CHOICES), and when a screen shows them
altOnly<Screen> (WHEN_CHOICES).

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
# The API has two columns and no sections, one control a line. So the page is
# the game's two places: the garage in the first column, the battle in the
# second, each holding everything that happens there. Every line reads the
# same way: where, then a dropdown among the same options as its neighbours,
# all of one width. Not a radio button group: CHAMPi's window draws one as a
# row of buttons, but Aslain's Mod Menu as a column of radio buttons, four
# lines a choice.
_SPACER = 12

# Wide enough for the longest option, "Ratings and flags".
_CHOICE_WIDTH = 200

# (label, rating, flags): what a screen shows. A team or detachment average
# goes with the ratings, being one.
SHOW_CHOICES = (
    ('Ratings and flags', True, True),
    ('Ratings only', True, False),
    ('Flags only', False, True),
    ('Nothing', False, False),
)

# (label, allies, enemies): whose stats a battle mode shows.
TEAM_CHOICES = (
    ('Both teams', True, True),
    ('Allies only', True, False),
    ('Enemies only', False, True),
    ('Nobody', False, False),
)

# When a screen shows them: at once, or while the extended info key is held.
WHEN_CHOICES = ('Always', 'While Alt is held')

_SURFACE_LABELS = {
    'contacts': 'Contacts list',
    'profile': 'Profile',
    'skirmishRoom': 'Skirmish room',
    'stronghold': 'Stronghold',
    'battleResults': 'Battle results',
    'battle': 'In battle',
}
_GARAGE_SURFACES = ('contacts', 'profile', 'skirmishRoom', 'stronghold', 'battleResults')

# The battle's screens that can wait for Alt, and the altOnly key of each.
_ALT_SCREENS = (('markers', 'Above tanks'), ('panel', 'Players list'), ('tab', 'Tab screen'),
                ('loading', 'Loading screen'))
_ALT_KEYS = ('markers', 'panel', 'tab', 'loading', 'results')

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


# The account card's checkbox. Not a settings.json value: the card's own cross
# hides it for the Wargaming account logged in, in account.json, and this box
# is the way back, which the cross alone never offered.
CARD_VAR = 'accountCard'

# Labels the garage's notices send the player looking for, so a notice and the
# window cannot name the same box differently. The Twitch panel's notice once
# pointed at "Twitch chat in the garage", a box that never existed.
CARD_LABEL = 'unicum.gg account card'
GARAGE_CHAT_LABEL = 'Chat panel in the garage'


def template(values, channel=u'', linked=False, card_shown=True):
    """The API's page for these settings, showing `values` and the Twitch channel followed.

    `linked` is whether the Twitch chat can be written to, `card_shown` whether
    the account card shows for the account logged in.
    """
    from gui.modsSettingsApi import templates
    window = to_window(values, card_shown)

    def checkbox(label, var, tooltip=None):
        return templates.createCheckbox(label, var, window[var], tooltip=tooltip)

    def choice(label, var, options, tooltip=None):
        return templates.createDropdown(label, var, list(options), window[var], tooltip=tooltip, width=_CHOICE_WIDTH)

    def show(surface):
        return choice(_SURFACE_LABELS[surface], _show_key(surface), [c[0] for c in SHOW_CHOICES])

    garage = [
        _heading(templates, 'Garage'),
        choice('Rating', 'metric', [metric.upper() for metric in METRICS]),
        choice('Period', 'window', [_WINDOW_LABELS[w] for w in WINDOWS],
               tooltip='{HEADER}Rating period{/HEADER}{BODY}Last 30 days falls back to overall while the '
                       '30-day value is not computed yet.{/BODY}'),
        templates.createNumericStepper('Flags per player or clan', 'maxFlags', window['maxFlags'], 1, MAX_FLAGS, 1),
        templates.createEmpty(_SPACER),
    ]
    garage.extend(show(surface) for surface in _GARAGE_SURFACES)
    garage.extend([
        choice('Battle results: when', _alt_key('results'), WHEN_CHOICES),
        templates.createEmpty(_SPACER),
        checkbox('Tank menu button', 'tankButton',
                 tooltip='{HEADER}Tank menu button{/HEADER}{BODY}A unicum.gg button beside the vehicle menu, '
                         'with links for the selected tank: its unicum.gg tabs, AI assistants and its '
                         'build.{/BODY}'),
        checkbox(CARD_LABEL, CARD_VAR,
                 tooltip='{HEADER}' + CARD_LABEL + '{/HEADER}{BODY}The card under the mission cards that '
                         'links this game to your unicum.gg account, or says which one it is linked to. Its '
                         'cross hides it for the account logged in; tick this to bring it back.{/BODY}'),
        checkbox(GARAGE_CHAT_LABEL, 'twitchGarage'),
        # Connect only while it has something to do: once the chat can be
        # written to, the line only says which channel it is.
        (templates.createLabel(channel_label(channel, linked), tooltip=_CONNECT_TOOLTIP) if linked else
         _button_line(templates, channel_label(channel, linked), CONNECT_VAR, 'Connect', _CONNECT_TOOLTIP)),
    ])

    battle = [
        _heading(templates, 'Battle'),
        show('battle'),
        templates.createEmpty(_SPACER),
    ]
    battle.extend(choice(_MODE_LABELS[mode], _mode_key(mode), [c[0] for c in TEAM_CHOICES],
                         tooltip=_MODES_TOOLTIP if mode == MODES[0] else None) for mode in MODES)
    battle.append(templates.createEmpty(_SPACER))
    battle.extend(choice(label, _alt_key(key), WHEN_CHOICES, tooltip=_TAB_TOOLTIP if key == 'tab' else None)
                  for key, label in _ALT_SCREENS)
    battle.extend([
        templates.createEmpty(_SPACER),
        checkbox('Twitch chat in battle', 'twitchBattleChat'),
        checkbox('Announce reloading', 'autoReload',
                 tooltip='{HEADER}Announce reloading{/HEADER}{BODY}Sends the "Reloading!" message to your team '
                         'by itself, as F8 does: after each shot, or once a magazine is empty. Reloads shorter '
                         'than the 5-second limit of the chat are not announced.{/BODY}'),
    ])
    return {'modDisplayName': 'unicum.gg', 'enabled': values['enabled'],
            'column1': garage, 'column2': battle}


_MODES_TOOLTIP = ('{HEADER}Whose stats, per mode{/HEADER}{BODY}Enemies only or Nobody keep the other team\'s '
                  'ratings and flags out of a mode, ranked battles for instance. It applies everywhere in battle: '
                  'players list, Tab, loading screen and above tanks.{/BODY}')

_TAB_TOOLTIP = ('{HEADER}Tab screen{/HEADER}{BODY}Press Tab first, then Alt: Alt then Tab switches windows. The '
                'random battles\' Tab screen shows no ratings either way.{/BODY}')


def to_window(values, card_shown=True):
    """What the window stores for these settings: flat, choices by index."""
    window = {CARD_VAR: card_shown,
              'enabled': values['enabled'], 'maxFlags': values['maxFlags'], 'tankButton': values['tankButton'],
              'autoReload': values['autoReload'],
              'twitchChannel': values['twitch']['channel'], 'twitchBattleChat': values['twitch']['battleChat'],
              'twitchGarage': values['twitch']['garage'],
              'metric': METRICS.index(values['metric']), 'window': WINDOWS.index(values['window'])}
    for key in _ALT_KEYS:
        window[_alt_key(key)] = 1 if values['altOnly'][key] else 0
    for mode in MODES:
        teams = values['modes'][mode]
        window[_mode_key(mode)] = _choice_of(TEAM_CHOICES, teams['allies'], teams['enemies'])
    for surface in SURFACES:
        window[_show_key(surface)] = _choice_of(SHOW_CHOICES, values[surface]['rating'], values[surface]['flags'])
    return window


def from_window(raw):
    """settings.json changes from what the window sends back."""
    changes = {}
    for key in ('enabled', 'tankButton', 'autoReload'):
        if isinstance(raw.get(key), bool):
            changes[key] = raw[key]
    alt_only = dict((key, bool(raw[_alt_key(key)])) for key in _ALT_KEYS
                    if _index(raw.get(_alt_key(key)), WHEN_CHOICES) is not None)
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
        index = _index(raw.get(_show_key(surface)), SHOW_CHOICES)
        if index is not None:
            _, rating, flags = SHOW_CHOICES[index]
            changes[surface] = {'rating': rating, 'flags': flags}
            if surface in AVERAGED:
                changes[surface]['average'] = rating
    modes = {}
    for mode in MODES:
        index = _index(raw.get(_mode_key(mode)), TEAM_CHOICES)
        if index is not None:
            _, allies, enemies = TEAM_CHOICES[index]
            modes[mode] = {'allies': allies, 'enemies': enemies}
    if modes:
        changes['modes'] = modes
    return changes


def _show_key(surface):
    return surface + 'Show'


def _mode_key(mode):
    return 'mode%s' % (mode[0].upper() + mode[1:])


def _alt_key(key):
    return 'altOnly' + key.capitalize()


def _choice_of(choices, first, second):
    """The index of the (label, first, second) option in `choices` matching two switches."""
    for index, (_, a, b) in enumerate(choices):
        if a == first and b == second:
            return index
    return 0


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
        # (channel followed, Twitch chat writable, game linked, account name,
        # card shown) as the page shows them.
        self._state = (u'', False, False, None, True)
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
                 self._card_shown())
        if state == self._state:
            return
        self._state = state
        # A new template replaces the page; its callbacks are added again, so
        # the ones already on the API's events come off first.
        self._unregister()
        self._register()

    def _card_shown(self):
        return not (self._link is not None and self._link.card_hidden)

    def _register(self):
        channel, writable, linked, name, card_shown = self._state
        self._api.setModTemplate(LINKAGE, template(self._settings.values(), channel, writable, card_shown),
                                 self._on_window, self._on_button)
        # The API keeps its own copy of every value and sends it back as the
        # player's choice. For the card that copy can be stale (the card's
        # cross changes the truth without going through the window), and an
        # old "shown" coming back would undo the cross: so it is set to the
        # truth first.
        self._api.updateModSettings(LINKAGE, to_window(self._settings.values(), card_shown))

    def _on_window(self, linkage, raw):
        if not self._alive or linkage != LINKAGE or not isinstance(raw, dict):
            return
        wanted = raw.get(CARD_VAR)
        if isinstance(wanted, bool) and self._link is not None and wanted != self._card_shown():
            if wanted:
                self._link.show_card()
            else:
                self._link.hide_card()
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

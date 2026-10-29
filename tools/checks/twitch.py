"""Checks for the Twitch chat: reading IRC lines, what the battle chat shows, and its settings."""

from checks.common import check


def check_twitch():
    from unicum.settings import validate
    from unicum.settings_window.codec import from_window, to_window
    from unicum.twitch.protocol import Message, format_message, parse_line
    from unicum.twitch.queueing import ChatQueue, linked_channel, linked_url

    line = ('@badge-info=;color=#1E90FF;display-name=Some\\sOne;mod=0 '
            ':someone!someone@someone.tmi.twitch.tv PRIVMSG #unicum :gg <b>wp</b> & co')
    kind, message = parse_line(line)
    check('a chat line gives its display name, colour and text',
          kind == 'message' and message == Message('Some One', '#1E90FF', 'gg <b>wp</b> & co', (), 'someone'))
    check('without tags, the nick is the name', parse_line(
        ':viewer!viewer@viewer.tmi.twitch.tv PRIVMSG #unicum :hi')[1] == Message('viewer', None, 'hi', (), 'viewer'))
    check('a /me keeps its words', parse_line(
        ':viewer!v@v PRIVMSG #unicum :\x01ACTION waves\x01')[1].text == 'waves')
    check('a ping is answered with its server', parse_line('PING :tmi.twitch.tv') == ('ping', ':tmi.twitch.tv'))
    check('other lines are ignored', parse_line(':tmi.twitch.tv 001 justinfan1 :Welcome, GLHF!') is None)
    check('a colour that is not one is left out',
          parse_line('@color=red;display-name=X :x!x@x PRIVMSG #c :t')[1].color is None)

    html = format_message(Message('A<b>', None, 'x & <font>'))
    check('names and text cannot inject markup',
          'A&lt;b&gt;' in html and 'x &amp; &lt;font&gt;' in html and '<b>' not in html)
    check('the Glitch stands before the name when the icon is installed, else the word',
          format_message(Message('a', None, 'b'), icon=True).startswith(
              '<IMG SRC="img://gui/maps/icons/unicum/twitch.png"')
          and '>Twitch</font>' in format_message(Message('a', None, 'b')))
    check('a long message is cut', len(format_message(Message('a', None, u'x' * 500))) < 400)

    queue = ChatQueue()
    for index in range(4):
        queue.add(Message('a', None, str(index)), in_battle=True)
    check('a few messages are shown two at a time', [m.text for m in queue.take()] == ['0', '1'])
    queue = ChatQueue()
    for index in range(45):
        queue.add(Message('a', None, str(index)), in_battle=True)
    queue.add(Message('a', None, 'garage'), in_battle=False)
    taken = queue.take()
    check('what a battle loading held is caught up faster, the oldest dropped past the queue',
          [m.text for m in taken] == ['5', '6', '7', '8', '9'] and len(queue.pending) == 35)
    check('messages outside a battle are kept but not queued', queue.history[-1].text == 'garage')

    check_battle_opening()

    check('a channel is read from a name, "#Name" or its link',
          [validate({'twitch': {'channel': value}})['twitch']['channel'] for value in
           ('Unicum_GG', '#unicum_gg', 'https://www.twitch.tv/unicum_gg/', 'no spaces!', 42)] ==
          ['unicum_gg', 'unicum_gg', 'unicum_gg', '', ''])
    values = validate({'twitch': {'channel': 'unicum_gg', 'battleChat': False}})
    window = to_window(values)
    check('the channel and its switch go to the window and back',
          window['twitchChannel'] == 'unicum_gg' and window['twitchBattleChat'] is False
          and validate(dict(values, **from_window(window))) == values)

    check('the linked channel is read from the player answer',
          linked_channel({'twitchLogin': 'Unicum_GG'}) == 'unicum_gg' and linked_channel({'twitchLogin': None}) == ''
          and linked_channel([]) == '')
    check('the player is asked for by an escaped nickname',
          linked_url('https://unicum.gg/', 'eu', 'a b/c') == 'https://unicum.gg/api/eu/players/a%20b%2Fc')
    from unicum.runtime.session import Session
    from unicum.settings import Settings
    import os, tempfile
    settings = Settings(Session(generation=0), store=os.path.join(tempfile.mkdtemp(), 'settings.json'))
    check('without a typed channel, the linked one is followed',
          settings.twitch_channel() == '' and settings.twitch_channel('Linked') == 'linked')
    settings.update({'twitch': {'channel': 'typed'}})
    check('a typed channel wins over the linked one', settings.twitch_channel('linked') == 'typed')
    settings.update({'enabled': False})
    check('the mod off follows no channel', settings.twitch_channel('linked') == ''
          and not settings.shows_twitch_in_battle())


def check_battle_opening():
    """The chat a battle opens on: what was said before it, not an empty screen."""
    from unicum.twitch import queueing as twitch
    from unicum.twitch.protocol import Message
    from unicum.twitch.queueing import _REPLAY, _REPLAY_SECONDS, ChatQueue

    class Clock(object):
        """Stands in for the module's `time`, so an age can be arranged."""

        def __init__(self):
            self.now = 1000.0

        def time(self):
            return self.now

    clock = Clock()
    real, twitch.time = twitch.time, clock
    try:
        queue = ChatQueue()
        for index in range(_REPLAY + 5):
            queue.add(Message('a', None, str(index)), in_battle=False)
        queue.open_battle()
        check('a battle opens on the last of the chat, oldest first',
              [m.text for m in queue.pending] == [str(i) for i in range(5, _REPLAY + 5)])

        queue = ChatQueue()
        queue.add(Message('a', None, 'stale'), in_battle=False)
        clock.now += _REPLAY_SECONDS + 1.0
        queue.add(Message('a', None, 'fresh'), in_battle=False)
        queue.open_battle()
        check('chat from long before the battle is left out', [m.text for m in queue.pending] == ['fresh'])

        queue = ChatQueue()
        queue.add(Message('a', None, 'garage'), in_battle=False)
        queue.add(Message('a', None, 'loading'), in_battle=True)
        queue.open_battle()
        check('what arrived while the battle loaded is shown once, not twice',
              [m.text for m in queue.pending] == ['garage', 'loading'])

        queue = ChatQueue()
        queue.add(Message('a', None, 'not kept'), in_battle=True, keep=False)
        queue.open_battle()
        check('with nothing said before it, a battle opens on an empty chat', not queue.pending)
    finally:
        twitch.time = real

    check_loading_screen_hold()


def check_loading_screen_hold():
    """Nothing is written while the battle loads: that chat goes with the screen."""
    import os
    import tempfile
    from unicum.twitch import chat as twitch
    from unicum.runtime.session import Session
    from unicum.settings import Settings
    from unicum.twitch.chat import _LOADING_HOLD, TwitchChat
    from unicum.twitch.protocol import Message

    def loading(shown):
        return type('FiredEvent', (object,), {'ctx': {'isShown': shown}})()

    session = Session(generation=0)
    settings = Settings(session, store=os.path.join(tempfile.mkdtemp(), 'settings.json'))
    chat = TwitchChat(session, settings, None)
    shown = []
    chat._show = shown.extend
    in_battle, twitch._in_battle = twitch._in_battle, lambda: True
    chat_shown, twitch._battle_chat_shown = twitch._battle_chat_shown, lambda: True
    try:
        chat._queue.add(Message('a', None, 'from the garage'), in_battle=False)
        chat._on_avatar()
        chat._flush()
        check('nothing is written while the battle is still loading', not shown)
        chat._on_loading(loading(True))
        chat._flush()
        check('nor while its loading screen is up', not shown)
        chat._on_loading(loading(False))
        chat._flush()
        check('the chat a battle opens on arrives once the loading screen is gone',
              [m.text for m in shown] == ['from the garage'])

        del shown[:]
        chat._on_avatar()
        chat._loading_until -= _LOADING_HOLD + 1.0
        chat._queue.add(Message('a', None, 'later'), in_battle=True)
        chat._flush()
        check('a loading screen that never reports itself over cannot silence a whole battle',
              [m.text for m in shown] == ['later'])
    finally:
        twitch._in_battle = in_battle
        twitch._battle_chat_shown = chat_shown
        session.close()


def check_twitch_badges():
    from unicum.twitch.protocol import Message, format_message, parse_line
    from unicum.twitch_badges import ChatBadges, badges_url, parse_badges, read_badges, res_path

    line = '@badges=subscriber/12,moderator/1;display-name=M :m!m@m PRIVMSG #c :hey'
    check('a chat line names its badges', parse_line(line)[1].badges == ('subscriber/12', 'moderator/1'))
    check('a badge that cannot be a file name is left out',
          parse_badges('subscriber/12,../x/1,vip/,a.b/1,broadcaster/1') == ('subscriber/12', 'broadcaster/1'))
    check('no badges tag, no badges', parse_line(':v!v@v PRIVMSG #c :hi')[1].badges == ())

    badges = read_badges({'badges': [
        {'set': 'subscriber', 'version': '12', 'image1x': 'https://static-cdn.jtvnw.net/a/1', 'channel': True},
        {'set': 'moderator', 'version': '1', 'image1x': 'https://static-cdn.jtvnw.net/b/1', 'channel': False},
        {'set': 'evil', 'version': '1', 'image1x': 'file:///c:/x', 'channel': False},
        {'set': '..', 'version': '1', 'image1x': 'https://x/y', 'channel': False},
    ]})
    check('the badges answer keeps the images it can fetch and file',
          badges == {'subscriber/12': ('https://static-cdn.jtvnw.net/a/1', True),
                     'moderator/1': ('https://static-cdn.jtvnw.net/b/1', False)})
    check('every badge lies in the one folder, a channel image under its login, a global one once for all',
          res_path('license__', 'subscriber/12', True) == 'gui/maps/icons/unicum/twitch/badges/license__.subscriber.12.png'
          and res_path('license__', 'moderator/1', False) == 'gui/maps/icons/unicum/twitch/badges/global.moderator.1.png')
    check('the badges are asked for by channel',
          badges_url('https://unicum.gg/', 'license__') == 'https://unicum.gg/api/twitch/license__/badges')

    html = format_message(Message('M', None, 'hey', ('moderator/1',)), icon=True, badges='<IMG SRC="b"/>')
    check('badges are drawn between the Glitch and the name', '/> <IMG SRC="b"/><font' in html)

    class Session(object):
        def fetch(self, url, callback, timeout=None):
            pass

    known = set(['gui/maps/icons/unicum/twitch/badges/global.moderator.1.png'])
    chat = ChatBadges(Session(), drawable=lambda path: path in known)
    chat.follow('license__')
    markup = chat.markup(('moderator/1', 'vip/1'))
    check('only the badges the client can load are drawn',
          markup.count('<IMG') == 1 and 'global.moderator.1.png' in markup)


def check_linked_channel():
    """The lookup that tells the hangar card whether a Twitch is linked.

    Reported from Discord on 2026-09-24: a player linked Twitch with the game
    running and the card kept offering Connect. The site had answered "no
    channel" at startup, which is a perfectly good answer, and the lookup had
    treated it as final.
    """
    import sys
    from unicum.twitch.queueing import LinkedChannel

    class Player(object):
        name = 'okuni'

    class Clock(object):
        """Just enough BigWorld: who the player is, and what time it is."""

        now = 1000.0

        def player(self):
            return Player()

        def time(self):
            return self.now

    class Response(object):
        def __init__(self, body):
            self.responseCode, self.body = 200, body

    class Session(object):
        def __init__(self):
            self.waiting = []

        def fetch(self, url, callback, timeout=None):
            self.waiting.append(callback)

        def answer(self, body):
            self.waiting.pop()(Response(body))

    clock, session = Clock(), Session()
    held = sys.modules.get('BigWorld')
    sys.modules['BigWorld'] = clock
    try:
        channel = LinkedChannel(session)
        channel.get()
        check('the linked channel is asked for', len(session.waiting) == 1)

        session.answer('{"twitchLogin": null}')
        check('a player with no channel is not called linked', channel.get() == '')
        check('and nothing is asked again within the minute', len(session.waiting) == 0)

        clock.now += 61.0
        check('but the question comes back, so linking mid-session is noticed',
              channel.get() == '' and len(session.waiting) == 1)

        session.answer('{"twitchLogin": "Okuni"}')
        check('a channel, once found, is lower-cased and kept', channel.get() == 'okuni')

        clock.now += 600.0
        channel.get()
        check('and is not asked for again', len(session.waiting) == 0)
    finally:
        if held is None:
            sys.modules.pop('BigWorld', None)
        else:
            sys.modules['BigWorld'] = held


def check_twitch_send():
    import hashlib
    from unicum.game_link import connect_url, new_secret, read_me, secret_hash
    from unicum.twitch_send import command_text, failure_html, failure_of

    check('only a message starting with !t goes to Twitch, without the prefix',
          command_text('!t salut le chat ') == 'salut le chat' and command_text('!T gg') == 'gg'
          and command_text('gg wp') is None and command_text('!t   ') is None and command_text('!tank') is None)
    check('a message longer than Twitch takes is cut', len(command_text('!t ' + 'x' * 900)) == 500)

    class Response(object):
        def __init__(self, code, body):
            self.responseCode, self.body = code, body

    check('a posted message is no failure', failure_of(Response(200, '{"status": "sent"}')) is None)
    check('the reasons a message was not posted are told apart',
          failure_of(Response(401, '{"error": "not_linked"}')) == ('unlinked_client', None)
          and failure_of(Response(403, '{"status": "missing_scope"}')) == ('missing_scope', None)
          and failure_of(Response(200, '{"status": "dropped", "reason": "AutoMod"}')) == ('dropped', 'AutoMod')
          and failure_of(Response(502, 'not json')) == ('failed', None))
    check('a drop reason cannot inject markup', '&lt;b&gt;' in failure_html('dropped', '<b>'))

    secret = new_secret()
    check('the secret is 64 hex characters and only its SHA-256 travels',
          len(secret) == 64 and connect_url('https://unicum.gg/', 'eu', secret)
          == 'https://unicum.gg/api/connect/game/%s?region=eu' % hashlib.sha256(secret).hexdigest()
          and secret not in connect_url('https://unicum.gg', 'eu', secret) and len(secret_hash(secret)) == 64)
    # A token no hex secret can contain, so its absence before the fragment means something.
    url = connect_url('https://unicum.gg', 'na', secret, '1001', 'wgtoken')
    check('the Wargaming web token rides in the fragment, which no server receives',
          url.split('#')[1] == 'account_id=1001&token=wgtoken' and 'region=na' in url.split('#')[0]
          and 'wgtoken' not in url.split('#')[0])
    check('the account answer gives its name, Twitch access and channel, a refusal nothing',
          read_me(Response(200, '{"name": "Winnie", "twitch": "ready", "twitchLogin": "License__"}'))
          == ('Winnie', 'ready', 'license__')
          and read_me(Response(200, '{"name": "Winnie", "twitch": "not_linked", "twitchLogin": null}'))
          == ('Winnie', 'not_linked', None)
          and read_me(Response(401, '{"error": "not_linked"}')) is None)


def check_regions():
    from unicum.config import region_of
    check('the region follows the client realm, EU for any other',
          [region_of(r) for r in ('EU', 'NA', 'ASIA', 'CT', None)] == ['eu', 'na', 'asia', 'eu', 'eu'])


def check_twitch_receiver():
    from unicum.twitch_send import RECEIVER_ID, RECEIVER_ORDER, is_twitch_receiver, receiver_vo

    vo = receiver_vo()
    check('the Twitch receiver sorts after the client receivers on both sides',
          vo['orderIndex'] == RECEIVER_ORDER > 3 and vo['clientId'] == RECEIVER_ID and vo['isEnabled'])
    receivers = [(1, None, True), (2, None, True), (RECEIVER_ID, None, True)]
    check('only the Twitch receiver index sends to Twitch',
          is_twitch_receiver(receivers, 2) and not is_twitch_receiver(receivers, 0)
          and not is_twitch_receiver(receivers, 5) and not is_twitch_receiver(None, 0))


def check_echo_guard():
    from unicum.twitch.queueing import EchoGuard

    guard = EchoGuard()
    guard.expect(u'gg', 100.0)
    check('a message sent from the game is not shown again when Twitch echoes it',
          guard.consume('license__', 'license__', u'gg', 101.5)
          and not guard.consume('license__', 'license__', u'gg', 102.0))
    guard.expect(u'hello', 200.0)
    check('someone else saying the same is shown', not guard.consume('viewer', 'license__', u'hello', 201.0))
    check('an echo that never came is forgotten', not guard.consume('license__', 'license__', u'hello', 260.0))


def check_own_message():
    from unicum.twitch.protocol import (Message, appearance_of, own_message,
                                        parse_line)

    first = own_message(None, 'license__', u'gg')
    check('before any of their messages, the player wears the broadcaster badge',
          first == Message('license__', None, u'gg', ('broadcaster/1',), 'license__'))
    seen = parse_line('@badges=broadcaster/1,subscriber/12;color=#FF4500;display-name=License__ '
                      ':license__!license__@license__ PRIVMSG #license__ :hi')[1]
    shown = own_message(appearance_of(seen), 'license__', u'gg')
    check('then with the name, colour and badges Twitch last showed them with',
          shown == Message('License__', '#FF4500', u'gg', ('broadcaster/1', 'subscriber/12'), 'license__'))
    check('while the channel is unknown, the message still has a name',
          own_message(None, '', u'gg').name == 'You')
    check('an appearance from another channel is not used',
          own_message(appearance_of(seen), 'other', u'gg').badges == ('broadcaster/1',))


def check_twitch_panel():
    from unicum.twitch.protocol import Message
    from unicum.twitch_panel import state

    class Settings(object):
        def __getitem__(self, key):
            return {'garageCollapsed': True, 'garagePosition': None, 'garageSize': [400, 300]}

        def shows_twitch_in_garage(self):
            return True

    class Chat(object):
        channel = 'license__'
        joined = True
        history = [Message('Viewer', '#FF0000', u'gg', ('moderator/1',), 'viewer'),
                   Message('license__', None, u'thanks', (), 'license__')]

        def badge_sources(self, badges):
            return ['gui/maps/icons/unicum/twitch/badges/global.%s.png' % key.replace('/', '.') for key in badges]

    class Link(object):
        secret = None

    data = state(Settings(), Chat(), Link(), 'img://gui/maps/icons/unicum/twitch.png')
    check('the garage panel gets the chat with its badges as images, and the player own lines marked',
          data['messages'][0]['badges'] == ['img://gui/maps/icons/unicum/twitch/badges/global.moderator.1.png']
          and not data['messages'][0]['own'] and data['messages'][1]['own']
          and data['collapsed'] and not data['linked'] and data['channel'] == 'license__')
    check('the panel is told whether the chat is joined', data['joined'])
    check('the panel is told how large the player made it', data['size'] == [400, 300])


def check_panel_position():
    from unicum.settings import validate
    from unicum.twitch_panel import parse_position

    check('a dragged panel position is read in rem, and anything else puts it back in its place',
          parse_position('1200.4,310') == [1200, 310] and parse_position('') is None
          and parse_position('a,b') is None and parse_position(None) is None)
    check('the panel position survives the settings file, and a bad one is dropped',
          validate({'twitch': {'garagePosition': [40, 50]}})['twitch']['garagePosition'] == [40, 50]
          and validate({'twitch': {'garagePosition': 'left'}})['twitch']['garagePosition'] is None)


def check_panel_size():
    from unicum.settings import MAX_PANEL, MIN_PANEL, validate
    from unicum.twitch_panel import parse_size

    check('a panel dragged by its corner is read in rem, and anything else puts its size back',
          parse_size('400.6,301') == [401, 301] and parse_size('') is None
          and parse_size('wide,tall') is None and parse_size(None) is None)
    check('a size is held between what a chat needs and what a screen holds',
          parse_size('10,10') == list(MIN_PANEL) and parse_size('9000,9000') == list(MAX_PANEL))
    check('the panel size survives the settings file, and a bad one is dropped',
          validate({'twitch': {'garageSize': [400, 300]}})['twitch']['garageSize'] == [400, 300]
          and validate({'twitch': {'garageSize': 'large'}})['twitch']['garageSize'] is None)


def check_channel_label():
    from unicum.settings_window.page import channel_label

    check('the Twitch section names the channel followed, and says when writing needs Connect',
          channel_label(u'license__', True) == u'Channel: license__'
          and channel_label(u'license__', False) == u'Channel: license__ (Connect to write in it)'
          and channel_label(u'', False) == u'Channel: not linked')



def check_links_per_account(workdir):
    import json
    import os
    from unicum.game_link import GameLink, connect_url, read_store

    class Session(object):
        def repeat(self, interval, callback):
            pass

        def fetch(self, *args, **kwargs):
            pass

    secret_a, secret_b = 'a' * 64, 'b' * 64
    store = os.path.join(workdir, 'account-links.json')
    with open(store, 'w') as handle:
        json.dump({'secret': secret_a}, handle)
    logged_in = ['1001']
    link = GameLink(Session(), store=store, account_id=lambda: logged_in[0])
    link._follow_account()
    check('a link saved before links were per account goes to the first account logged in',
          link.secret == secret_a and read_store(json.load(open(store)))[0] == {'1001': secret_a})
    logged_in[0] = '2002'
    link._follow_account()
    check('another account logged in reads as not linked', link.secret is None)
    link._linked('2002', secret_b, 'Other', 'ready')
    link.hide_card()
    logged_in[0] = '1001'
    link._follow_account()
    check('switching back finds the first account link, and its card still shown',
          link.secret == secret_a and not link.card_hidden)
    logged_in[0] = '2002'
    link._follow_account()
    check('the card closed on one account stays closed for it', link.card_hidden and link.secret == secret_b)
    link.show_card()
    check('the settings window brings a closed card back', not link.card_hidden)
    logged_in[0] = '1001'
    link._follow_account()
    link.show_card()
    check('bringing back a card that is shown changes nothing', not link.card_hidden)
    logged_in[0] = '2002'
    link._follow_account()
    check('the site is told which account the game is logged in with',
          '&account=2002' in connect_url('https://unicum.gg', 'eu', secret_b, '2002', 't').split('#')[0])


def check_error_reporting():
    """The mod hands its logged exceptions to an error reporter, when one is installed."""
    import logging
    import sys
    from unicum import reporting
    from unicum.runtime.session import Session

    class FakeReporter(object):
        def __init__(self):
            self.calls = []

        def report_exception(self, mod_name, mod_version, exc_info, context, source):
            self.calls.append((mod_name, mod_version, exc_info[0], context, source))

        def ours(self):
            # The session this check installs, told apart from the mod's own,
            # which the harness started earlier and reports under its version.
            return [call for call in self.calls if call[1] == VERSION]

    VERSION = '9.9.9'
    session = Session(generation=0)
    logger = logging.getLogger('unicum.checks.reporting')
    reporter = FakeReporter()
    sys.modules['gui.mods.mod_error_reporter'] = reporter
    entry = type(sys)('gui.mods.mod_unicum')
    sys.modules['gui.mods.mod_unicum'] = entry
    try:
        reporting.install(session, VERSION)
        logger.info('nothing to report')
        check('a message without an exception is not reported', not reporter.ours())
        try:
            raise ValueError('boom')
        except ValueError:
            logger.exception('something failed')
        check('the released entry point is what an error is reported under',
              len(reporter.ours()) == 1 and reporter.ours()[0][0] == 'gui.mods.mod_unicum'
              and reporter.ours()[0][2] is ValueError)
        check('the report carries which logger failed and what it said',
              reporter.ours()[0][3]['logger'] == 'unicum.checks.reporting'
              and reporter.ours()[0][3]['message'] == 'something failed')

        del sys.modules['gui.mods.mod_unicum']
        sys.modules['gui.mods.mod_unicum_dev'] = type(sys)('gui.mods.mod_unicum_dev')
        try:
            raise ValueError('again')
        except ValueError:
            logger.exception('failed again')
        check('the development bootstrap is reported under its own name',
              reporter.ours()[-1][0] == 'gui.mods.mod_unicum_dev')

        del sys.modules['gui.mods.mod_error_reporter']
        before = len(reporter.ours())
        try:
            raise ValueError('nobody listening')
        except ValueError:
            logger.exception('failed with no reporter installed')
        check('without a reporter installed, nothing is sent', len(reporter.ours()) == before)

        session.close()
        sys.modules['gui.mods.mod_error_reporter'] = reporter
        try:
            raise ValueError('after the session')
        except ValueError:
            logger.exception('failed after the session closed')
        check('a closed session reports nothing more', len(reporter.ours()) == before)
    finally:
        session.close()
        for name in ('gui.mods.mod_error_reporter', 'gui.mods.mod_unicum', 'gui.mods.mod_unicum_dev'):
            sys.modules.pop(name, None)


def check_twitch_window():
    """The Twitch window on the queue screen: the garage panel's state, place and size."""
    from unicum.twitch_panel import PanelRect, parse_rect
    from unicum.twitch_window.placing import (parse_size, resized,
                                              window_place, window_state)
    from unicum.twitch_window.where import is_queue_route

    rect = parse_rect('1500,600,322,220,1920,1080,0,322,220,1552,700')
    check('the garage panel reports its box, the screen, the fold, its size in rem and its own place',
          rect == PanelRect(1500, 600, 322, 220, 1920, 1080, False, 322, 220, 1552, 700))
    check('a report of an older shape or with an empty box is left out',
          parse_rect('1500,600,322,220,1920,1080,0,322,220') is None
          and parse_rect('1,2,0,4,5,6,0,7,8,9,10') is None and parse_rect(None) is None)
    state = window_state({'position': [10, 20], 'size': [400, 300], 'collapsed': True}, rect, 'fr')
    check('the window holds the panel in its corner at the garage panel\'s size, folded as it is',
          state == {'position': None, 'size': [322, 220], 'collapsed': True, 'lang': 'fr', 'covered': False,
                    'moved': True})
    check('the reset arrow shows only for a place or a size of the player\'s',
          window_state({'position': None, 'size': None}, rect)['moved'] is False)
    check('a resize keeps to the panel\'s bounds and to the room on screen',
          resized((322, 220), (100, -500), (2000, 2000)) == (422, 120)
          and resized((322, 220), (5000, 5000), (700, 900)) == (700, 900))
    check('every battle queue opens the window, and nothing else does',
          is_queue_route('subScope/subLayer/battleQueue/battleQueue')
          and is_queue_route('subScope/subLayer/battleQueue/battleStrongholdsQueue')
          and not is_queue_route('subScope/subLayer/hangar') and not is_queue_route('battleQueue')
          and not is_queue_route('subScope/subLayer/comp7/hangar/{root}') and not is_queue_route(None))
    check('before the garage panel has said, the window keeps the settings\' size',
          window_state({'position': None, 'size': [400, 300]}, None)['size'] == [400, 300])
    check('the window goes where the garage panel was, in the window system\'s units',
          window_place(rect, (1280, 720), (215, 147)) == (1000, 400))
    check('it stays on screen',
          window_place(PanelRect(1900, 1000, 322, 220, 1920, 1080, False, 322, 220, 0, 0), (1920, 1080), (322, 220))
          == (1598, 860))
    check('without a report, the right of the screen, halfway down',
          window_place(None, (1920, 1080), (322, 220)) == (1552, 430))
    check('the page\'s size is read in pixels, and nothing else',
          parse_size('322,220') == (322, 220) and parse_size('0,5') is None and parse_size('x') is None)


def check_account_card_link():
    """The account card opens the player's own page, and only when it can.

    The hangar's own cards are clickable, and this one sat among them doing
    nothing: a card that says "Connected as X" and ignores a click reads as
    broken rather than as decoration.
    """
    import unicum.tank_button as tank_button
    from unicum.twitch_panel import TwitchPanel

    opened = []

    class Link(object):
        secret = 'a-secret'
        name = '_Winnie'

    link = Link()
    panel = TwitchPanel.__new__(TwitchPanel)
    panel._link = link
    panel._sender = None

    original, tank_button.open_url = tank_button.open_url, opened.append
    try:
        panel._act({'item': 'accountProfile', 'text': ''})
        check('the card opens the page of the account it names',
              len(opened) == 1 and '/eu/players/_Winnie' in opened[0])
        # Told apart from the garage menu's own link, which the site reads to
        # know where a visit came from.
        check('and says it came from the card',
              'utm_content=account-card' in opened[0])

        # A nickname is not always a URL: the site is addressed by the client's
        # own word for a player, so it has to survive the round trip.
        link.name = u'Sgt. Pepper'
        panel._act({'item': 'accountProfile', 'text': ''})
        check('a nickname that needs escaping still addresses the right page',
              'Sgt.%20Pepper' in opened[1] or 'Sgt.+Pepper' in opened[1])

        # Before the site has answered there is no name, and a page built on
        # nothing is a 404 served to someone who clicked a card that worked a
        # moment ago.
        link.name = None
        panel._act({'item': 'accountProfile', 'text': ''})
        check('with no name yet, nothing is opened', len(opened) == 2)
    finally:
        tank_button.open_url = original


def check_borrowed_decor():
    """The account card and the Twitch panel are drawn by the hangar.

    Painted by us they were both wrong, and in the same way: a fill and a
    border read off `background-color`, which is not where a hangar card keeps
    either. A card's fill is a border-image of the ui_kit's noise, and its
    hover moves three layers at once. So both wear the hangar's own classes and
    the values stay the client's. Those class names carry a per-build hash,
    which is why none of them may be written down in our own files.
    """
    import os
    import re
    from checks.common import REPO

    hangar = os.path.join(REPO, 'src', 'unicum', 'web', 'hangar')

    def read(name):
        with open(os.path.join(hangar, name)) as handle:
            return handle.read()

    card_js, card_css = read('account_card.js'), read('account_card.css')
    panel_js, panel_css = read('twitch_panel.js'), read('twitch_panel.css')

    # A hashed class name, as opposed to the documenting comments, which spell
    # the hash `<h>`, and to the stable halves the code looks the classes up by.
    hashed = re.compile(r'(?:Card|QuestCard)_[A-Za-z_]*[0-9a-f]{6,}\b')

    def written_down(text, css):
        bare = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        if not css:
            bare = re.sub(r'//[^\n]*', '', bare)
        return hashed.findall(bare)

    for name, text, css in (('account_card.css', card_css, True),
                            ('account_card.js', card_js, False),
                            ('twitch_panel.css', panel_css, True),
                            ('twitch_panel.js', panel_js, False)):
        check('%s names no class of the client\'s, which would last one build' % name,
              not written_down(text, css))

    # What they look up instead, each the half of a class name that survives a
    # build: the card takes all three layers and the two classes the hover
    # hangs off, the panel takes the one layer that draws a card at rest.
    for needle in ('hoverBg', 'Card_border_', 'Card_borderHelper_', 'Card_card__enabled_'):
        check('the card finds the decor by "%s"' % needle, needle in card_js)
    check('the panel takes the layer that draws a card at rest',
          'Card_borderHelper_' in panel_js and 'Card_borderHelper_' in panel_css)
    # A chat panel is not a button, and the hangar lights a card up because a
    # card opens something.
    check('and not the hover a card has', 'Card_card__enabled_' not in panel_js)

    # A mission card's edge at rest is this one layer: the Card_border_ beside
    # it is transparent until the pointer arrives and the veil is at 0. So the
    # panel wears the same border as the card only by writing no strength of
    # its own and taking the client's, whatever a build changes it to. Every
    # value tried here instead -- a widget's full strength, the .45 the client
    # gives a card under the pointer -- read as a lighter edge than the card's,
    # because that is exactly what it was.
    layer_rule = panel_css.split('[class*="Card_borderHelper_"]')[-1].split('}')[0]
    # Without the comments: the one above says the word out loud.
    layer_decls = re.sub(r'/\*.*?\*/', '', layer_rule, flags=re.S)
    check("the panel writes no strength of its own, so its border is the card's",
          'opacity' not in layer_decls)
    check('and pins it over its border rather than inside it', '-1rem' in layer_rule)

    # The panel's border holds its box: the list's height is the panel's less
    # the header, the footer and those two rems, so the border stays declared
    # and the fallback only colours it in.
    check('the panel keeps its border declared and transparent',
          'border: 1rem solid rgba(255, 255, 255, 0)' in panel_css)
    check('and the fallback colours it rather than adding one',
          'border-color:' in panel_css.split('__plain')[-1])

    # Nothing to borrow from: a hangar showing no mission, and the Twitch
    # window of the battle queue, which is a window of the client's own.
    check('the card falls back to a plain look of its own',
          'UnicumAccountCard__plain' in card_js and '.UnicumAccountCard__plain' in card_css)
    check('so does the panel',
          'UnicumTwitchPanel__plain' in panel_js and '.UnicumTwitchPanel__plain' in panel_css)

    # The borrowed layer covers the whole of either, so the content has to
    # claim its place over it: the hangar's own cards carry the same line.
    check('the card\'s content sits above the borrowed layers', 'z-index: 2' in card_css)
    check('the panel\'s does too', 'z-index: 2' in panel_css)

    # The hangar gives its mission column 241rem or 319rem depending on the
    # screen, so neither may hold a width of its own as the answer.
    check('both measure the hangar\'s mission column',
          'function column(' in card_js and 'function column(' in panel_js)

"""Checks for the Twitch chat: reading IRC lines, what the battle chat shows, and its settings."""

from checks.common import check


def check_twitch():
    from unicum.settings import validate
    from unicum.settings_window import from_window, to_window
    from unicum.twitch import ChatQueue, Message, format_message, linked_channel, linked_url, parse_line

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


def check_twitch_badges():
    from unicum.twitch import Message, format_message, parse_line
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
    check('the account answer gives its name and Twitch access, a refusal nothing',
          read_me(Response(200, '{"name": "Winnie", "twitch": "ready"}')) == ('Winnie', 'ready')
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
    from unicum.twitch import EchoGuard

    guard = EchoGuard()
    guard.expect(u'gg', 100.0)
    check('a message sent from the game is not shown again when Twitch echoes it',
          guard.consume('license__', 'license__', u'gg', 101.5)
          and not guard.consume('license__', 'license__', u'gg', 102.0))
    guard.expect(u'hello', 200.0)
    check('someone else saying the same is shown', not guard.consume('viewer', 'license__', u'hello', 201.0))
    check('an echo that never came is forgotten', not guard.consume('license__', 'license__', u'hello', 260.0))


def check_own_message():
    from unicum.twitch import Message, appearance_of, own_message, parse_line

    first = own_message(None, 'license__', u'gg')
    check('before any of their messages, the player wears the broadcaster badge',
          first == Message('license__', None, u'gg', ('broadcaster/1',), 'license__'))
    seen = parse_line('@badges=broadcaster/1,subscriber/12;color=#FF4500;display-name=License__ '
                      ':license__!license__@license__ PRIVMSG #license__ :hi')[1]
    shown = own_message(appearance_of(seen), 'license__', u'gg')
    check('then with the name, colour and badges Twitch last showed them with',
          shown == Message('License__', '#FF4500', u'gg', ('broadcaster/1', 'subscriber/12'), 'license__'))
    check('an appearance from another channel is not used',
          own_message(appearance_of(seen), 'other', u'gg').badges == ('broadcaster/1',))


def check_twitch_panel():
    from unicum.twitch import Message
    from unicum.twitch_panel import state

    class Settings(object):
        def __getitem__(self, key):
            return {'garageCollapsed': True, 'garagePosition': None}

        def shows_twitch_in_garage(self):
            return True

    class Chat(object):
        channel = 'license__'
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


def check_panel_position():
    from unicum.settings import validate
    from unicum.twitch_panel import parse_position

    check('a dragged panel position is read in rem, and anything else puts it back in its place',
          parse_position('1200.4,310') == [1200, 310] and parse_position('') is None
          and parse_position('a,b') is None and parse_position(None) is None)
    check('the panel position survives the settings file, and a bad one is dropped',
          validate({'twitch': {'garagePosition': [40, 50]}})['twitch']['garagePosition'] == [40, 50]
          and validate({'twitch': {'garagePosition': 'left'}})['twitch']['garagePosition'] is None)


def check_channel_label():
    from unicum.settings_window import channel_label

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
    check('the site is told which account the game is logged in with',
          '&account=2002' in connect_url('https://unicum.gg', 'eu', secret_b, '2002', 't').split('#')[0])

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
          kind == 'message' and message == Message('Some One', '#1E90FF', 'gg <b>wp</b> & co'))
    check('without tags, the nick is the name', parse_line(
        ':viewer!viewer@viewer.tmi.twitch.tv PRIVMSG #unicum :hi')[1] == Message('viewer', None, 'hi'))
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
    for index in range(15):
        queue.add(Message('a', None, str(index)), in_battle=True)
    queue.add(Message('a', None, 'garage'), in_battle=False)
    taken = queue.take()
    check('a burst is shown a few at a time, the oldest dropped past the queue',
          [m.text for m in taken] == ['5', '6'] and len(queue.pending) == 8)
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

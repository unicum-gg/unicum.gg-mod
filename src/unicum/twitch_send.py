"""Writing in the player's Twitch chat from the battle chat.

The battle chat gets one more receiver, "TO TWITCH", beside "TO TEAM" and
"TO ALL", which Tab cycles to like the others. A message sent to it, or any
message starting with `!t `, never reaches the players: it is taken out of
BattleMessengerView.sendMessageToChannel before the client sends it, and
posted to the player's own Twitch chat through unicum.gg
(POST /api/game/twitch/chat), which holds the Twitch token and sends it as
the player. It needs the account link (see game_link.py), and the receiver
only shows once the game is linked.

The view keeps its receivers twice, in step by index: a Python list sorted by
`order` (`__receivers`, of (clientID, settings, isEnabled)) and the Flash
side's, sorted by the VO's `orderIndex`. The Twitch receiver goes into both
with the same order, after the client's own (1 to 3), so every index still
points at the same receiver on both sides. The client rebuilds both lists
when a channel joins (addController) or its preferences change
(invalidateReceivers), so the receiver is added again after each.

The message shows in the battle chat as soon as it is sent (TwitchChat.echo),
and the copy Twitch sends back is left out; a failure adds a line under it.
"""
import json
import logging

from unicum import config

_logger = logging.getLogger('unicum.twitch_send')

PREFIX = '!t '

# A client id no channel uses, and an order after the client's receivers.
RECEIVER_ID = -2604
RECEIVER_NAME = 'unicumTwitch'
RECEIVER_ORDER = 100
_RECEIVER_COLOR = 0xB28CFF
_MAX_LENGTH = 500

_ERROR_COLOR = '#FF6A55'

_FAILURES = {
    'not_linked': 'Twitch is not linked to your unicum.gg account: use Connect in the unicum.gg settings.',
    'missing_scope': 'unicum.gg may not write in your Twitch chat yet: use Connect in the unicum.gg settings.',
    'dropped': 'Twitch did not post the message%s.',
    'failed': 'the message could not be sent to Twitch.',
    'unlinked_client': 'this game is not linked to unicum.gg: use Connect in the unicum.gg settings.',
}


def command_text(raw):
    """The message after `!t `, or None when the text is not for Twitch."""
    if not isinstance(raw, basestring) or not raw[:len(PREFIX)].lower() == PREFIX:
        return None
    text = raw[len(PREFIX):].strip()
    return text[:_MAX_LENGTH] if text else None


def failure_of(response):
    """None when the message was posted, else a key of _FAILURES and Twitch's reason."""
    code = getattr(response, 'responseCode', None)
    if code == 401:
        return 'unlinked_client', None
    try:
        payload = json.loads(response.body)
    except (TypeError, ValueError, AttributeError):
        return 'failed', None
    status = payload.get('status') if isinstance(payload, dict) else None
    if code == 200 and status == 'sent':
        return None
    if status in _FAILURES:
        return status, payload.get('reason')
    return 'failed', None


RECEIVER_LABEL = u'<font color="#9146FF">TO TWITCH : </font>'


def receiver_vo():
    """The Flash side's receiver, shaped like messenger_view._makeReceiverVO's."""
    return {'clientId': RECEIVER_ID, 'labelStr': RECEIVER_LABEL, 'orderIndex': RECEIVER_ORDER,
            'isByDefault': False, 'inputColor': _RECEIVER_COLOR, 'isEnabled': True}


def is_twitch_receiver(receivers, index):
    return receivers is not None and 0 <= index < len(receivers) and receivers[index][0] == RECEIVER_ID


def _receivers(view):
    return getattr(view, '_BattleMessengerView__receivers', None)


def failure_html(key, reason=None):
    text = _FAILURES[key]
    if key == 'dropped':
        text = text % (': %s' % reason if reason else '')
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return u"<font color='%s'>Twitch: %s</font>" % (_ERROR_COLOR, text)


class TwitchSender(object):

    def __init__(self, session, link, chat=None):
        self._session = session
        self._link = link
        self._chat = chat

    def install(self):
        try:
            from messenger.gui.Scaleform.view.battle.messenger_view import BattleMessengerView
        except ImportError:
            _logger.info('no battle messenger in this client, Twitch messages cannot be sent')
            return
        sender = self

        def build_send(original):
            def sendMessageToChannel(view, receiverIndex, rawMsgText):
                text = command_text(rawMsgText)
                if text is None and is_twitch_receiver(_receivers(view), receiverIndex):
                    text = (rawMsgText or '').strip()[:_MAX_LENGTH]
                    if not text:
                        view.setFocused(False)
                        return True
                if text is None:
                    return original(view, receiverIndex, rawMsgText)
                sender.send(text)
                return True
            return sendMessageToChannel

        def build_refresh(original):
            def refresh(view, *args, **kwargs):
                result = original(view, *args, **kwargs)
                if sender._link.secret:
                    sender._add_receiver(view)
                return result
            return refresh

        self._session.patch(BattleMessengerView, 'sendMessageToChannel', build_send)
        self._session.patch(BattleMessengerView, 'addController', build_refresh)
        self._session.patch(BattleMessengerView, 'invalidateReceivers', build_refresh)
        _logger.info('installed')

    @staticmethod
    def _add_receiver(view):
        receivers = _receivers(view)
        if receivers is None or any(receiver[0] == RECEIVER_ID for receiver in receivers):
            return
        try:
            from messenger.doc_loaders.settings_set import _ReceiverInBattle
            settings = _ReceiverInBattle(RECEIVER_NAME, RECEIVER_LABEL, [], [], RECEIVER_ORDER)
            receivers.append((RECEIVER_ID, settings, True))
            receivers.sort(key=lambda receiver: receiver[1].order)
            view.as_setReceiverS(receiver_vo(), False)
        except Exception:
            _logger.exception('could not add the Twitch receiver to the battle chat')

    def send(self, text):
        secret = self._link.secret
        if not secret:
            self._show(failure_html('unlinked_client'))
            return
        text = text if isinstance(text, unicode) else text.decode('utf-8', 'replace')
        if self._chat is not None:
            self._chat.echo(text)
        headers = {'Authorization': 'Bearer %s' % secret, 'Content-Type': 'application/json'}
        body = json.dumps({'message': text})

        def answered(response):
            failure = failure_of(response)
            if failure is not None:
                _logger.warning('Twitch message not posted: %s (HTTP %s)', failure[0],
                                getattr(response, 'responseCode', None))
                self._show(failure_html(*failure))

        self._session.fetch('%s/api/game/twitch/chat' % config.API_BASE.rstrip('/'), answered,
                            headers=headers, timeout=config.API_TIMEOUT, method='POST', post_data=body)

    @staticmethod
    def _show(html):
        try:
            from messenger import MessengerEntry
            MessengerEntry.g_instance.gui.addClientMessage(html)
        except Exception:
            _logger.exception('could not show a Twitch error in the battle chat')


def install(session, link, chat=None):
    TwitchSender(session, link, chat).install()

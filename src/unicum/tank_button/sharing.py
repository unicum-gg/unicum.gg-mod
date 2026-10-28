"""What the button offers, and what each choice does.

The menu, the prompts behind the AI entries, and the two ways a link leaves
the client: a browser opened on this machine, or a line put in the chat. The
list of choices is data, so the panel and the checks read the same list and
cannot disagree about what the button can do.
"""
from __future__ import absolute_import

import functools
import logging

import BigWorld
from CurrentVehicle import g_currentVehicle
from gui.impl.lobby.hangar.presenters.vehicle_menu_presenter import VehicleMenuPresenter
from unicum import build
from unicum.tank_button.urls import (item_url, markdown_url, player_ai_url,
                                     player_markdown_url, player_url,
                                     support_url, tank_ai_url, tank_url)

_logger = logging.getLogger('unicum.tank_button.sharing')

def open_url(url):
    """A link in the player's own browser."""
    _logger.info('opening %s', url)
    BigWorld.wg_openWebBrowser(url)

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

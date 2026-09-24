"""unicum.gg entries in the game's own right-click menus.

The client builds every context menu the same way, whatever it is attached
to: a handler derived from `AbstractContextMenuHandler` returns a list of
items from `_generateOptions`, and is told which one was picked through
`onOptionSelect`. The battle players panel derives from it too, so one pair
of patches reaches every menu in the game rather than one per surface.

What a menu is about is read from the handler rather than from a list of
classes. A player menu is one that carries a `databaseID` and a `userName`; a
vehicle menu is one carrying a compact descriptor, under whichever of four
names that version of the client happens to use. That is deliberate: the
class list would be twelve entries long, would name several that are only
reachable from modes most players never open, and would quietly miss the one
Wargaming adds next patch. Read this way, a menu nobody thought about gets
the entries for free, and a menu with nothing to identify gets none and is
left exactly as it was.

Nothing here may break a menu. A right-click that fails is a right-click the
player cannot use at all, so every step that touches the client's own data is
guarded and falls back to adding nothing.
"""
import logging

from unicum import tank_button

_logger = logging.getLogger('unicum.context_menu')

# Ours, and namespaced: `onOptionSelect` is given a bare string and the
# client's own ids are bare words, so a collision would fire the wrong action.
OPEN = 'unicum.open'
AI_MENU = 'unicum.ai'
AI_PREFIX = 'unicum.ai.'

# The assistants, in the order the garage menu lists them.
AI_ORDER = ('chatgpt', 'claude', 'scira')
AI_LABELS = {'chatgpt': 'ChatGPT', 'claude': 'Claude', 'scira': 'Scira'}

# No icon beside these, and not for want of trying. `iconType` takes a name
# the client's own menu SWF already knows, so it cannot be handed a file of
# ours; and an <IMG> in the label, which is how every flag and rating in this
# mod is drawn, is printed verbatim here -- these labels are plain text, not
# the htmlText the rest of the interface uses. The name carries the mark.
OPEN_LABEL = 'Open on unicum.gg'
AI_LABEL = 'Ask an AI'

# Where a vehicle's compact descriptor is kept, across the handlers that have
# one. The client is not consistent about this -- `_intCD` in the tech tree
# and the storage, `_vehicleCD` in the shop and the profile, `vehCD` in the
# hangar carousel, `_vehCD` in the comparison -- so all four are tried.
VEHICLE_ATTRS = ('vehCD', '_vehCD', '_vehicleCD', '_intCD')


def _player(handler):
    """The nickname a menu is about, else None.

    The nickname alone, because that is what a unicum.gg address is built
    from; the `databaseID` beside it in the garage handlers is the client's
    own key and would only narrow what this recognises.

    Two shapes, because the client has two. Garage menus put `userName`
    straight on the handler. The battle players panel keeps it inside an
    object of its own, under a private name, so its attributes are searched
    for anything carrying one rather than mangling the class name -- which
    would tie this to a class the client is free to rename.
    """
    try:
        nickname = getattr(handler, 'userName', None)
        if isinstance(nickname, basestring) and nickname:
            return nickname
        for value in vars(handler).values():
            nickname = getattr(value, 'userName', None)
            if isinstance(nickname, basestring) and nickname:
                return nickname
    except Exception:
        _logger.exception('could not read the player off %r', handler)
    return None


def _vehicle_cd(handler):
    """The compact descriptor for a menu about a vehicle, else None.

    Checked against the catalogue rather than trusted: `_intCD` is also what
    the module and equipment menus carry, and a shell's descriptor would
    otherwise be opened as though it were a tank.
    """
    for attr in VEHICLE_ATTRS:
        value = getattr(handler, attr, None)
        if not isinstance(value, int):
            continue
        try:
            from items import vehicles
            vehicles.getVehicleType(value)
            return value
        except Exception:
            continue
    return None


def _items():
    """The two entries: the page, and the assistants under one row."""
    make = _make_item
    if make is None:
        return []
    sub = [make(AI_PREFIX + name, AI_LABELS[name]) for name in AI_ORDER]
    return [make(OPEN, OPEN_LABEL), make(AI_MENU, AI_LABEL, optSubMenu=sub)]


_make_item = None
_settings = None


def _wanted(subject):
    """Whether the player asked for these entries on this kind of menu."""
    if _settings is None:
        return True
    kind = 'players' if subject[0] == 'player' else 'vehicles'
    try:
        return _settings.shows_context_menu(kind)
    except Exception:
        _logger.exception('could not read the context menu setting')
        return True


def _subject(handler):
    """('player', nickname) or ('vehicle', cd), else None.

    A player first: the battle panel's menu is about a player who happens to
    be in a tank, and the tank is the lesser half of what is being asked.
    """
    nickname = _player(handler)
    if nickname:
        return ('player', nickname)
    cd = _vehicle_cd(handler)
    if cd is not None:
        return ('vehicle', cd)
    return None


def _open(subject):
    """The address an entry opens, or None when there is nothing to open."""
    if subject[0] == 'player':
        return tank_button.player_url(subject[1])
    return tank_button.tank_url(subject[1], content='context-menu')


def _ask(subject, item):
    """The address an AI entry opens."""
    if subject[0] == 'player':
        return tank_button.player_ai_url(item, subject[1])
    return tank_button.tank_ai_url(item, subject[1])


def install(session, settings):
    """Add the entries to every context menu that can carry them."""
    global _make_item, _settings
    _settings = settings
    try:
        from gui.Scaleform.framework.managers.context_menu import (AbstractContextMenuHandler,
                                                                   ContextMenuManager)
    except ImportError:
        _logger.exception('no context menu manager; entries not installed')
        return
    _make_item = AbstractContextMenuHandler._makeItem

    # Everything the hooks need, held in the closure rather than read from the
    # module as they run. A patched method outlives the generation that made
    # it: the client keeps hold of it, a reload purges this module's globals
    # to None, and the next click then dies on `_logger.exception` before it
    # can reach anything. Captured here, an orphaned hook still works, and
    # still delegates.
    log = _logger
    links = tank_button
    subject_of = _subject
    wanted = _wanted
    items_for = _items

    def send_hook(original):

        def _sendOptionsToFlash(manager, options):
            try:
                handler = manager.getCurrentHandler()
                subject = subject_of(handler) if handler is not None else None
                if subject is not None and wanted(subject) and options:
                    added = items_for()
                    if added:
                        # A separator first, so ours read as a group rather
                        # than as two more of the client's own actions.
                        options = list(options) + [handler._makeSeparator()] + added
            except Exception:
                log.exception('could not add the entries to the menu')
            original(manager, options)

        return _sendOptionsToFlash

    def select_hook(original):

        def onOptionSelect(manager, optionId):
            try:
                if optionId == AI_MENU:
                    # The submenu's own row is a label rather than an action,
                    # and the handler would log it as an unknown option.
                    return
                if optionId == OPEN or (optionId or '').startswith(AI_PREFIX):
                    handler = manager.getCurrentHandler()
                    subject = subject_of(handler) if handler is not None else None
                    if subject is not None:
                        url = (_open(subject) if optionId == OPEN
                               else _ask(subject, optionId[len(AI_PREFIX):]))
                        if url:
                            links.open_url(url)
                    return
            except Exception:
                log.exception('could not act on %r', optionId)
                return
            original(manager, optionId)

        return onOptionSelect

    # On the manager rather than on the handler, which is where this started.
    # Every menu reaches Flash through this one object, while the handlers are
    # a dozen classes and at least one of them (BaseUserCMHandler, so every
    # player menu in the game) overrides `getOptions` and hid the patch
    # underneath it. `_sendOptionsToFlash` and `onOptionSelect` are the two
    # places nothing can get past.
    session.patch(ContextMenuManager, '_sendOptionsToFlash', send_hook)
    session.patch(ContextMenuManager, 'onOptionSelect', select_hook)
    _logger.info('context menu entries installed')

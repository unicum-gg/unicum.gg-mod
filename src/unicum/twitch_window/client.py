"""The Gameface classes this window is built out of.

Looked up rather than imported, because the client moves them between builds
and an import that fails at module level takes the whole mod down with it.
Kept in a file of its own so that the three halves above can each reach them
without reaching through one another.
"""
from __future__ import absolute_import

import logging

from unicum.layouts import layout_id

_logger = logging.getLogger('unicum.twitch_window.client')

def _model_class():
    from frameworks.wulf import ViewModel

    class TwitchWindowModel(ViewModel):
        __slots__ = ('onItemClick', '_first')

        def __init__(self, first):
            # (revision, script, style, twitch): the page's first state,
            # given before it loads rather than sent after.
            self._first = first
            super(TwitchWindowModel, self).__init__(properties=4, commands=1)

        def _initialize(self):
            super(TwitchWindowModel, self)._initialize()
            revision, script, style, twitch = self._first
            self._addNumberProperty('revision', revision)
            self._addStringProperty('script', script)
            self._addStringProperty('style', style)
            self._addStringProperty('twitch', twitch)
            self.onItemClick = self._addCommand('onItemClick')

    return TwitchWindowModel

def _window_class():
    from frameworks.wulf import WindowFlags
    from gui.impl.pub import WindowImpl

    class TwitchWindow(WindowImpl):
        __slots__ = ()

        def __init__(self, content, parent, layer):
            super(TwitchWindow, self).__init__(WindowFlags.WINDOW, content=content, layer=layer,
                                               parent=parent, name='unicumTwitchWindow')

        def _onReady(self):
            # Shown without the keyboard: the player's keys stay the game's
            # until they click in the panel's field.
            self.show(False)

    return TwitchWindow

def _main_window():
    """The client's main window once loaded, or None."""
    from frameworks.wulf import WindowStatus
    from helpers import dependency
    from skeletons.gui.impl import IGuiLoader
    main = dependency.instance(IGuiLoader).windowsManager.getMainWindow()
    if main is None or main.proxy is None or main.windowStatus != WindowStatus.LOADED:
        return None
    return main

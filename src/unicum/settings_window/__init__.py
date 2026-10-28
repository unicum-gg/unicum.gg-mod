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

from __future__ import absolute_import

from unicum.settings_window.window import SettingsWindow


def install(session, settings, link=None):
    window = SettingsWindow(session, settings, link)
    window.install()
    return window

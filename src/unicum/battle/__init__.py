"""Marks battle player names with where each player comes from.

The rating badge and the flags are drawn by each vehicle icon, lined up in a
column per team. The battle view (as3/src/unicum/VehicleMarkers.as) draws
them from the markup per vehicle and the order of each team published here:
in the players panel beside the icon, towards the middle of the screen; in a
Flash Tab screen outside each team's rows; on the loading screen beside the
icon. No row names its vehicle, so the order is taken from what the
statistics controller sends those screens (leftItemsIDs and rightItemsIDs).

Without the battle view they go after the player's name instead. The panels
are fed by the stats exchange: VehicleInfoComponent.addVehicleInfo builds one
dict per vehicle, and its `region` goes to AS3, where StatsUserProps and
formatPlayerName assign it as `htmlText`. So the flags go into that dict, and
nowhere else.

They used to go in one level lower, into player_format.getRegionCode. That
reached the same panels, but getRegionCode also feeds every other consumer
of a formatted name: the damage panel shows the player's own name as plain
text, so its <IMG> markup was drawn as characters, and playerFullName carried
it into markers and messages too. The stats exchange is where the name is
known to end up in an HTML field.

`region` is empty for anyone on their home realm, so on EU the field is
essentially always empty. A genuinely roaming player does have a code, and
it is not ours to drop: ours is appended to it.

Onslaught (comp7) gets flags too, at a cost in the log. Its VO leaves
`region` at null, typed Object, and DAAPIDataClass.fromHash reports a string
assigned there as "incorrect cast value ... to field with type Object" --
then assigns it anyway, so the flags draw. A player without flags is left
untouched, so only flagged players produce that line.

addVehicleInfo is synchronous and the answer comes over the network. So it
never waits: it uses whatever is cached, and the account ids it sees are
resolved in one batch just after. A vehicle drawn before the answer lands
picks its flags up the next time the arena updates it.

Each team's average rating goes after its name, in the Tab screen and on the
loading screen. Those names are set as plain text (team1TF.text), so the
badge only draws when the battle view (as3/src/unicum/TeamNamesHtml.as) is
loaded to re-set them as HTML; without it the average is a bare number. In a
Flash Tab table the view then moves it into the team's badge column.
"""

from __future__ import absolute_import

import logging

from unicum.battle.flags import BattleFlags

_logger = logging.getLogger('unicum.battle')


def install(session, lookup, flags, badges, settings, alt=None):
    if alt is None:
        from unicum.extended_info import ExtendedInfo
        alt = ExtendedInfo(session)
        alt.install()
    battle_flags = BattleFlags(session, lookup, flags, badges, settings)
    battle_flags.alt = alt
    battle_flags.install()
    alt.on_change(battle_flags._publish)
    try:
        from gui.Scaleform.daapi.view.battle.shared.markers2d import manager  # the client has them
    except ImportError:
        _logger.info('no vehicle markers in this client, no badge by the names above vehicles')
        return
    try:
        from unicum import name_markers
        name_markers.install(session, battle_flags)
    except Exception:
        # The rest of the battle surfaces stay.
        _logger.exception('could not install the badges by the names above vehicles')

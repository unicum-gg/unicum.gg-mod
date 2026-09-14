"""Temporary probe. Confirms where a flag can live in the Stronghold roster.

The name is composed in AS3 by CommonsLobby.formatPlayerName as

    prefix + userName + [clanAbbrev] + region + igrStr + suffix + eyeIcon

and handed to applyTextProps, which assigns `htmlText`. So <img> tags render
there: it is how the client draws its own anonymizer eye and IGR icons.

`region` is the field to use. getRegionCode returns None unless the player is
roaming from another realm, so it is empty for everyone on their home server,
it already means "where this player comes from", and writing to it leaves the
name, the rating and the earned badge alone.

Two things are checked at once:

  1. region    an <img> plus a [XX] marker, the shape the feature will ship
  2. fullName  a plain prefix, to show whether that field reaches the screen
               at all or only feeds tooltips

Delete this module once the answer is recorded.
"""
import logging

from gui.Scaleform.daapi.view.lobby.rally import vo_converters

_logger = logging.getLogger('unicum.probe')

# An icon that certainly ships with the client. Only whether it draws matters;
# real flags come later, sized to the line height.
_ICON = ("<img src='img://gui/maps/icons/library/qualifiers/16x16/gunner.png'"
         " width='16' height='16' vspace='-3'/>")


def install(session):
    # Patching the module attribute reaches the Stronghold roster, because
    # stronghold_battle_room -> makeStrongholdsSlotsVOs -> makeSlotsVOs ->
    # _getSlotsData resolves makePlayerVO as a module global at call time,
    # and makeSortiePlayerVO (the volunteers panel) does the same.
    #
    # rally_dps does `from ... import makePlayerVO` instead, so its binding
    # is unaffected. That is deliberate: those call sites feed the squad and
    # unit windows, which this feature has no business touching.
    session.patch(vo_converters, 'makePlayerVO', _wrap)
    _logger.info('probe installed on vo_converters.makePlayerVO')


def _wrap(original):

    def makePlayerVO(pInfo, user, colorGetter, isPlayerSpeaking=False,
                     isIncludeAccountWTR=False):
        vo = original(pInfo, user, colorGetter, isPlayerSpeaking,
                      isIncludeAccountWTR)
        _logger.info('roster row: dbID=%s clanDBID=%s clanAbbrev=%s '
                     'region=%r name=%r',
                     getattr(pInfo, 'dbID', None),
                     getattr(pInfo, 'clanDBID', None),
                     getattr(pInfo, 'clanAbbrev', None),
                     vo.get('region'),
                     vo.get('fullName'))

        # Appended, not assigned: a genuinely roaming player already has a
        # region code here and it is not ours to drop.
        vo['region'] = '%s%s[XX]' % (vo.get('region') or '', _ICON)
        vo['fullName'] = 'FN:' + (vo.get('fullName') or '')
        return vo

    return makePlayerVO

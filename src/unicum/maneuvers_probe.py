"""TEMPORAIRE -- a retirer apres la validation des Manoeuvres.

Demande au client le jeton wgcg (celui que le client obtient en echangeant un
SPA token, et que l'app embarquee des Manoeuvres envoie en `X-Access-Token`) et
l'ecrit sur le disque pour que la lecture des deux classements puisse etre
validee depuis l'exterieur.

N'envoie rien, ne patche rien, ne touche a aucune surface du jeu.
"""
from __future__ import absolute_import

import json
import logging
import os

_logger = logging.getLogger('unicum.maneuvers_probe')

OUT = os.path.join(
    os.environ.get('TEMP', '.'),
    'claude', 'c34b64f5b6d05741', '7166cd55-8803-4d18-809c-5b83de3b8eaa',
    'scratchpad', 'wgcg_token.json',
)

# Laisse le controleur web finir sa connexion avant de lui demander le jeton.
_DELAY = 8.0


def _write(payload):
    try:
        folder = os.path.dirname(OUT)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(OUT, 'wb') as handle:
            handle.write(json.dumps(payload).encode('utf-8'))
        _logger.info('maneuvers_probe: ecrit dans %s', OUT)
    except Exception:
        _logger.exception('maneuvers_probe: ecriture impossible')


def _ask(session):
    try:
        from helpers import dependency, time_utils
        from skeletons.gui.web import IWebController

        controller = dependency.instance(IWebController)

        def received(data):
            if not session.alive:
                return
            if data is None or not getattr(data, 'accessToken', None):
                _logger.warning('maneuvers_probe: le client n a pas rendu de jeton')
                _write({'ok': False, 'reason': 'no_token'})
                return
            now = time_utils.getServerUTCTime()
            _write({
                'ok': True,
                'token': str(data.accessToken),
                'expiresAt': float(data.expiresAt),
                'now': float(now),
                'secondsLeft': float(data.expiresAt) - float(now),
            })
            _logger.info(
                'maneuvers_probe: jeton obtenu, il reste %.0f s',
                float(data.expiresAt) - float(now),
            )

        _logger.info('maneuvers_probe: demande du jeton wgcg')
        controller.getAccessTokenData(False)(received)
    except Exception:
        _logger.exception('maneuvers_probe: echec de la demande')
        _write({'ok': False, 'reason': 'exception'})


def install(session):
    """Demande le jeton une fois, peu apres le demarrage."""
    session.callback(_DELAY, lambda: _ask(session))

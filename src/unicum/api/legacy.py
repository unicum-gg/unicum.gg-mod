"""Answers in the /resolve shape, from a server that does not have /resolve.

Temporary. unicum.gg shipped a languages-only batch endpoint first, and
/resolve replaces it; until every server the mod talks to has /resolve, the
lookup falls back to this on a 404 so flags keep drawing. Ratings are simply
absent from what it produces. Delete it once /resolve is deployed.

The old way, for one batch:

  tags     GET /{region}/clans/{tag}, one per tag, for the clan id
  ids      GET /{region}/languages/resolve?players=...&clans=..., at most
           100 per kind per request, tag-resolved clans included
"""
import json
import logging
import urllib

from unicum import config

_logger = logging.getLogger('unicum.api')

_CHUNK = 100


def parse(response, what):
    """The JSON object of a 200, or None for anything that is not an answer.

    None is kept apart from an empty answer on purpose. A timeout, a 5xx or
    the bot challenge's 403 says nothing about the players asked for, and
    caching it as "unknown" is what once made every flag vanish while the
    API was unreachable.
    """
    code = getattr(response, 'responseCode', None)
    if code != 200:
        _logger.warning('%s failed with HTTP %s', what, code)
        return None
    try:
        payload = json.loads(response.body)
    except (TypeError, ValueError):
        _logger.warning('%s returned a body that is not JSON', what)
        return None
    return payload if isinstance(payload, dict) else None


def fetch(session, api_base, region, batch, done):
    """Call done(payload) once with {players, clans, tags}, or done(None)."""
    state = {'tags': {}, 'failed': False, 'pending': len(batch['tags'])}

    def tag_answered(tag, response):
        code = getattr(response, 'responseCode', None)
        if code == 200:
            clan = (parse(response, 'clan lookup') or {}).get('clan') or {}
            if clan.get('id'):
                state['tags'][tag] = int(clan['id'])
        elif code != 404:
            _logger.warning('clan lookup for %s failed with HTTP %s', tag, code)
            state['failed'] = True
        state['pending'] -= 1
        if state['pending'] == 0:
            after_tags()

    def after_tags():
        if state['failed']:
            done(None)
            return
        clans = list(batch['clans'])
        clans.extend(i for i in state['tags'].values() if i not in clans)
        _languages(session, api_base, region, list(batch['players']), clans,
                   lambda payload: done(None if payload is None else dict(
                       payload, tags=state['tags'])))

    if not batch['tags']:
        after_tags()
        return
    for tag in batch['tags']:
        url = '%s/api/%s/clans/%s' % (api_base, region, urllib.quote(tag, safe=''))
        session.fetch(url, lambda response, tag=tag: tag_answered(tag, response),
                      timeout=config.API_TIMEOUT)


def _languages(session, api_base, region, players, clans, done):
    """languages/resolve in requests of at most 100 per kind, merged."""
    requests = []
    offset = 0
    while offset < max(len(players), len(clans)):
        requests.append((players[offset:offset + _CHUNK], clans[offset:offset + _CHUNK]))
        offset += _CHUNK
    if not requests:
        done({'players': {}, 'clans': {}})
        return
    merged = {'players': {}, 'clans': {}}
    state = {'pending': len(requests), 'failed': False}

    def answered(response):
        payload = parse(response, 'languages/resolve')
        if payload is None:
            state['failed'] = True
        else:
            merged['players'].update(payload.get('players') or {})
            merged['clans'].update(payload.get('clans') or {})
        state['pending'] -= 1
        if state['pending'] == 0:
            done(None if state['failed'] else merged)

    for chunk_players, chunk_clans in requests:
        parts = []
        if chunk_players:
            parts.append('players=' + ','.join(str(i) for i in chunk_players))
        if chunk_clans:
            parts.append('clans=' + ','.join(str(i) for i in chunk_clans))
        url = '%s/api/%s/languages/resolve?%s' % (api_base, region, '&'.join(parts))
        session.fetch(url, answered, timeout=config.API_TIMEOUT)

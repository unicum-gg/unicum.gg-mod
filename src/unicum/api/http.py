"""Reading unicum.gg's JSON answers."""
import json
import logging

_logger = logging.getLogger('unicum.api')


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


def said(body):
    """What the server put in the body of a refusal, short enough to log.

    The status code alone was not enough: a 400 repeated for a whole evening
    without once saying which field the server disliked, while the body was
    carrying the `{error: ...}` that names it the entire time. A 401 did the
    same later, until the server started naming what refused the client.
    """
    try:
        text = body if isinstance(body, str) else str(body)
    except Exception:
        return 'no body'
    text = ' '.join(text.split())
    if not text:
        return 'empty body'
    return text[:300] + ('...' if len(text) > 300 else '')

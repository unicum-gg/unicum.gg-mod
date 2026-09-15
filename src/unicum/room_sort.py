"""Sorting the skirmish room's members: the special battles' orders, plus two ratings.

The dropdown and the sorting itself are AS3 (as3/src/unicum/MembersSection.as):
rows are only moved on screen, because the client updates and acts on the
members list by slot number. What stays here is what AS3 cannot do:

  - remember the chosen order: AS3 holds it in `sortMode` for the session,
    and a freshly loaded view starts empty, so the saved one is written back;
  - label the orders the client also has with its own translations, and
    ours with the room's rating from the settings ("By 30d WNX"), or no
    such order when the room shows no rating.

Orders: the client's four, "score" for the rating chosen in the settings,
and "rating" for the client's personal rating. The ratings "score" sorts by
come from lobby.py, with the members.
"""
import json
import logging
import os

from gui.impl import backport
from gui.impl.gen import R

from unicum import views

_logger = logging.getLogger('unicum.room_sort')

MODES = ('default', 'vehicle', 'status', 'name', 'score', 'rating')

# Saved by earlier versions, under what the order is called now.
_RENAMED = {'wnx': 'score'}
_POLL_SECONDS = 0.5
_STORE = os.path.join('mods', 'configs', 'unicum', 'room_sort.json')


def labels(rating_label):
    """The dropdown's entries, in MODES order, newline separated.

    An empty entry is an order the dropdown leaves out: "score" without a
    rating to sort by.
    """
    sort = R.strings.prebattle.labels.sort
    game = [backport.text(resource()) for resource in (sort.byOrder, sort.byVehicles, sort.byStatus, sort.byName)]
    score = u'By %s' % rating_label if rating_label else u''
    return u'\n'.join(game + [score, u'By rating'])


class RoomSort(object):

    def __init__(self, session, settings, store=_STORE):
        self._session = session
        self._settings = settings
        self._store = store
        self._mode = self._load()
        self._labels = None

    def install(self):
        self._session.repeat(_POLL_SECONDS, self._poll)
        self._settings.on_change(self._on_settings)
        _logger.info('installed, members sorted by %s', self._mode)

    def _on_settings(self):
        self._labels = None

    def _poll(self):
        view = views.lobby_view()
        if view is None:
            return
        if self._labels is None:
            try:
                self._labels = labels(self._settings.label('skirmishRoom'))
            except Exception:
                _logger.exception('could not read the sort labels, AS3 keeps its English ones')
                self._labels = u''
        if self._labels and getattr(view, 'sortLabels', None) != self._labels:
            view.sortLabels = self._labels
        chosen = getattr(view, 'sortMode', None)
        if not chosen:
            view.sortMode = self._mode
        elif chosen != self._mode and chosen in MODES:
            self._mode = chosen
            self._save()

    def _load(self):
        try:
            with open(self._store, 'rb') as handle:
                mode = json.load(handle).get('mode')
        except (IOError, ValueError, AttributeError):
            return 'default'
        mode = _RENAMED.get(mode, mode)
        return mode if mode in MODES else 'default'

    def _save(self):
        try:
            directory = os.path.dirname(self._store)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            with open(self._store, 'wb') as handle:
                json.dump({'mode': self._mode}, handle)
        except (IOError, OSError):
            _logger.exception('could not write %s', self._store)


def install(session, settings):
    RoomSort(session, settings).install()

"""What was sent last time, and what has moved since.

The fingerprints of every vehicle already accepted, the hash of the marks, the
vehicles the player asked to withdraw, and the pure functions that say which
of them the server has not been told about yet. Values in, values out, so the
checks drive the reconciliation with no client in sight.
"""
from __future__ import absolute_import

import hashlib
import json
import logging
import os

from unicum.loadouts.reading import crewed, entry_of, fingerprint, mounted

_logger = logging.getLogger('unicum.loadouts.store')

# Which fingerprints were last accepted, so a second sweep sends nothing.
STORE = os.path.join('mods', 'configs', 'unicum', 'loadouts.json')

def _read_store():
    """The whole file, or an empty document.

    Read whole and written whole because it now carries two things that must
    not overwrite one another: the fingerprints, and the withdrawal a player
    has asked for and the server has not yet confirmed.
    """
    if not os.path.isfile(STORE):
        return {}
    try:
        with open(STORE, 'rb') as handle:
            stored = json.load(handle)
    except (IOError, ValueError):
        _logger.warning('could not read %s, sending everything', STORE)
        return {}
    return stored if isinstance(stored, dict) else {}

def _write_store(document):
    try:
        directory = os.path.dirname(STORE)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(STORE, 'wb') as handle:
            json.dump(document, handle)
        return True
    except (IOError, OSError):
        _logger.warning('could not write %s; the next sweep sends again', STORE, exc_info=True)
        return False

def load_sent():
    """{tank id: {'f': fingerprint, 'd': set(devices), 'c': crew size}} the server took.

    The devices and the crew size ride along with the fingerprint because a
    fingerprint only says THAT a vehicle changed, and the two rules below have
    to know HOW.
    """
    sent = _read_store().get('sent')
    if not isinstance(sent, dict):
        return {}
    out = {}
    for key, value in sent.items():
        entry = entry_of(value)
        # An entry with no devices recorded is unprotected against a demount
        # until its next real change, which is the right price for reading an
        # older file rather than discarding the whole carousel. Same for a
        # crew size the file does not carry.
        out[int(key)] = {'f': entry['f'],
                         'd': set(entry['d']) if entry['d'] is not None else None,
                         'c': entry['c']}
    return out

def save_sent(sent):
    on_disk = {}
    for key, value in sent.items():
        entry = entry_of(value)
        on_disk[key] = {'f': entry['f'], 'd': sorted(entry['d'] or ()), 'c': entry['c']}
    document = _read_store()
    document['sent'] = on_disk
    _write_store(document)

def load_marks_hash():
    """The fleet's marks as they were when the server last accepted them."""
    return _read_store().get('marksHash')

def save_marks_hash(value):
    document = _read_store()
    document['marksHash'] = value
    _write_store(document)

def marks_hash(marks):
    """One value for the whole fleet's marks, so an unchanged fleet is free.

    Without this the marks would ride only on sweeps that had a loadout to
    send, which is the rare case: a player who changes nothing in the garage
    changes nothing to send, and their marks would then never leave -- yet the
    marks move with every battle, which is precisely when the garage is
    untouched.
    """
    return hashlib.md5(json.dumps(sorted(marks.items()), sort_keys=True)).hexdigest()

def load_garage_hash():
    """The garage as it was when the server last accepted it."""
    return _read_store().get('garageHash')

def save_garage_hash(value):
    document = _read_store()
    document['garageHash'] = value
    _write_store(document)

def garage_hash(garage):
    """One value for the whole garage, so an unchanged one is free.

    The same reasoning as `marks_hash`, with the opposite rhythm: marks move
    with every battle, while a garage changes only when the player buys or
    sells. Without this the list would ride on sweeps that had a loadout to
    send and nothing else, and a player who has not touched their garage in a
    month has nothing to send -- which is exactly when the list is worth
    having, because it is then the only statement that their collection is
    still what it was.
    """
    return hashlib.md5(json.dumps(sorted(garage))).hexdigest()

def load_withdraw():
    """Whether the player asked us to be forgotten and the server has not said it did."""
    return bool(_read_store().get('withdraw'))

def save_withdraw(pending):
    """Remember, across restarts, that a withdrawal is still owed.

    A player unticks the box and closes the game, or the request fails
    because the network is down. Either way the rows are still published and
    the player believes they are not, so the ask has to outlive the session
    that made it and be repeated until the server confirms.
    """
    document = _read_store()
    if pending:
        document['withdraw'] = True
    else:
        document.pop('withdraw', None)
    _write_store(document)

def _keep_rejected(code, batch):
    """Leave a refused batch on disk, beside the fingerprints.

    Kept rather than removed once it had done its job. The shape of a loadout
    is a contract between this mod, a game client nobody here controls and a
    server in another repository, and the two bugs it has already found were
    both a vehicle the schema had not imagined: one with nothing to say about
    its post progression, and one whose main armament is a machine gun
    carrying 2700 rounds. Neither was visible from the log, and neither could
    be reproduced without the batch that carried it.

    Only what the server refused outright, never a network failure, and always
    the same file: this is a diagnosis, not a history.
    """
    if not (400 <= (code or 0) < 500):
        return
    try:
        with open(os.path.join('mods', 'configs', 'unicum', 'loadouts-rejected.json'), 'wb') as handle:
            json.dump(batch, handle)
    except (IOError, OSError):
        _logger.debug('could not write the refused batch down', exc_info=True)

def demounted(record, previous):
    """Whether this is a vehicle being stripped rather than rebuilt.

    A player moves equipment between vehicles constantly: the stabiliser comes
    off the IS-7 to go on the Leopard, and for a while the IS-7 sits there with
    an empty slot. That empty slot is not how the IS-7 is played, and recording
    it puts a build on the player's page that they have never used. Worse, the
    vehicle most worth reading about is often the one just stripped to equip
    the next.

    So a strict SUBSET is the signature: every device still mounted was already
    mounted before, and there are fewer of them. Swapping a rammer for vents is
    not a subset and is recorded, because that is a real decision. Only the
    taking away is refused, and a battle undoes the refusal (see `_on_battle`),
    since a vehicle that goes to war is equipped the way its owner means to
    play it.
    """
    before = previous.get('d') if previous else None
    if not before:
        # Nothing known about what was mounted (a store written before this
        # rule existed), so there is nothing to protect.
        return False
    now = mounted(record)
    return now < before

def uncrewed(record, previous):
    """Whether this is a vehicle whose crew is away rather than disbanded.

    The crew half of `demounted`, and the residue of it: `_crew` already
    fills the empty seats of a vehicle that has fought from its last crew, so
    what still reaches here is a vehicle the client keeps no last crew for,
    one that has never been to battle since it was built.

    A count is the whole signature. A vehicle never loses a seat, so fewer
    members than we recorded can only mean the crew went to drive something
    else. Retraining or resetting a perk keeps the members, so it is recorded
    rather than refused, which is right: that one is a decision.
    """
    before = previous.get('c') if previous else None
    if not before:
        # Nothing known about the crew (a store written before this rule
        # existed), so there is nothing to protect.
        return False
    return crewed(record) < before

def changed(records, sent, held):
    """The records worth sending: new, altered, or absent from the server.

    `held` is what the server says it already has. A fingerprint alone is not
    enough to decide: this file survives a reinstall of the site's database,
    and a vehicle we believe we sent but that the server does not hold would
    otherwise never be sent again.
    """
    out = []
    for record in records:
        tank = record['tankId']
        previous = sent.get(tank)
        known = previous.get('f') if previous else None
        if known == fingerprint(record) and (held is None or tank in held):
            continue
        if demounted(record, previous) or uncrewed(record, previous):
            continue
        out.append(record)
    return out

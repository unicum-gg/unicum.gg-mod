"""Shared by every check: the assertion, sample ids, the bootstrap stub."""

import os


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STUB_TEMPLATE = os.path.join(REPO, 'dev', 'mod_unicum_dev.py.in')


def render_stub(workdir, src_root):
    with open(STUB_TEMPLATE) as handle:
        text = handle.read().replace('__SRC_ROOT__', src_root.replace('\\', '/'))
    path = os.path.join(workdir, 'mod_unicum_dev.py')
    with open(path, 'w') as handle:
        handle.write(text)
    return path


def check(label, condition):
    print('%-4s %s' % ('ok' if condition else 'FAIL', label))
    if not condition:
        raise SystemExit(1)


# Accounts and a clan from a real EU skirmish roster, used so the lookup is
# exercised against answers the server actually holds.
SAMPLE_PLAYERS = [518080300, 538132472]
# A third real account, never looked up before the profile check.
SAMPLE_UNCACHED_PLAYER = 554095149
SAMPLE_CLAN = 500198413
SAMPLE_CLAN_TAG = 'RASZ'


# Enough to cover what those samples resolve to, without depending on it.
FLAG_CODES = ('CZ', 'GB-UKM', 'PL', 'DE', 'FR', 'RU', 'UA', 'SK')

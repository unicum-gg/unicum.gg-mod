"""The convention in AGENTS.md, enforced rather than hoped for.

A file past the limit is not a style problem. It is where two small, unrelated
additions start colliding, where a reader has to hold too much at once, and
where the import that should have been obvious goes wrong quietly: see the
`battle_results` collision in `battles.py`, which shipped a dead feature.

`ALLOWED` is a ratchet, not a list of exemptions. Each entry is a file that
was already over the line when this check was written, with the size it had;
the check fails if one of them grows. Entries come off as files are split,
and nothing is ever added: a new file over the limit fails outright.
"""

import os

from checks.common import check, REPO

#: What AGENTS.md asks for.
LIMIT = 400

#: Files already over the limit, with the size to hold them to.
#:
#: Written down on 2026-10-28, when 11 of 49 modules were over. The number
#: beside each is a ceiling: it may go down and never up.
ALLOWED = {
    # battles.py came off this list on 2026-10-28: 1498 lines became the
    # seven modules of battles/, the largest 333.
    # loadouts.py came off on 2026-10-28: 972 lines became the five
    # modules of loadouts/, the largest 318.
    # replays.py came off on 2026-10-28: 950 lines became the six
    # modules of replays/, the largest 261.
    # settings_window.py came off on 2026-10-28 (issue #3): 770 lines
    # became the five modules of settings_window/, the largest 263.
    # twitch_window.py came off on 2026-10-28: 670 lines became the
    # five modules of twitch_window/, the largest 216.
    # twitch.py came off on 2026-10-28: 595 lines became the four
    # modules of twitch/, the largest 305.
    'battle.py': 551,
    'settings.py': 526,
    'lobby.py': 492,
    'game_link.py': 469,
    'tank_button.py': 458,
}


def _modules():
    """(path relative to src/unicum, line count) for every module in the mod."""
    root = os.path.join(REPO, 'src', 'unicum')
    for folder, _, names in os.walk(root):
        for name in names:
            if not name.endswith('.py'):
                continue
            full = os.path.join(folder, name)
            with open(full) as handle:
                lines = sum(1 for _ in handle)
            yield os.path.relpath(full, root).replace(os.sep, '/'), lines


def check_file_sizes():
    """No module over the limit that was not already, and none of those growing."""
    sizes = dict(_modules())

    over = sorted(name for name, lines in sizes.items()
                  if lines > LIMIT and name not in ALLOWED)
    check('no new module is over %d lines%s'
          % (LIMIT, '' if not over else ': ' + ', '.join(over)), not over)

    grown = sorted('%s %d > %d' % (name, sizes[name], ceiling)
                   for name, ceiling in ALLOWED.items()
                   if name in sizes and sizes[name] > ceiling)
    check('no module over the limit has grown%s'
          % ('' if not grown else ': ' + ', '.join(grown)), not grown)

    # The ratchet only works if it tightens. A file split below the limit has
    # to leave the list, or it buys back room it no longer needs.
    slack = sorted('%s is %d, allowed %d' % (name, sizes[name], ceiling)
                   for name, ceiling in ALLOWED.items()
                   if name in sizes and sizes[name] <= LIMIT)
    check('nothing stays on the list once it is under the limit%s'
          % ('' if not slack else ': ' + ', '.join(slack)), not slack)

    gone = sorted(name for name in ALLOWED if name not in sizes)
    check('the list names no module that no longer exists%s'
          % ('' if not gone else ': ' + ', '.join(gone)), not gone)

    remaining = sum(1 for name, lines in sizes.items() if lines > LIMIT)
    print('       %d of %d modules over %d lines' % (remaining, len(sizes), LIMIT))

"""The convention in AGENTS.md, enforced rather than hoped for.

A file past the limit is not a style problem. It is where two small, unrelated
additions start colliding, which is what Rayman223 measured in #3; where a
reader has to hold too much at once; and where the import that should have
been obvious goes wrong quietly, as the `battle_results` collision in
battles.py did, shipping a feature that did nothing at all.

`ALLOWED` is a ratchet. It held eleven entries on 2026-10-28, one per module
that was already over the line, with the size it had, and the check failed if
one grew. It is empty now, each of the eleven having become a package, so the
first check is what the convention asks for and the other three are what keep
the ratchet honest should an entry ever be needed again.
"""

import os

from checks.common import check, REPO

#: What AGENTS.md asks for.
LIMIT = 400

#: Modules allowed past the limit, with a ceiling each.
#:
#: Empty, and meant to stay that way. An entry may only be added for a module
#: that is genuinely over the limit and cannot be split today, with the size it
#: has; it may then go down and never up, and comes off once the module is
#: under the limit.
ALLOWED = {}


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
    """No module over the limit, and no exception growing or outstaying itself."""
    sizes = dict(_modules())

    over = sorted('%s (%d)' % (name, lines) for name, lines in sizes.items()
                  if lines > LIMIT and name not in ALLOWED)
    check('no module is over %d lines%s'
          % (LIMIT, '' if not over else ': ' + ', '.join(over)), not over)

    grown = sorted('%s %d > %d' % (name, sizes[name], ceiling)
                   for name, ceiling in ALLOWED.items()
                   if name in sizes and sizes[name] > ceiling)
    check('no module with an exception has grown%s'
          % ('' if not grown else ': ' + ', '.join(grown)), not grown)

    # The ratchet only works if it tightens. A file split below the limit has
    # to leave the list, or it buys back room it no longer needs.
    slack = sorted('%s is %d, allowed %d' % (name, sizes[name], ceiling)
                   for name, ceiling in ALLOWED.items()
                   if name in sizes and sizes[name] <= LIMIT)
    check('nothing keeps an exception it no longer needs%s'
          % ('' if not slack else ': ' + ', '.join(slack)), not slack)

    gone = sorted(name for name in ALLOWED if name not in sizes)
    check('no exception names a module that no longer exists%s'
          % ('' if not gone else ': ' + ', '.join(gone)), not gone)

    largest = max(sizes.values()) if sizes else 0
    print('       %d modules, largest %d lines, limit %d'
          % (len(sizes), largest, LIMIT))

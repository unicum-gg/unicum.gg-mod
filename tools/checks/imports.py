"""Every name the mod takes from itself, checked against what defines it.

A name used in a module header is already checked by the suite: the module
loads, or the run stops on the spot. A name used *inside a function* is not.
It is read the first time that function runs, which in the client can be
minutes in, or on a screen nobody opened during a test.

That is how the package split shipped ten broken references. Six were
deferred imports of names that had moved into a submodule (`ICON_RES_PATH`
into `twitch.protocol`, `linked_notice` into `settings_window.labels`); four
were `tank_button.<name>` reads of names the new package never re-exported.
The battle Twitch panel failed every half second for two hours of play, the
garage window lost its icon, two menu entries would have failed on click, and
the suite said nothing. From the outside the mod looked fine: each error was
caught, logged, and retried forever.

So this reads the whole tree rather than the module header, and checks both
ways a module reaches into another:

  import      `from unicum.x import name`, at any depth
  attribute   `x.name`, where `x` was bound to one of our modules

Static, so it costs nothing and covers the branches no test reaches. It
cannot judge a module that populates itself, and says so by skipping it.
"""

import ast
import os

from checks.common import check, REPO

#: Python 2.7 names the two halves of a try separately; 3.x merged them.
_TRY = tuple(getattr(ast, name) for name in ('Try', 'TryExcept', 'TryFinally')
             if hasattr(ast, name))

_SRC = os.path.join(REPO, 'src')


def _module_file(dotted):
    """The file a dotted mod module resolves to, or None if there is none."""
    path = os.path.join(_SRC, *dotted.split('.'))
    if os.path.isdir(path):
        init = os.path.join(path, '__init__.py')
        return init if os.path.isfile(init) else None
    return path + '.py' if os.path.isfile(path + '.py') else None


def _bound(node, names):
    """Add whatever `node` binds at the level it sits on."""
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        names.add(node.name)
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    elif isinstance(node, (ast.Import, ast.ImportFrom)):
        for alias in node.names:
            names.add(alias.asname or alias.name.split('.')[0])


def _defines(path):
    """(names bound at the top level, whether the module binds any itself)."""
    with open(path) as handle:
        tree = ast.parse(handle.read(), path)
    names = set()
    for node in tree.body:
        _bound(node, names)
        # A constant behind a version check, or a name from a try/except
        # ImportError, is bound just as much as one at the top level.
        if isinstance(node, (ast.If,) + _TRY):
            for inner in ast.walk(node):
                _bound(inner, names)

    dynamic = any(isinstance(node, ast.Name) and node.id in ('setattr', 'globals')
                  for node in ast.walk(tree))
    return names, dynamic


def _reassigned(tree):
    """Every name the module assigns or takes as an argument anywhere.

    A name in here cannot be trusted to still mean the module it was bound to
    at the top, so its attribute reads are left alone rather than guessed at.
    """
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arguments):
            for arg in node.args:
                if isinstance(arg, ast.Name):
                    names.add(arg.id)            # 2.7
                elif hasattr(arg, 'arg'):
                    names.add(arg.arg)           # 3.x, for running the file
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _ours(node):
    """Whether an ImportFrom names one of our modules absolutely."""
    return (not node.level and node.module
            and node.module.split('.')[0] == 'unicum')


def _modules():
    """(path relative to src, parsed tree) for every module in the mod."""
    for folder, _, files in os.walk(_SRC):
        for name in sorted(files):
            if not name.endswith('.py'):
                continue
            path = os.path.join(folder, name)
            with open(path) as handle:
                yield (os.path.relpath(path, _SRC).replace(os.sep, '/'),
                       ast.parse(handle.read(), path))


def _bindings(tree):
    """local name -> the dotted mod module it was bound to."""
    modules = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _ours(node):
            for alias in node.names:
                dotted = node.module + '.' + alias.name
                if _module_file(dotted):
                    modules[alias.asname or alias.name] = dotted
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (alias.asname and alias.name.split('.')[0] == 'unicum'
                        and _module_file(alias.name)):
                    modules[alias.asname] = alias.name

    for local in _reassigned(tree):
        modules.pop(local, None)
    return modules


def check_imports():
    """No module takes from another a name it does not have."""
    broken, counts = [], {'import': 0, 'deferred': 0, 'attribute': 0}
    defines = {}

    def known(dotted):
        target = _module_file(dotted)
        if target not in defines:
            defines[target] = _defines(target)
        return defines[target]

    for rel, tree in _modules():
        # What the module header imports, so the rest are the deferred ones.
        header = set(id(node) for node in tree.body)
        modules = _bindings(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if not _ours(node):
                    continue
                if _module_file(node.module) is None:
                    broken.append('%s:%d imports from %s, which does not exist'
                                  % (rel, node.lineno, node.module))
                    continue
                names, _ = known(node.module)
                for alias in node.names:
                    if alias.name == '*':
                        continue
                    counts['import'] += 1
                    if id(node) not in header:
                        counts['deferred'] += 1
                    # A submodule imports without the package binding it.
                    if _module_file(node.module + '.' + alias.name):
                        continue
                    if alias.name not in names:
                        broken.append('%s:%d asks %s for %s'
                                      % (rel, node.lineno, node.module, alias.name))

            elif isinstance(node, ast.Attribute):
                if not isinstance(node.value, ast.Name):
                    continue
                dotted = modules.get(node.value.id)
                if dotted is None or node.attr.startswith('__'):
                    continue
                names, dynamic = known(dotted)
                if dynamic:
                    continue
                counts['attribute'] += 1
                if _module_file(dotted + '.' + node.attr):
                    continue
                if node.attr not in names:
                    broken.append('%s:%d reads %s.%s, which is not there'
                                  % (rel, node.lineno, dotted, node.attr))

    check('every name the mod takes from itself exists%s'
          % ('' if not broken else ': ' + '; '.join(sorted(broken))), not broken)
    print('       %d imported names (%d inside a function), %d attribute reads'
          % (counts['import'], counts['deferred'], counts['attribute']))

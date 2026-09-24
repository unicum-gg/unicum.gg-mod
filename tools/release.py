"""Cut a release: one command from the last tag to a package ready to publish.

    python tools/release.py                 read the commits, show what it would
                                            do, then do it once confirmed
    python tools/release.py --dry-run       show and stop, writing nothing
    python tools/release.py --minor         force the level the commits did not ask for

The version and the changelog both come from the commits since the last tag,
which is the whole point: the subjects are already typed (`<gitmoji> <type>
<description>`), so a release needs no second place to write down what changed
and no file to remember to add. What the commits cannot decide is left to a
person: the level can be forced, and the changelog is opened in an editor
before anything is built.

Runs on Python 3. The checks it calls run on the client's Python 2.7, which it
finds the way `build_release.py` does.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import webbrowser

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(REPO, 'dist')
CHANGELOG = os.path.join(REPO, 'CHANGELOG.md')

# The mod's page, and the section a new build is uploaded from. Neither can be
# automated: wgmods publishes no API for it (`robots.txt` disallows `/api/` and
# `/modder-section/`), so the last step is a person dropping a file in a form.
WGMODS_MOD = 'https://wgmods.net/7928'
WGMODS_UPLOAD = 'https://wgmods.net/modder-section/'

# `<gitmoji> <type> <description>`: the type is what decides both halves of a
# release, so it is read rather than guessed from the emoji, which repeats
# across types (💄 is worn by `fix` and by `improve` alike).
SUBJECT = re.compile(r'^\S+\s+(add|fix|improve|update|remove|refactor|rename|move|upgrade|downgrade|release)\s+(.+)$')

# A new capability is a minor; everything else is a patch. A major is never
# inferred: it says the mod stopped doing something it did, which is a decision
# rather than a count, so it takes `--major`.
MINOR = {'add'}

# What a player is told about, and under which heading. A type absent here
# still counts towards the version -- it was work, and the build changed -- but
# says nothing to somebody reading the changelog: `refactor`, `move` and
# `rename` move code around without moving anything they can see.
SECTIONS = (
    ('Added', ('add',)),
    ('Improved', ('improve', 'update', 'upgrade')),
    ('Fixed', ('fix',)),
    ('Removed', ('remove', 'downgrade')),
)
TOLD = {kind for _, kinds in SECTIONS for kind in kinds}


def run(command, capture=False, cwd=REPO):
    """A command, failing loudly: a release that half happened is worse than none."""
    if capture:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding='utf-8')
        if done.returncode:
            raise SystemExit('failed: %s\n%s' % (' '.join(command), done.stderr or done.stdout))
        return done.stdout
    if subprocess.run(command, cwd=cwd).returncode:
        raise SystemExit('failed: %s' % ' '.join(command))
    return None


def last_tag():
    """The newest `vX.Y.Z`, or None on a repository that has never released."""
    tags = run(['git', 'tag', '-l', 'v*', '--sort=-v:refname'], capture=True).split()
    return tags[0] if tags else None


def commits_since(tag):
    """(type, description) for each commit since `tag`, newest last.

    A subject that does not parse is kept as an unknown type rather than
    dropped: it still counts as work done, and a release that silently ignores
    a commit is a release nobody can check.
    """
    span = '%s..HEAD' % tag if tag else 'HEAD'
    subjects = run(['git', 'log', '--reverse', '--pretty=%s', span], capture=True).splitlines()
    read = []
    for subject in subjects:
        found = SUBJECT.match(subject.strip())
        read.append(found.groups() if found else (None, subject.strip()))
    return read


def next_version(tag, commits, forced):
    """The version these commits earn, or the one that was asked for."""
    major, minor, patch = (int(part) for part in (tag or 'v0.0.0')[1:].split('.'))
    level = forced or ('minor' if any(kind in MINOR for kind, _ in commits) else 'patch')
    if level == 'major':
        return '%d.0.0' % (major + 1), level
    if level == 'minor':
        return '%d.%d.0' % (major, minor + 1), level
    return '%d.%d.%d' % (major, minor, patch + 1), level


def changelog(version, commits):
    """The release notes, grouped, in the mod's own language.

    English, like every string the mod shows and like the wgmods page this is
    pasted into: the audience is whoever plays the game, not whoever wrote it.
    """
    lines = ['## %s' % version, '']
    for heading, kinds in SECTIONS:
        said = [text for kind, text in commits if kind in kinds]
        if not said:
            continue
        lines.append('### %s' % heading)
        lines.append('')
        lines.extend('- %s%s' % (text[0].upper(), text[1:]) for text in said)
        lines.append('')
    quiet = [text for kind, text in commits if kind not in TOLD]
    if quiet:
        lines.append('<!-- %d commit(s) not shown, being invisible to a player:' % len(quiet))
        lines.extend('     %s' % text for text in quiet)
        lines.append('-->')
        lines.append('')
    return '\n'.join(lines)


def edited(text):
    """The notes after a read-through, or None if they were emptied to cancel.

    Opened rather than written straight out, because the subjects were written
    for whoever reads the log and the changelog is read by whoever plays: the
    two are close enough to start from and never the same words.
    """
    handle, path = tempfile.mkstemp(suffix='.md', text=True)
    os.close(handle)
    with open(path, 'w', encoding='utf-8') as out:
        out.write(text)
        out.write('\n\n<!-- Read it over, then save and close. Empty the file to cancel. -->\n')
    editor = os.environ.get('EDITOR') or ('notepad' if os.name == 'nt' else 'nano')
    subprocess.run([editor, path])
    with open(path, encoding='utf-8') as back:
        kept = re.sub(r'<!--.*?-->', '', back.read(), flags=re.S).strip()
    os.unlink(path)
    return kept or None


def prepend(notes):
    """The new notes on top of the file, which reads newest first."""
    whole = ''
    if os.path.exists(CHANGELOG):
        with open(CHANGELOG, encoding='utf-8') as current:
            whole = current.read()
    # Drop the title so it is written once, and keep what released before it.
    body = (whole.split('\n', 1)[1] if whole.startswith('# ') else whole).strip()
    with open(CHANGELOG, 'w', encoding='utf-8') as out:
        out.write('# Changelog\n\n%s\n' % notes.strip())
        if body:
            out.write('\n%s\n' % body)


def to_clipboard(text):
    """The notes in the clipboard, for the form that cannot be posted to."""
    try:
        if os.name == 'nt':
            subprocess.run(['clip'], input=text, text=True, encoding='utf-8', check=True)
            return True
    except Exception:
        pass
    return False


def build(version, py27, game):
    """The package, then the two checks that read it the way the client does."""
    run([sys.executable, os.path.join('tools', 'build_as3.py'), '--game', game])
    release = [sys.executable, os.path.join('tools', 'build_release.py'), '--version', version]
    if py27:
        release += ['--python27', py27]
    run(release)
    run([py27 or 'python2.7', os.path.join('tools', 'selftest.py')])
    run([py27 or 'python2.7', os.path.join('tools', 'release_check.py'),
         os.path.join('dist', 'gg.unicum_%s.wotmod' % version)])


def publish(version, notes):
    """The tag, and the GitHub release carrying what a player downloads."""
    run(['git', 'add', '--', 'CHANGELOG.md'])
    run(['git', 'commit', '-m', '🔖 release %s' % version])
    run(['git', 'tag', '-a', 'v%s' % version, '-m', version])
    run(['git', 'push', 'origin', 'HEAD', '--follow-tags'])
    handle, path = tempfile.mkstemp(suffix='.md', text=True)
    os.close(handle)
    with open(path, 'w', encoding='utf-8') as out:
        out.write(notes)
    run(['gh', 'release', 'create', 'v%s' % version,
         os.path.join('dist', 'gg.unicum_%s.wotmod' % version),
         os.path.join('dist', 'unicum.gg_%s.zip' % version),
         '--title', version, '--notes-file', path])
    os.unlink(path)


def hand_over(version, notes):
    """Everything the upload form needs, put in front of whoever fills it in."""
    copied = to_clipboard(notes)
    if os.name == 'nt':
        subprocess.run(['explorer', DIST])
    webbrowser.open(WGMODS_UPLOAD)
    print('\n  wgmods is the one step that stays manual: it publishes no upload API.')
    print('  dist/gg.unicum_%s.wotmod and dist/unicum.gg_%s.zip are built.' % (version, version))
    print('  The notes are %s.' % ('in your clipboard' if copied else 'in CHANGELOG.md'))
    print('  The GitHub release is live now; wgmods follows once it has reviewed it')
    print('  (0.1.1 took six days), which is why nothing announces a version on its own.\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dry-run', action='store_true', help='show what would happen, write nothing')
    parser.add_argument('--major', dest='level', action='store_const', const='major')
    parser.add_argument('--minor', dest='level', action='store_const', const='minor')
    parser.add_argument('--patch', dest='level', action='store_const', const='patch')
    parser.add_argument('--python27', help="path to the client's Python 2.7")
    parser.add_argument('--game', default=r'C:/Games/World_of_Tanks_EU',
                        help='the client the AS3 build compiles against')
    args = parser.parse_args()

    tag = last_tag()
    commits = commits_since(tag)
    if not commits:
        raise SystemExit('nothing since %s' % (tag or 'the first commit'))
    version, level = next_version(tag, commits, args.level)
    counted = {}
    for kind, _ in commits:
        counted[kind or 'unreadable'] = counted.get(kind or 'unreadable', 0) + 1

    print('\n  since %s: %d commits' % (tag or 'the beginning', len(commits)))
    print('  %s' % ', '.join('%d %s' % (n, k) for k, n in sorted(counted.items(), key=lambda p: -p[1])))
    print('  -> %s (%s)%s\n' % (version, level, ', forced' if args.level else ''))
    notes = changelog(version, commits)
    print('\n'.join('  ' + line for line in notes.splitlines()))

    if args.dry_run:
        print('\n  --dry-run: nothing written.\n')
        return

    notes = edited(notes)
    if not notes:
        raise SystemExit('cancelled')
    prepend(notes)
    build(version, args.python27, args.game)
    publish(version, notes)
    hand_over(version, notes)


if __name__ == '__main__':
    main()

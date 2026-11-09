"""Decide whether a release is due, and write it into the working tree if so.

    python tools/release_pr.py --client DIR [--published FILE]

Run by .github/workflows/release-pr.yml, which turns what this writes into the
release pull request; merging that pull request is what releases. Two things
make a release due, and either is enough:

  * commits on main since the last tag that a player would be told about, read
    exactly as tools/release.py reads them (the version and the notes come from
    their typed subjects). The others wait for one that is: alone, they would
    send the hub's moderators a version with empty notes;
  * the live client moving away from the files the last release was built
    against, which a release records as its `client.json` asset. Not only the
    mods folder: Wargaming republished battleVehicleMarkersApp.swf around
    2026-10-29 under the same mods/2.4.1.1, and the package ships that file in
    place of the client's own, so a release built on the 26 October copy was
    out of date with nothing in the folder name to say so.

DIR is what wot.build's `npm run client-files` wrote: the client's files at the
live build and a manifest.json hashing each of them. FILE is the last release's
client.json; a release published before those existed has none, which reads as
"built against something else", since there is no way to say it was not.

It writes CHANGELOG.md, replacing an unreleased section at the top rather than
stacking a second one (a regenerated pull request, or a merge whose release
failed), and appends `version=` and `due=` to $GITHUB_OUTPUT when it is set.
Python 3, never shipped inside the mod.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from release import CHANGELOG, TOLD, changelog, commits_since, last_tag, next_version  # noqa: E402

SECTION = re.compile(r'^## (\d+\.\d+\.\d+)\s*$', re.M)


def read_json(path):
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as source:
        return json.load(source)


def client_moved(live, published):
    """True when the live client's files are not the ones the last release used."""
    if published is None:
        return True
    return live['mods'] != published.get('mods') or live['files'] != published.get('files')


def tagged(version):
    found = subprocess.run(['git', 'tag', '-l', 'v%s' % version], capture_output=True, text=True)
    return bool(found.stdout.strip())


def write_changelog(notes):
    """The new section on top, in place of a section no tag has released yet."""
    whole = ''
    if os.path.exists(CHANGELOG):
        with open(CHANGELOG, encoding='utf-8') as current:
            whole = current.read()
    body = (whole.split('\n', 1)[1] if whole.startswith('# ') else whole).strip()
    top = SECTION.search(body)
    if top and top.start() == 0 and not tagged(top.group(1)):
        following = SECTION.search(body, top.end())
        body = body[following.start():] if following else ''
    with open(CHANGELOG, 'w', encoding='utf-8') as out:
        out.write('# Changelog\n\n%s\n' % notes.strip())
        if body:
            out.write('\n%s\n' % body)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--client', required=True, help="wot.build's client-files output")
    parser.add_argument('--published', help="the last release's client.json, if it has one")
    args = parser.parse_args()

    live = read_json(os.path.join(args.client, 'manifest.json'))
    if live is None:
        raise SystemExit('no manifest.json in %s' % args.client)
    tag = last_tag()
    commits = commits_since(tag)
    moved = client_moved(live, read_json(args.published))

    due = any(kind in TOLD for kind, _ in commits) or moved
    version = None
    if due:
        # A client that moved with nothing committed is still a release: the
        # package has to be rebuilt on the new files, which is a patch.
        version, level = next_version(tag, commits, None)
        if moved:
            commits = commits + [('improve', 'build for the game client %s' % live['mods'])]
        write_changelog(changelog(version, commits))
        print('release %s (%s): %d commits since %s%s' % (
            version, level, len(commits) - (1 if moved else 0), tag or 'the beginning',
            ', client moved to %s (%s)' % (live['mods'], live['versionName']) if moved else ''))
    else:
        print('nothing to release since %s' % tag)

    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a', encoding='utf-8') as out:
            out.write('due=%s\n' % ('yes' if due else 'no'))
            out.write('version=%s\n' % (version or ''))
            out.write('mods=%s\n' % live['mods'])
            out.write('build=%s\n' % live['versionName'])
            out.write('moved=%s\n' % ('yes' if moved else 'no'))


if __name__ == '__main__':
    main()

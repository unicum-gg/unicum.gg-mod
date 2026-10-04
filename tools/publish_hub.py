"""Add a built version to the mod hub, without filling its form by hand.

    python tools/publish_hub.py --version 0.4.1              what it would send
    python tools/publish_hub.py --version 0.4.1 --send       send it

The hub has no documented API, but its own pages drive two Django REST views,
and those are what this uses:

    POST /api/mods/mod_file_upload      the archive, multipart, field `source`
    PUT  /api/mods/7928/                the mod, with a version added

Both need `X-Requested-With: XMLHttpRequest` -- without it they answer 404,
which is how the API gets mistaken for absent -- a `sessionid` cookie, and a
`csrftoken` cookie echoed back in `X-CSRFToken`.

**It is not a robot that can run while you are away.** A wgmods session lasts
hours, so there is nothing durable to put in a CI secret; this is meant to be
run from a machine where you are logged in, which turns twenty minutes of form
filling into one command. Wargaming reviews every submission either way, so
nothing reaches players the moment this returns.

Credentials come from the environment and are never written anywhere:

    WGMODS_SESSIONID    the `sessionid` cookie
    WGMODS_CSRFTOKEN    the `csrftoken` cookie

In Chrome or Brave: devtools, Application, Cookies, https://wgmods.net.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / 'dist'

MOD_ID = 7928
BASE = 'https://wgmods.net'
# The owner's own view of the mod: the same fields the edit page draws from.
OWNER = f'{BASE}/api/mods/{MOD_ID}/owner/'
MOD = f'{BASE}/api/mods/{MOD_ID}/'
UPLOAD = f'{BASE}/api/mods/mod_file_upload'
# Where a version is created. Not a nested route under the mod and not a
# write on the mod itself: a PATCH carrying `versions` answers 200 and adds
# nothing, which is how this was got wrong the first time.
VERSIONS = f'{BASE}/api/mods/versions/'
# The edit page carries the game versions it offers, with the ids the API wants.
# They sit in a JS string literal, so every quote arrives as the six
# characters \u0022:
#
#     \u0022gameVersions\u0022: [{\u0022version\u0022: \u00222.4.0.2\u0022, ...
#
# Both spellings are accepted here, in case the page is ever served plainly.
EDIT = f'{BASE}/{MOD_ID}/edit/'
GAME_VERSIONS = re.compile(r'(?:\\u0022|")gameVersions(?:\\u0022|")\s*:\s*(\[.*?\])', re.S)

# How the edit page spells a quote inside its JS string literal. Built from
# its code point so no amount of escaping on the way in can resolve it.
ESCAPED_QUOTE = chr(92) + 'u0022'

VERSION = re.compile(r'^\d+\.\d+\.\d+$')


def credentials() -> tuple[str, str]:
    session = os.environ.get('WGMODS_SESSIONID', '').strip()
    csrf = os.environ.get('WGMODS_CSRFTOKEN', '').strip()
    if not session or not csrf:
        raise SystemExit(
            'set WGMODS_SESSIONID and WGMODS_CSRFTOKEN from the cookies of a '
            'logged-in wgmods.net (devtools, Application, Cookies)')
    return session, csrf


def call(url: str, session: str, csrf: str, method: str = 'GET',
         body: bytes | None = None, content_type: str | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header('Accept', 'application/json')
    # Without this the view answers 404 rather than saying what it wants.
    request.add_header('X-Requested-With', 'XMLHttpRequest')
    request.add_header('X-CSRFToken', csrf)
    request.add_header('Referer', EDIT)
    request.add_header('Cookie', f'sessionid={session}; csrftoken={csrf}')
    if content_type:
        request.add_header('Content-Type', content_type)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except urllib.error.URLError as error:
        raise SystemExit(f'{url}: {error.reason}')


def multipart(path: Path) -> tuple[bytes, str]:
    """The archive as one `source` field, the way the edit page sends it."""
    boundary = f'----unicum{uuid.uuid4().hex}'
    kind = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    head = (f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="source"; filename="{path.name}"\r\n'
            f'Content-Type: {kind}\r\n\r\n').encode('utf-8')
    tail = f'\r\n--{boundary}--\r\n'.encode('utf-8')
    return head + path.read_bytes() + tail, f'multipart/form-data; boundary={boundary}'


def game_version_id(session: str, csrf: str, wanted: str) -> int:
    """The hub's own id for a client version, read off the edit page."""
    status, body = call(EDIT, session, csrf)
    if status != 200:
        raise SystemExit(f'{EDIT}: HTTP {status}; is the session still good?')
    found = GAME_VERSIONS.search(body.decode('utf-8', 'replace'))
    if not found:
        raise SystemExit(f'no gameVersions on {EDIT}')
    versions = json.loads(found.group(1).replace(ESCAPED_QUOTE, '"'))
    for entry in versions:
        if entry.get('version') == wanted:
            return int(entry['id'])
    offered = ', '.join(str(entry.get('version')) for entry in versions[:6])
    raise SystemExit(f'the hub does not offer client {wanted}; it offers {offered}')


def client_of(zip_path: Path) -> str:
    """The client version the zip targets, from the folder it unpacks into."""
    import zipfile
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            found = re.match(r'^mods/([0-9][0-9.]*)/', name)
            if found:
                return found.group(1)
    raise SystemExit(f'no mods/<version>/ inside {zip_path}')


def changelog_of(version: str) -> str:
    """This version's section of CHANGELOG.md, as the release notes use it."""
    text = (REPO / 'CHANGELOG.md').read_text(encoding='utf-8')
    found = re.search(r'^##\s*\[?%s\]?\s*$(.*?)(?=^##\s|\Z)' % re.escape(version),
                      text, re.S | re.M)
    return found.group(1).strip() if found else ''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', required=True, help='the mod version, x.y.z')
    parser.add_argument('--zip', type=Path, help='the archive; dist/unicum.gg_<version>.zip by default')
    parser.add_argument('--send', action='store_true',
                        help='actually add the version; without it nothing is written')
    args = parser.parse_args()
    if not VERSION.match(args.version):
        raise SystemExit('--version must be x.y.z')

    archive = args.zip or DIST / f'unicum.gg_{args.version}.zip'
    if not archive.is_file():
        raise SystemExit(f'{archive} is not there; build it first')
    session, csrf = credentials()

    client = client_of(archive)
    print(f'archive  {archive.name} ({archive.stat().st_size / 1024:.0f} KB), for client {client}')

    status, body = call(OWNER, session, csrf)
    if status != 200:
        raise SystemExit(f'{OWNER}: HTTP {status}; is the session still good?')
    mod = json.loads(body)
    have = [str(v.get('version')) for v in mod.get('versions') or []]
    print(f'hub      status={mod.get("status")}, versions {", ".join(have) or "none"}')
    if args.version in have:
        raise SystemExit(f'{args.version} is already on the hub')

    client_id = game_version_id(session, csrf, client)
    notes = changelog_of(args.version)
    print(f'client   {client} is id {client_id} on the hub')
    print(f'notes    {len(notes)} characters from CHANGELOG.md'
          f'{"" if notes else " (none: the version has no section)"}')

    if not args.send:
        print('\nnothing sent. The version it would add:\n')
        print(json.dumps({'version': args.version,
                          'game_version': {'id': client_id, 'version': client},
                          'change_log': notes[:300] + ('...' if len(notes) > 300 else ''),
                          'is_visible': True}, indent=2, ensure_ascii=False))
        print('\nrun again with --send to add it.')
        return

    body, content_type = multipart(archive)
    status, raw = call(UPLOAD, session, csrf, 'POST', body, content_type)
    if status not in (200, 201):
        raise SystemExit(f'{UPLOAD}: HTTP {status}\n{raw[:400].decode("utf-8", "replace")}')
    uploaded = json.loads(raw)
    print(f'uploaded id={uploaded["id"]} as {uploaded.get("source_original_name")}')

    # One POST creates the version. The fields are the ones the edit page
    # sends, and `mod` is in the body rather than the path.
    created = {
        'mod': MOD_ID,
        'game_version': client_id,
        'version': args.version,
        'is_visible': True,
        'change_log': notes,
        'temporary_version_file': uploaded['id'],
        'temporary_version_file_access_token': uploaded['access_token'],
    }
    status, raw = call(VERSIONS, session, csrf, 'POST',
                       json.dumps(created).encode('utf-8'), 'application/json')
    if status not in (200, 201):
        raise SystemExit(f'{VERSIONS}: HTTP {status}' + chr(10) + raw[:600].decode("utf-8", "replace"))
    version = json.loads(raw)
    print(f'created  version id={version["id"]}, status={version.get("status")}')

    # The hub's own form posts the notes nowhere: it creates the version and
    # leaves `change_log` empty, so 0.4.1 went to review without any. The
    # create here does send them, and this checks rather than trusts: if they
    # did not stick, the instance takes them.
    if notes and not (version.get('change_log') or '').strip():
        instance = f'{VERSIONS}{version["id"]}/'
        status, raw = call(instance, session, csrf, 'PATCH',
                           json.dumps({'change_log': notes}).encode('utf-8'),
                           'application/json')
        if status not in (200, 202):
            raise SystemExit(f'{instance}: HTTP {status}' + chr(10) + raw[:400].decode("utf-8", "replace"))
        print('notes    attached separately')

    print(f'sent     {args.version} for client {client}; Wargaming reviews it before it appears')


if __name__ == '__main__':
    sys.exit(main())

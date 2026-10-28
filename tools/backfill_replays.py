"""Send the replays already on disk, the ones from before the mod included.

    python tools/backfill_replays.py                      what it would send
    python tools/backfill_replays.py --send               send it
    python tools/backfill_replays.py --send --limit 50    stop after 50 files
    python tools/backfill_replays.py --selfcheck          its own date cases

The mod only ever offers the replay of a battle it watched end: it looks at
the six newest files in the folder and asks for them by the battle id it read
out of the client. A folder holding a year of play is therefore invisible to
it, and this is what reaches that.

WHY A REPLAY IS ENOUGH ON ITS OWN

A finished `.wotreplay` carries two JSON blocks in the clear, ahead of the
encrypted stream:

    block 0   mapName, gameplayID, clientVersionFromXml, playerID
    block 1   [{personal, players, vehicles, common, arenaUniqueID, avatars}]

Block 1 is the shape `postResult` hands the mod at the end of a battle, and
block 0 holds the two things `payload` needs that are not in the
results. So a battle from months ago can be declared from its file alone, and
`battles.extract.payload` builds the body here rather than a copy of it living in
this file. About one replay in twenty carries no results at all, a battle
left before it ended, and there is nothing to be done with those.

WHY NOT IN THE MOD

Not because the mod could not: because of what it would cost whoever is
playing. In the client a body is capped at 8000000 bytes by `fetchURL`, so
anything over about 5.7 MB has to go in pieces, uploads are 20 seconds apart
by design, and every read, base64 and hash happens on the thread drawing the
game. None of that applies to a process run while nobody is playing, and the
server takes 12 MiB decoded in one request, which is more than the largest
file measured here (8.5 MB).

WHAT THE SERVER WILL AND WILL NOT TAKE

    30 replay uploads an hour, per account   the real bottleneck
    300 battle declarations an hour          not a bottleneck, 5 to a request
    12 MiB per replay, decoded

And a floor on the date: `packages/core/src/battles/ingest.ts` refuses any
battle that started before the first of LAST month, because the battles table
is partitioned by month and an older row would land in the DEFAULT partition,
where the month it belonged to can never be attached afterwards. Such a file
is written down as `too_old` and left alone; it is not an error, and not a
failure of this tool.

**That floor moves on the first of every month.** On 1 November the oldest
month accepted becomes October, and every September replay still on disk
stops being sendable for good. At 30 an hour a thousand files take a day and
a half, so the arithmetic is worth doing before the month turns.

RESUMING

Every file's outcome is written down as it happens, so an interrupted run
costs nothing and a second run sends nothing twice. The quotas' own clock is
written down with it: a run started ten minutes after the last one does not
get to spend thirty fresh uploads, and does not have to learn that from a
429.
"""
from __future__ import annotations

import argparse
import base64
import calendar
import hashlib
import importlib.util
import json
import os
import struct
import sys
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "unicum"

#: Magic at the top of every replay, from the client's own writer.
MAGIC = b"\x12\x32\x34\x11"

#: Enough of the front of a file to hold both JSON blocks.
HEADER_BYTES = 262144

#: The quotas, read off the routes that enforce them rather than guessed.
REPLAYS_PER_HOUR = 30
BATTLES_PER_HOUR = 300
HOUR = 3600.0

#: Battles to a declaration request, which is what the mod sends.
BATCH = 5

#: Where the run's memory lives, beside the mod's own state.
STATE = Path("mods") / "configs" / "unicum" / "backfill.json"

#: Outcomes that are done with: the file is never looked at again.
DONE = ("stored", "already_stored", "no_results", "not_a_player", "not_mine")

#: Outcomes worth coming back to, should the floor ever move.
LATER = ("too_old",)

#: The least time between two writes of the run's record.
_SAVE_EVERY = 5.0

#: What this calls itself on the wire.
#:
#: Required, not a courtesy. The site sits behind Cloudflare, which bans
#: `Python-urllib/3.x` on sight: every request comes back 403 with `error code:
#: 1010`, the browser-signature ban, before it reaches the app at all. Saying
#: plainly what this is gets through, and the alternative -- borrowing a real
#: browser's string -- would be lying to a WAF about who is calling.
USER_AGENT = "unicum.gg-mod backfill (+https://github.com/unicum-gg/unicum.gg-mod)"

#: What `upload` answers when the request never reached the API.
_UNREACHED = "\x00unreached"

#: Declaration failures in a row before a run gives up.
#:
#: Without it, a wrong secret or a WAF in the way walks the whole folder at a
#: few hundred requests an hour, failing identically every time and saying so
#: three thousand times. Whatever is wrong at the fourth attempt is not going
#: to be right at the three hundredth.
_MAX_IN_A_ROW = 3


def mod_module(name: str):
    """`unicum.<dotted name>` on its own, without the package pulling in the game.

    `src/unicum/__init__.py` imports the whole mod, which imports `gui` and
    `BigWorld`, so the ordinary import fails outside the client. Loading the
    files by path gives the real `payload` and the real answer readers, which
    is the point: the body this sends is built by the code that builds it in
    the game, so the two cannot drift apart.

    Every package along the way is created first, and given a `__path__`, so
    that a module's own `from unicum.battles.naming import cluster` resolves
    the same way it does in the client.
    """
    parts = name.split(".")
    here = SRC
    dotted = "unicum"
    if dotted not in sys.modules:
        package = types.ModuleType(dotted)
        package.__path__ = [str(here)]
        sys.modules[dotted] = package
    for depth, part in enumerate(parts):
        dotted += "." + part
        last = depth == len(parts) - 1
        if dotted in sys.modules:
            here = here / part
            continue
        folder = here / part
        if folder.is_dir() and not last:
            package = types.ModuleType(dotted)
            package.__path__ = [str(folder)]
            sys.modules[dotted] = package
            here = folder
            continue
        spec = importlib.util.spec_from_file_location(dotted, here / (part + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[dotted] = module
        spec.loader.exec_module(module)
        here = folder
    return sys.modules[dotted]


def blocks(path: Path) -> list:
    """The JSON blocks at the front of a replay, parsed; [] if it has none.

    Reads the header only. The blocks are not encrypted, so this never touches
    Blowfish and never inflates anything.
    """
    try:
        with open(path, "rb") as handle:
            head = handle.read(HEADER_BYTES)
    except OSError:
        return []
    if len(head) < 12 or head[:4] != MAGIC:
        return []
    try:
        count = struct.unpack_from("<I", head, 4)[0]
        if count > 16:
            return []
        at, out = 8, []
        for _ in range(count):
            if at + 4 > len(head):
                break
            size = struct.unpack_from("<I", head, at)[0]
            at += 4
            if at + size > len(head):
                # Runs past the header, which only the stream does.
                break
            out.append(json.loads(head[at:at + size].decode("utf-8")))
            at += size
        return out
    except (ValueError, UnicodeDecodeError, struct.error):
        return []


def battle_of(path: Path, extract) -> tuple:
    """(body, owning account id) for this replay; body None if it says too little."""
    parts = blocks(path)
    meta = parts[0] if parts and isinstance(parts[0], dict) else {}
    owner = str(meta.get("playerID") or "")
    results = None
    for part in parts[1:]:
        candidate = part[0] if isinstance(part, list) and part else part
        if isinstance(candidate, dict) and candidate.get("arenaUniqueID"):
            results = candidate
            break
    if results is None:
        return None, owner
    arena = (meta.get("mapName"), meta.get("gameplayID"))
    version = meta.get("clientVersionFromXml") or meta.get("clientVersionFromExe")
    return extract.payload(results, arena, version), owner


def links(game: Path) -> dict:
    """{account id: secret} from the client's own account.json.

    The mod's own bearer token, drawn by the mod and hashed to the site;
    nothing here belongs to Wargaming. Which one is used matters: the server
    checks that the account speaking was in the battle it describes.
    """
    try:
        with open(game / "mods" / "configs" / "unicum" / "account.json") as handle:
            saved = json.load(handle)
        return {str(k): v for k, v in (saved.get("links") or {}).items()}
    except (OSError, ValueError):
        return {}


def _plain(seconds: float) -> str:
    """A duration read without converting it."""
    seconds = int(max(0, seconds))
    if seconds < 90:
        return "%ds" % seconds
    if seconds < 5400:
        return "%dmin" % round(seconds / 60.0)
    return "%.1fh" % (seconds / 3600.0)


class Quota:
    """A sliding hour, so a run starts at full speed and then settles.

    Not one sleep of `3600 / limit` between calls: the first thirty cost
    nothing, and pacing them would hold back a window the server is willing
    to spend at once. The stamps persist, so stopping and starting cannot
    spend the same window twice.
    """

    def __init__(self, limit: int, stamps: list, label: str):
        self._limit = limit
        self._label = label
        self._stamps = [float(s) for s in stamps]

    def _current(self, now: float) -> list:
        self._stamps = [s for s in self._stamps if now - s < HOUR]
        return self._stamps

    def room(self, announce=print) -> None:
        """Returns once there is room, sleeping while the hour is full."""
        while True:
            now = time.time()
            if len(self._current(now)) < self._limit:
                return
            rest = HOUR - (now - min(self._stamps)) + 1.0
            announce("  %s quota spent (%d/h); waiting %s"
                     % (self._label, self._limit, _plain(rest)))
            time.sleep(max(1.0, rest))

    def spend(self) -> None:
        self._stamps.append(time.time())

    def hold(self, seconds: float, announce=print) -> None:
        """Stay quiet for as long as the server asked, after a 429."""
        announce("  the server is rate limiting %s; waiting %s"
                 % (self._label, _plain(seconds)))
        time.sleep(max(1.0, seconds))

    def stamps(self) -> list:
        return self._current(time.time())

    def left(self) -> int:
        return max(0, self._limit - len(self._current(time.time())))


class State:
    """What became of each file, and the quotas' own clock.

    On disk because the run is long and interruptible, and because sending a
    replay twice spends an upload that the next file wanted. Keyed by file
    name, which is unique within the folder.
    """

    def __init__(self, path: Path):
        self._path = path
        self._saved = 0.0
        self.files: dict = {}
        self.replay_stamps: list = []
        self.battle_stamps: list = []
        try:
            with open(path) as handle:
                saved = json.load(handle)
            self.files = saved.get("files") or {}
            self.replay_stamps = saved.get("replayStamps") or []
            self.battle_stamps = saved.get("battleStamps") or []
        except (OSError, ValueError):
            pass

    def outcome(self, name: str) -> str:
        return (self.files.get(name) or {}).get("state", "")

    def put(self, name: str, state: str, **extra) -> None:
        row = {"state": state, "at": int(time.time())}
        row.update({key: value for key, value in extra.items() if value})
        self.files[name] = row

    def save(self, replays: Quota, battles: Quota, force: bool = False) -> None:
        """Write the record down, at most every `_SAVE_EVERY` seconds.

        Rate limited because a pass over twelve thousand files would otherwise
        rewrite the whole thing a few thousand times, and what is at stake is
        small: the most a crash between two saves can cost is a handful of
        files looked at twice. `force` is for the end of a run and for the
        moments the caller knows are worth a write of their own.
        """
        now = time.time()
        if not force and now - self._saved < _SAVE_EVERY:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps({
            "files": self.files,
            "replayStamps": replays.stamps(),
            "battleStamps": battles.stamps(),
        })
        # Written whole and moved over the old one: a run killed mid-write
        # would otherwise lose the record of all it had already sent.
        temporary = self._path.with_suffix(".tmp")
        with open(temporary, "w") as handle:
            handle.write(blob)
        # Windows hands out a brief handle on a file the moment it appears, to
        # whatever indexes or scans it, and a rename over an existing file
        # fails outright while that handle is open. Measured here: a run
        # saving a few thousand times hit it. Retried rather than fatal,
        # because the alternative is losing a whole pass to a virus scanner.
        for attempt in range(6):
            try:
                os.replace(temporary, self._path)
                self._saved = now
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.2 * (attempt + 1))


def post(url: str, secret: str, body: str, timeout: float = 180.0) -> tuple:
    """(status, text, retry after) for one request; status 0 when none came back."""
    request = urllib.request.Request(
        url, data=body.encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer %s" % secret,
                 "Content-Type": "application/json",
                 "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return answer.status, answer.read().decode("utf-8", "replace"), 0.0
    except urllib.error.HTTPError as err:
        rest = err.headers.get("Retry-After") if err.headers else None
        try:
            rest = float(rest)
        except (TypeError, ValueError):
            rest = 0.0
        return err.code, err.read().decode("utf-8", "replace"), rest
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as err:
        return 0, str(err), 0.0


def floor_utc(now: float | None = None) -> int:
    """The earliest start the server will take, as a unix time.

    A mirror of `earliestAccepted` in `packages/core/src/battles/ingest.ts`:
    midnight UTC on the first of last month, which is the oldest monthly
    partition the battles table has.

    Duplicated here for one reason only, which is cost. Without it a run walks
    the folder oldest first, opens eleven thousand headers and spends two
    thousand declaration requests to be told `too_old` eleven thousand times,
    at three hundred requests an hour. The server stays the authority: this
    only decides what is not worth asking about, and anything this lets
    through is still judged there.
    """
    moment = time.gmtime(now if now is not None else time.time())
    year, month = moment.tm_year, moment.tm_mon - 1
    if month < 1:
        year, month = year - 1, 12
    # timegm, not mktime less an offset: `time.timezone` is the standard
    # offset and says nothing about whether daylight saving is on today, so
    # the floor would move by an hour twice a year for no reason.
    return calendar.timegm((year, month, 1, 0, 0, 0, 0, 1, 0))


#: How far a name may sit before the floor and still be worth opening.
#:
#: A name is local time (`20260901_0007`) while the floor is UTC, and the
#: battle's real start comes from the server's own clock, so the two can
#: disagree by a timezone. Two days is far more slack than any offset, and it
#: is only used to decide whether to read a header.
_NAME_SLACK = 2 * 86400


def name_time(name: str) -> float:
    """What the name says the battle started, as a unix time; 0 if unreadable."""
    try:
        return time.mktime((int(name[0:4]), int(name[4:6]), int(name[6:8]),
                            int(name[9:11]), int(name[11:13]), 0, 0, 1, -1))
    except (ValueError, OverflowError):
        return 0.0


def _reached_app(status: int, text: str) -> bool:
    """Whether the API itself answered, rather than something in front of it.

    A quota is only spent by a request the API saw. Cloudflare's own refusals
    never get that far: a browser-signature ban comes back 403 with the body
    `error code: 1010`, and a request that times out comes back with nothing
    at all. Counting either against the hour meant a run sat out a window the
    server had not touched -- 296 blocked requests once cost an hour of
    waiting for quota that was never spent.

    Told apart by the body being JSON, which everything this API answers is,
    and the edge's errors are not. A 429 is handled before this is asked,
    since that one proves the API counted the request.
    """
    if status == 200:
        return True
    try:
        return isinstance(json.loads(text), dict)
    except (TypeError, ValueError):
        return False


def stamped(name: str) -> bool:
    """Whether a name carries its battle's start, as `20261027_1800_...`.

    The client's format under the "all" recording setting. The two names it
    uses otherwise, `replay_last_battle` and `temp`, say nothing about when
    they were written and are reused for every battle, so they are left to
    the mod, which is watching the battle they belong to.
    """
    return (len(name) > 13 and name[:8].isdigit() and name[8] == "_"
            and name[9:13].isdigit() and name[13] == "_")


def declare(store, bodies: dict, secret: str, api: str, quota: Quota) -> dict:
    """{arena id: 'stored'|'known'|reason} for one batch of battles.

    Read with the mod's own `read_answer`, which answers None for a body that
    names none of its three lists. That matters as much here as in the game:
    a login page or a CDN error served with a 200 must not read as "nothing
    was stored, carry on", or a run would march through the whole folder
    marking everything refused.
    """
    quota.room()
    status, text, rest = post("%s/api/game/battles" % api, secret,
                              json.dumps({"battles": list(bodies.values())}))
    if status == 429:
        quota.hold(rest or 900.0)
        return {}
    if not _reached_app(status, text):
        print("  the request did not reach the API (%s: %s); nothing spent"
              % (status, text.strip()[:90] or "no answer"))
        return {}
    quota.spend()
    if status != 200:
        print("  the server answered %s to a declaration: %s"
              % (status, text.strip()[:160] or "no body"))
        return {}
    answer = store.read_answer(text)
    if answer is None:
        print("  a declaration answer could not be read; batch kept")
        return {}
    stored, known, refused = answer
    out = {arena: "stored" for arena in stored}
    out.update({arena: "known" for arena in known})
    out.update({arena: reason for arena, reason in refused})
    return out


def upload(answers, path: Path, arena: str, started: int, secret: str,
           api: str, quota: Quota) -> str:
    """The outcome of sending one file, as the server named it.

    base64 inside JSON because that is what the route accepts, and the hash
    rides along so a body cut short in transit is caught rather than archived.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as err:
        return "unreadable: %s" % err
    body = json.dumps({"replay": base64.b64encode(raw).decode("ascii"),
                       "sha256": hashlib.sha256(raw).hexdigest()})
    quota.room()
    url = "%s/api/game/battles/%s/replay?startedAt=%d" % (api.rstrip("/"), arena, started)
    status, text, rest = post(url, secret, body)
    if status == 429:
        quota.hold(rest or 900.0)
        return ""
    if not _reached_app(status, text):
        # Apart from "" on purpose: "" means the hour was full and this file
        # is owed another go, while this means nothing is getting through and
        # the caller should stop rather than try it on all 1,473 of them.
        print("  the upload did not reach the API (%s: %s); nothing spent"
              % (status, text.strip()[:90] or "no answer"))
        return _UNREACHED
    quota.spend()
    if status != 200:
        # A refusal the mod can act on comes back 200 with `refused`; a 4xx
        # carries `error` and is about the request, not about the battle.
        try:
            named = (json.loads(text) or {}).get("error")
        except (TypeError, ValueError):
            named = None
        return "%s (http %s)" % (named, status) if named else "http %s" % status
    answer = answers.read_answer(text)
    if answer is None:
        return "unreadable answer"
    return "stored" if answer[0] == "stored" else answer[1]


def selfcheck() -> int:
    """The date arithmetic, which is the part of this that can be wrong quietly.

    Not in `tools/selftest.py`: that suite runs under the client's Python 2.7,
    by design and by its own docstring, and this file is Python 3. The build
    tools beside it are untested there for the same reason, so this keeps its
    own cases rather than pretending to be covered.

    Why these cases: a wrong floor does not fail, it silently refuses a month
    of replays or offers a month the server will refuse, and the month before
    January is the one every hand-rolled version of this gets wrong.
    """
    failed = []

    def want(got, expected, what):
        print("  %-46s %s" % (what, "ok" if got == expected else
                              "FAILED: %r, wanted %r" % (got, expected)))
        if got != expected:
            failed.append(what)

    def floor_on(day):
        at = calendar.timegm(time.strptime(day + " 12:00", "%Y-%m-%d %H:%M"))
        return time.strftime("%Y-%m-%d", time.gmtime(floor_utc(at)))

    want(floor_on("2026-10-28"), "2026-09-01", "the floor is the first of last month")
    want(floor_on("2026-01-15"), "2025-12-01", "January looks back to December")
    want(floor_on("2026-01-01"), "2025-12-01", "and so does the first of January")
    want(floor_on("2026-03-01"), "2026-02-01", "the first of a month is already in it")
    want(floor_on("2026-12-31"), "2026-11-01", "December looks back to November")

    want(stamped("20260901_0227_usa-A189_Ares_90_127_japort.wotreplay"), True,
         "a dated name is recognised")
    want(stamped("replay_last_battle.wotreplay"), False,
         "the name reused for every battle is not")
    want(stamped("temp.wotreplay"), False, "nor the recording in progress")

    want(time.strftime("%Y-%m-%d %H:%M",
                       time.localtime(name_time("20260901_0227_x.wotreplay"))),
         "2026-09-01 02:27", "a name gives its own date back")
    want(name_time("not_a_date_x.wotreplay"), 0.0, "and an odd name gives nothing")

    # The mod's own code has to load, or everything above is beside the point.
    try:
        extract = mod_module("battles.extract")
        store = mod_module("battles.store")
        answers = mod_module("replays.store")
        want(callable(extract.payload) and callable(store.read_answer)
             and callable(answers.read_answer), True,
             "the mod's payload builder and answer readers load")
    except Exception as err:
        want("could not load: %s" % err, True, "the mod's own modules load")

    print("\n%s" % ("all checks passed" if not failed else
                    "%d check(s) failed" % len(failed)))
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selfcheck", action="store_true",
                        help="check this tool's own date arithmetic and exit")
    parser.add_argument("--game", default=r"C:/Games/World_of_Tanks_EU",
                        help="the client whose replays folder is read")
    parser.add_argument("--send", action="store_true",
                        help="actually send; without it nothing leaves the machine")
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after this many files have been sent")
    parser.add_argument("--api", default="https://unicum.gg", help="the API to send to")
    parser.add_argument("--retry-old", action="store_true",
                        help="look again at files once refused as too old")
    args = parser.parse_args()

    if args.selfcheck:
        return selfcheck()

    game = Path(args.game)
    folder = game / "replays"
    if not folder.is_dir():
        print("no replays folder at %s" % folder)
        return 1
    secrets = links(game)
    if not secrets:
        print("no linked account in %s" % (game / "mods/configs/unicum/account.json"))
        return 1

    extract = mod_module("battles.extract")
    store = mod_module("battles.store")
    answers = mod_module("replays.store")
    uploads = mod_module("replays.uploader")
    state = State(game / STATE)
    replay_quota = Quota(REPLAYS_PER_HOUR, state.replay_stamps, "upload")
    battle_quota = Quota(BATTLES_PER_HOUR, state.battle_stamps, "declaration")

    names = sorted(n for n in os.listdir(folder)
                   if n.lower().endswith(".wotreplay") and stamped(n))
    skip = DONE if args.retry_old else DONE + LATER
    todo = [n for n in names if state.outcome(n) not in skip]
    floor = floor_utc()
    inside = sum(1 for n in todo if name_time(n) + _NAME_SLACK >= floor)
    print("%d replay(s) on disk, %d still to look at" % (len(names), len(todo)))
    print("the server takes battles from %s on; %d of those are in range"
          % (time.strftime("%Y-%m-%d", time.gmtime(floor)), inside))
    print("quota left this hour: %d upload(s), %d declaration(s)"
          % (replay_quota.left(), battle_quota.left()))
    if not args.send:
        print("\nwithout --send nothing is sent. Reading headers only.\n")

    counts: dict = {}
    sent = 0
    failures = 0
    stalls = 0
    # In batches, oldest first: the oldest are the ones closest to falling out
    # of the window the server accepts, and the newest are the ones the mod has
    # most likely already sent.
    for at in range(0, len(todo), BATCH):
        chunk = todo[at:at + BATCH]
        bodies, owners, paths = {}, {}, {}
        for name in chunk:
            # By name first, which costs no disk at all. Only what might be
            # inside the window is opened.
            at = name_time(name)
            if at and at + _NAME_SLACK < floor:
                state.put(name, "too_old")
                counts["too_old"] = counts.get("too_old", 0) + 1
                continue
            body, owner = battle_of(folder / name, extract)
            if body is None:
                state.put(name, "no_results")
                counts["no_results"] = counts.get("no_results", 0) + 1
                continue
            if owner and owner not in secrets:
                state.put(name, "not_mine", owner=owner)
                counts["not_mine"] = counts.get("not_mine", 0) + 1
                continue
            if body["startedAt"] < floor:
                # The name was within the slack but the battle's own start,
                # which is the server's clock, is not.
                state.put(name, "too_old", battle=body["arenaUniqueId"])
                counts["too_old"] = counts.get("too_old", 0) + 1
                continue
            arena = body["arenaUniqueId"]
            bodies[arena] = body
            owners[arena] = owner or next(iter(secrets))
            paths[arena] = name
        if not bodies:
            state.save(replay_quota, battle_quota)
            continue
        if not args.send:
            shown = counts.get("would send", 0)
            for arena, name in paths.items():
                if shown < 8:
                    print("  would send %s (battle %s)" % (name, arena))
                    shown += 1
            counts["would send"] = counts.get("would send", 0) + len(bodies)
            continue

        # One secret per request, because the server checks the speaker was in
        # the battle. A batch mixing two accounts is split by account.
        by_account: dict = {}
        for arena in bodies:
            by_account.setdefault(owners[arena], []).append(arena)
        verdicts: dict = {}
        for account, arenas in by_account.items():
            verdicts.update(declare(
                store, {a: bodies[a] for a in arenas},
                secrets[account], args.api, battle_quota))
        if not verdicts:
            failures += 1
            if failures >= _MAX_IN_A_ROW:
                print("\n%d declarations in a row told us nothing; stopping so "
                      "this does not walk the whole folder failing." % failures)
                state.save(replay_quota, battle_quota, force=True)
                _report(counts, state, game)
                return 1
            continue
        failures = 0

        for arena, name in paths.items():
            verdict = verdicts.get(arena)
            if verdict is None:
                continue  # Nothing was learned; the file stays on the list.
            if verdict not in ("stored", "known"):
                state.put(name, verdict, battle=arena)
                counts[verdict] = counts.get(verdict, 0) + 1
                print("  %-52s %s" % (name[:52], verdict))
                continue
            outcome = upload(answers, folder / name, arena,
                             bodies[arena]["startedAt"], secrets[owners[arena]],
                             args.api, replay_quota)
            if outcome == _UNREACHED:
                stalls += 1
                if stalls >= _MAX_IN_A_ROW:
                    print("\n%d uploads in a row never reached the API; stopping."
                          % stalls)
                    state.save(replay_quota, battle_quota, force=True)
                    _report(counts, state, game)
                    return 1
                continue
            if not outcome:
                continue  # Rate limited; try this file again next pass.
            stalls = 0
            state.put(name, outcome, battle=arena)
            counts[outcome] = counts.get(outcome, 0) + 1
            sent += 1
            print("  %-52s %s  (%d/%d)" % (name[:52], outcome, sent, len(todo)))
            # Forced: an upload just spent one of thirty an hour, and that is
            # the one thing in here worth a write of its own.
            state.save(replay_quota, battle_quota, force=True)
            if outcome in uploads.Uploader.CLOSED:
                # The archive is full, or this account's replays are not kept.
                # Neither is "try the next file", so the run ends here rather
                # than asking the same question twelve thousand times.
                print("\nthe server is not taking replays (%s); stopping" % outcome)
                _report(counts, state, game)
                return 0
            if args.limit and sent >= args.limit:
                print("\nstopping at --limit %d" % args.limit)
                state.save(replay_quota, battle_quota, force=True)
                _report(counts, state, game)
                return 0
        state.save(replay_quota, battle_quota)

    state.save(replay_quota, battle_quota, force=True)
    _report(counts, state, game)
    return 0


def _report(counts: dict, state: State, game: Path) -> None:
    print("")
    for name, count in sorted(counts.items(), key=lambda pair: -pair[1]):
        print("  %-24s %d" % (name, count))
    waiting = sum(1 for row in state.files.values() if row.get("state") in LATER)
    if waiting:
        print("\n  %d file(s) are older than the months the table holds. They stay"
              % waiting)
        print("  on the list, and --retry-old looks at them again if that changes.")
    print("\n  state in %s" % (game / STATE))


if __name__ == "__main__":
    sys.exit(main())

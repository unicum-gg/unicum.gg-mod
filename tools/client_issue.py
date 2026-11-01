"""Keep one client-update issue per WoT version, without daily comments.

Python 3; called by the client workflow, never shipped inside the mod.
Only the marked report belongs to the bot. Everything outside it stays intact.
"""
import json
import os
import re
import subprocess


VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){3}")
LEGACY_REPORT = re.compile(
    r"\AThe live client reads `mods/(?P<live>[0-9]+(?:\.[0-9]+){3})`\. The newest published release, "
    r"`[^`\n]+`, unpacks into `mods/[0-9.]+`, so it installs and does nothing\."
    r"\n\nSources read: upstream mirror `[^`\n]+`, hub page `[^`\n]+`\."
    r"\n\nThis has to be cut on a machine with the game installed, because the "
    r"client \.swc and `battleVehicleMarkersApp\.swf` have to come off that install: "
    r"the mirror carries a different build of both, and the markers app ships "
    r"inside the package and replaces the client's own\."
    r"\n\n```\npython tools/release\.py\n```"
)


def gh_json(arguments, payload=None):
    try:
        result = subprocess.run(
            ["gh", "api"] + arguments,
            input=json.dumps(payload) if payload is not None else None,
            text=True, capture_output=True, check=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError("GitHub API request failed: %s" % (error.stderr or str(error))) from error
    if "--paginate" not in arguments:
        return json.loads(result.stdout)
    # gh emits one JSON array per page. Decode that stream without requiring
    # --slurp, which is absent from older CLI installations used locally.
    pages = []
    remaining = result.stdout.strip()
    decoder = json.JSONDecoder()
    while remaining:
        page, end = decoder.raw_decode(remaining)
        pages.append(page)
        remaining = remaining[end:].strip()
    return pages


def sync_issue(repo, live, report, title, suffix="", api=gh_json):
    if not VERSION.fullmatch(live):
        raise ValueError("invalid client version")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid repository")
    start = "<!-- client-watch:%s:start -->" % live
    end = "<!-- client-watch:%s:end -->" % live
    block = start + "\n" + report.strip() + "\n" + end
    legacy_title = re.compile(
        r"Client " + re.escape(live) + r" is live; the published package targets [0-9.]+\Z"
    )

    def matches_legacy_body(issue):
        match = LEGACY_REPORT.match(issue.get("body") or "")
        return match is not None and match.group("live") == live

    pages = api(["--paginate", "repos/%s/issues?state=all&per_page=100" % repo])
    candidates = [issue for page in pages for issue in page
                  if "pull_request" not in issue
                  and issue.get("user", {}).get("login") == "github-actions[bot]"
                  and (start in (issue.get("body") or "")
                       or end in (issue.get("body") or "")
                       or legacy_title.fullmatch(issue["title"])
                       or matches_legacy_body(issue))]
    if not candidates:
        return api(["--method", "POST", "repos/%s/issues" % repo, "--input", "-"],
                   {"title": title, "body": block + suffix})

    # Prefer the migrated issue, then the oldest, including closed issues.
    issue = min(candidates, key=lambda item: (start not in (item.get("body") or ""),
                                             item["number"]))
    previous = issue.get("body") or ""
    if start in previous or end in previous:
        if previous.count(start) != 1 or previous.count(end) != 1:
            raise ValueError("ambiguous managed issue section")
        left, rest = previous.split(start, 1)
        _, right = rest.split(end, 1)
        body = left + block + right
    else:
        # The old workflow owned this exact prefix. A maintainer's additions
        # after it (including checked boxes) are outside the managed section.
        legacy = LEGACY_REPORT.match(previous)
        body = block + previous[legacy.end():] if legacy else block + "\n\n" + previous
    changes = {}
    if body != previous:
        changes["body"] = body
    if legacy_title.fullmatch(issue["title"]):
        changes["title"] = title
    if issue.get("state") == "closed":
        changes["state"] = "open"
    # Only migrate the old generated title. Preserve custom maintainer titles:
    # the marker identifies the issue even after it has been renamed.
    if changes:
        return api(["--method", "PATCH", "repos/%s/issues/%s" % (repo, issue["number"]),
                    "--input", "-"], changes)
    print("Client %s: #%s is unchanged" % (live, issue["number"]))
    return issue


def report_from_env():
    live, shipped, tag = (os.environ[key] for key in ("LIVE", "SHIPPED", "TAG"))
    upstream = os.environ.get("UPSTREAM") or "no answer"
    hub = os.environ.get("HUB") or "no answer"
    return (
        "The live client reads `mods/%s`. The newest published release, `%s`, "
        "unpacks into `mods/%s`, so it installs and does nothing.\n\n"
        "Sources read: upstream mirror `%s`, hub page `%s`.\n\n"
        "This has to be cut on a machine with the game installed, because the "
        "client .swc and `battleVehicleMarkersApp.swf` have to come off that install: "
        "the mirror carries a different build of both, and the markers app ships "
        "inside the package and replaces the client's own.\n\n"
        "```\npython tools/release.py\n```"
    ) % (live, tag, shipped, upstream, hub)


if __name__ == "__main__":
    live = os.environ["LIVE"]
    sync_issue(os.environ["GH_REPO"], live, report_from_env(),
               "Client %s is live; a release is due" % live)

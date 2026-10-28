"""Offline regressions for repeated client-watch runs and legacy issues."""
import copy
import subprocess
import os
import unittest
from unittest.mock import patch

from client_issue import gh_json, report_from_env, sync_issue


LIVE = "2.4.1.1"
REPO = "unicum-gg/unicum.gg-mod"
ENV = dict(LIVE=LIVE, SHIPPED="2.4.1.0", TAG="v0.6.0",
           UPSTREAM="2.4.1.0", HUB=LIVE)


class FakeAPI:
    def __init__(self, issues=()):
        self.issues = copy.deepcopy(list(issues))
        self.writes = []

    def __call__(self, arguments, payload=None):
        if payload is None:
            # Two pages prove that an older issue is still found.
            return [self.issues[:1], self.issues[1:]]
        self.writes.append((arguments, copy.deepcopy(payload)))
        if "POST" in arguments:
            issue = dict(number=max([i["number"] for i in self.issues] or [6]) + 1,
                         state="open", user={"login": "github-actions[bot]"},
                         **payload)
            self.issues.append(issue)
        else:
            number = int(arguments[-3].rsplit("/", 1)[1])
            issue = next(item for item in self.issues if item["number"] == number)
            issue.update(payload)
        return copy.deepcopy(issue)


class ClientIssueTests(unittest.TestCase):
    def test_cli_paginated_json_stream_is_read_without_slurp(self):
        with patch("client_issue.subprocess.run") as run:
            run.return_value.stdout = '[{"number":1}]\n[{"number":2}]\n'
            self.assertEqual(gh_json(["--paginate", "repos/test/repo/issues"]),
                             [[{"number": 1}], [{"number": 2}]])

    def test_api_failure_exposes_error_and_never_creates_an_issue(self):
        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="HTTP 403: forbidden")
        with patch("client_issue.subprocess.run", side_effect=error) as run:
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                sync_issue(REPO, LIVE, "report", "title")
        self.assertEqual(run.call_count, 1)

    def sync(self, api, report="Current report", live=LIVE):
        return sync_issue(REPO, live, report, "Client %s is live; a release is due" % live,
                          api=api)

    def test_three_identical_runs_create_one_issue_without_comments(self):
        api = FakeAPI()
        for _ in range(3):
            self.sync(api)
        self.assertEqual(len(api.issues), 1)
        self.assertEqual(len(api.writes), 1)
        self.assertIn("POST", api.writes[0][0])

    def test_new_release_still_behind_reuses_same_client_issue(self):
        api = FakeAPI()
        with patch.dict(os.environ, dict(ENV, SHIPPED="2.4.0.2", TAG="v0.5.0")):
            self.sync(api, report_from_env())
        with patch.dict(os.environ, ENV):
            self.sync(api, report_from_env())
            self.sync(api, report_from_env())
        self.assertEqual(len(api.issues), 1)
        self.assertEqual(len(api.writes), 2)
        self.assertIn("`v0.6.0`", api.issues[0]["body"])
        self.assertNotIn("`v0.5.0`", api.issues[0]["body"])

    def test_existing_issue_on_later_page_is_reused(self):
        api = FakeAPI()
        self.sync(api)
        unrelated = dict(number=1, title="Unrelated", body="", state="open",
                         user={"login": "maintainer"})
        api.issues.insert(0, unrelated)
        self.sync(api)
        self.assertEqual(len(api.writes), 1)

    def test_new_report_preserves_notes_title_and_checked_boxes(self):
        api = FakeAPI()
        self.sync(api)
        issue = api.issues[0]
        issue["body"] = "Maintainer introduction\n\n" + issue["body"] + "\n\n- [x] Tested\nNotes"
        issue["title"] = "Maintainer title"
        self.sync(api, "A newer package still targets the old client")
        self.assertTrue(issue["body"].startswith("Maintainer introduction\n\n"))
        self.assertTrue(issue["body"].endswith("\n\n- [x] Tested\nNotes"))
        self.assertIn("A newer package", issue["body"])
        self.assertNotIn("Current report", issue["body"])
        self.assertEqual(issue["title"], "Maintainer title")
        self.sync(api, "A newer package still targets the old client")
        self.assertEqual(len(api.writes), 2)

    def test_closed_issue_is_reopened_once_without_comment(self):
        api = FakeAPI()
        self.sync(api)
        api.issues[0]["state"] = "closed"
        self.sync(api)
        self.assertEqual(api.writes[-1][1], {"state": "open"})
        self.sync(api)
        self.assertEqual(len(api.writes), 2)

    def test_legacy_report_is_migrated_with_maintainer_notes_intact(self):
        with patch.dict(os.environ, ENV):
            legacy = report_from_env()
        api = FakeAPI([dict(number=7, state="open", user={"login": "github-actions[bot]"},
                            title="Client %s is live; the published package targets 2.4.1.0" % LIVE,
                            body=legacy + "\n\n- [x] Test in game\nMaintainer notes")])
        self.sync(api, "Updated release information")
        self.assertEqual(len(api.issues), 1)
        self.assertNotIn(legacy, api.issues[0]["body"])
        self.assertEqual(api.issues[0]["title"], "Client %s is live; a release is due" % LIVE)
        self.assertTrue(api.issues[0]["body"].endswith("\n\n- [x] Test in game\nMaintainer notes"))
        self.sync(api, "Updated release information")
        self.assertEqual(len(api.writes), 1)

    def test_unrecognized_legacy_body_is_preserved(self):
        issue = dict(number=7, state="open", user={"login": "github-actions[bot]"},
                     title="Client %s is live; the published package targets 2.4.0.2" % LIVE,
                     body="Entirely rewritten by the maintainer\n- [x] Tested")
        api = FakeAPI([issue])
        self.sync(api)
        self.assertTrue(api.issues[0]["body"].endswith(issue["body"]))

    def test_renamed_legacy_issue_is_migrated_without_resetting_title(self):
        with patch.dict(os.environ, ENV):
            legacy = report_from_env()
        api = FakeAPI([dict(number=7, state="open", user={"login": "github-actions[bot]"},
                            title="Custom release request", body=legacy + "\n\n- [x] Tested")])
        self.sync(api, "Updated report")
        self.assertEqual(len(api.issues), 1)
        self.assertEqual(api.issues[0]["title"], "Custom release request")
        self.assertTrue(api.issues[0]["body"].endswith("\n\n- [x] Tested"))
        self.sync(api, "Updated report")
        self.assertEqual(len(api.writes), 1)

    def test_renamed_legacy_issue_for_other_client_is_ignored(self):
        with patch.dict(os.environ, dict(ENV, LIVE="2.4.1.10")):
            legacy = report_from_env()
        api = FakeAPI([dict(number=7, state="open", user={"login": "github-actions[bot]"},
                            title="Custom release request", body=legacy)])
        self.sync(api)
        self.assertEqual(len(api.issues), 2)
        self.assertIn("POST", api.writes[0][0])

    def test_other_authors_pull_requests_and_client_versions_are_ignored(self):
        api = FakeAPI()
        self.sync(api, live="2.4.1.0")
        human = copy.deepcopy(api.issues[0])
        human.update(number=8, user={"login": "maintainer"})
        human["body"] = human["body"].replace("2.4.1.0", LIVE)
        pr = copy.deepcopy(human)
        pr.update(number=9, user={"login": "github-actions[bot]"}, pull_request={})
        api.issues.extend([human, pr])
        self.sync(api)
        self.assertEqual(len(api.writes), 2)
        self.assertIn("POST", api.writes[-1][0])

    def test_damaged_managed_section_fails_without_writing(self):
        for marker in ("start", "end"):
            with self.subTest(marker=marker):
                api = FakeAPI()
                self.sync(api)
                api.issues[0]["body"] = api.issues[0]["body"].replace(
                    ":%s -->" % marker, ":broken -->")
                previous = api.issues[0]["body"]
                with self.assertRaises(ValueError):
                    self.sync(api, "New report")
                self.assertEqual(len(api.issues), 1)
                self.assertEqual(len(api.writes), 1)
                self.assertEqual(api.issues[0]["body"], previous)

    def test_invalid_identity_is_rejected_before_api_calls(self):
        api = FakeAPI()
        with self.assertRaises(ValueError):
            self.sync(api, live="2.4.1.1\nother-output=yes")
        with self.assertRaises(ValueError):
            sync_issue("../repo", LIVE, "report", "title", api=api)
        self.assertEqual(api.issues, [])


if __name__ == "__main__":
    unittest.main()

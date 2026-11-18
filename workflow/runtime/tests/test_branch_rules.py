"""Issue branch naming and legacy manual compatibility without remote writes."""

import copy
from pathlib import Path
import shutil
import unittest

from workflow.runtime import branch_rules, git_tools, publish, validate_config
from workflow.runtime.codex_adapter import ExecutionError
from workflow.runtime.tests import test_run


RUN_ID = "00000000-0000-4000-8000-000000000000"
TEMPLATE = "ai_feature/{date}/{approver}/{issue_title}"


class BranchNamingTests(unittest.TestCase):
    def setUp(self):
        self.config = {"project_id": "sample", "base_branch": "main", "pr_policy": {"target_branch": "main"},
                       "publishing": {"branch_template": TEMPLATE, "manual_branch_template": "ai/{project_id}/{run_id}"}}
        self.report = {"started_at": "2026-11-17T15:00:00+00:00",
                       "approved_issue": {"title": "로그인 화면 개선", "approver": "JunSuHeo"}}

    def test_requested_format_uses_seoul_execution_date_and_approved_identity(self):
        self.assertEqual(publish.branch_name(self.config, RUN_ID, self.report),
                         "ai_feature/26.11.18/JunSuHeo/로그인-화면-개선")
        self.report["started_at"] = "2026-11-17T14:59:59+00:00"
        self.assertEqual(publish.branch_name(self.config, RUN_ID, self.report),
                         "ai_feature/26.11.17/JunSuHeo/로그인-화면-개선")

    def test_same_report_keeps_same_branch_for_later_publication(self):
        self.report["approved_issue"]["approved_at"] = "2026-11-15T01:00:00+00:00"
        first = publish.branch_name(self.config, RUN_ID, self.report)
        self.assertEqual(publish.branch_name(self.config, RUN_ID, copy.deepcopy(self.report)), first)
        self.assertIn("26.11.18", first)

    def test_title_cannot_create_extra_paths_or_git_ref_syntax(self):
        title = " ../로그인 / 개선: [테스트]?*~^\\@{작업}..lock "
        self.report["approved_issue"]["title"] = title
        name = publish.branch_name(self.config, RUN_ID, self.report)
        self.assertEqual(len(name.split("/")), 4)
        self.assertTrue(branch_rules.valid_name(name))
        self.assertIn("로그인", name)
        self.assertNotIn("..", name)
        self.assertNotIn(".lock", name)

    def test_long_unicode_title_is_bounded_without_broken_characters(self):
        component = branch_rules.issue_title_component("한글" * 1000)
        self.assertLessEqual(len(component.encode("utf-8")), 120)
        self.assertTrue(component)
        self.assertNotIn("\ufffd", component)

    def test_unicode_is_normalized_and_unsafe_empty_title_uses_safe_component(self):
        self.assertEqual(branch_rules.issue_title_component("Cafe\u0301 기능"), "Café-기능")
        self.assertEqual(branch_rules.issue_title_component("../:*?[]"), "issue")
        self.assertEqual(branch_rules.issue_title_component("release.lock"), "release-lock")
        self.assertEqual(branch_rules.issue_title_component("version.2 개선"), "version.2-개선")

    def test_manual_requests_keep_legacy_template_without_inventing_issue_data(self):
        for report in (None, {"started_at": self.report["started_at"]}):
            self.assertEqual(publish.branch_name(self.config, RUN_ID, report), "ai/sample/" + RUN_ID)
        del self.config["publishing"]["manual_branch_template"]
        self.assertEqual(publish.branch_name(self.config, RUN_ID), "ai/sample/" + RUN_ID)
        self.config["publishing"]["branch_template"] = "feature/{project_id}/{run_id}"
        self.assertEqual(publish.branch_name(self.config, RUN_ID, self.report), "feature/sample/" + RUN_ID)

    def test_missing_or_unsafe_approved_issue_fields_fail_closed(self):
        for change in ({"approved_issue": {}}, {"approved_issue": None},
                       {"started_at": "2026-11-17T00:00:00"}, {"started_at": "invalid"},
                       {"approved_issue": {"title": "title", "approver": "../someone"}},
                       {"approved_issue": {"title": "", "approver": "someone"}}):
            with self.subTest(change=change), self.assertRaises(ExecutionError):
                publish.branch_name(self.config, RUN_ID, {**self.report, **change})

    def test_unknown_fields_and_format_modifiers_still_fail(self):
        for template in ("ai/{unknown}/{run_id}", "ai/{date}/{approver}", "ai/{date!r}/{approver}/{issue_title}",
                         "ai/{date:>10}/{approver}/{issue_title}", "ai/{}/{run_id}"):
            with self.subTest(template=template), self.assertRaises(ExecutionError):
                config = copy.deepcopy(self.config)
                config["publishing"]["branch_template"] = template
                publish.branch_name(config, RUN_ID, self.report)

    def test_offline_validator_accepts_issue_template_and_rejects_unsafe_rules(self):
        fixture = test_run.EngineTests(methodName="test_task_parsing")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.config["publishing"] = {**self.config["publishing"], "remote": "origin", "draft": True}
        self.assertEqual(validate_config.validate_config(fixture.write(), fixture.root), [])
        fixture.config["publishing"]["manual_branch_template"] = TEMPLATE
        self.assertTrue(validate_config.validate_config(fixture.write(), fixture.root))
        fixture.config["publishing"] = {"remote": "origin", "draft": True, "branch_template": "bad../{date}/{approver}/{issue_title}"}
        self.assertTrue(validate_config.validate_config(fixture.write(), fixture.root))

    @unittest.skipUnless(shutil.which("git"), "Local Git is required")
    def test_generated_unicode_names_pass_actual_git_ref_validation(self):
        for title in ("로그인 화면 개선", "title: /path? [test]", "../.lock", "한글" * 1000):
            self.report["approved_issue"]["title"] = title
            name = publish.branch_name(self.config, RUN_ID, self.report)
            git_tools.Git(Path.cwd()).run("check-ref-format", "--branch", name)


if __name__ == "__main__":
    unittest.main()

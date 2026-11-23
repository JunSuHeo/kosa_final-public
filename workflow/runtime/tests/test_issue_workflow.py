"""Mock Issue intake/approval and real local orchestration; no remote operations."""

import copy
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from workflow.runtime import evidence, issue_workflow as subject, orchestrator, workspace
from workflow.runtime.codex_adapter import CodexCLI, ExecutionError, restricted_environment
from workflow.runtime.github_adapter import GitHubCLI, environment
from workflow.runtime.issue_github import IssueGitHub
from workflow.runtime.tests import test_run, test_publish
from workflow.runtime.simulated_github import SimulatedGitHubCLI, SimulatedNetworkGit


KEY = b"test-signing-key-with-at-least-32-bytes"
BOT = "github-actions[bot]"
PLAN = {"purpose": "Update sample calculation", "summary": ["Preserve calculation contract"],
        "areas": ["Calculation source"], "files": ["sample/src/main.py"],
        "steps": ["Inspect the contract", "Update implementation", "Run configured tests"],
        "tests": ["Unit calculation tests", "E2E calculation tests"],
        "risks": ["Preserve existing inputs and outputs"], "questions": [], "requires_clarification": False,
        "plan_reply_example": ""}


class MemoryGitHub:
    repository = "example/sample"

    def __init__(self):
        self.current = {"number": 1, "title": "Update sample", "body": "Preserve calculation behavior",
                        "user": {"login": "author", "type": "User"}, "state": "open",
                        "created_at": "2026-11-17T00:00:00Z",
                        "url": "https://api.github.com/repos/example/sample/issues/1",
                        "html_url": "https://github.com/example/sample/issues/1"}
        self.records, self.next_id = [], 100
        self.permission = Mock(return_value="write")
        self.preflight = Mock()
        self.fail_write = False

    def issue(self, number):
        return copy.deepcopy(self.current)

    def comments(self, number):
        return copy.deepcopy(self.records)

    def comment(self, comment_id):
        return copy.deepcopy(next(comment for comment in self.records if comment["id"] == comment_id))

    def create_comment(self, number, body, login=BOT, user_type="Bot"):
        if self.fail_write:
            raise ExecutionError("github_failed", "Mock journal failure")
        comment = {"id": self.next_id, "body": body, "user": {"login": login, "type": user_type},
                   "created_at": "2026-11-17T00:00:00Z", "updated_at": "2026-11-17T00:00:00Z",
                   "issue_url": f"https://api.github.com/repos/{self.repository}/issues/{number}"}
        self.next_id += 1
        self.records.append(comment)
        return copy.deepcopy(comment)

    def event(self, command="/approve", login="maintainer", user_type="User"):
        comment = self.create_comment(1, command, login, user_type)
        return {"action": "created", "repository": {"full_name": self.repository},
                "issue": self.issue(1), "comment": comment, "sender": copy.deepcopy(comment["user"])}


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_run.EngineTests(methodName="test_task_parsing")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.write()
        self.github = MemoryGitHub()
        self.analyzer = Mock()
        self.analyzer.analyze.return_value = copy.deepcopy(PLAN)
        self.engine = Mock(side_effect=self.pipeline)
        self.controller = self.new_controller()

    def new_controller(self):
        return subject.IssueController(self.fixture.path, self.fixture.root, self.fixture.results,
            self.github, KEY, BOT, analyzer=self.analyzer, engine=self.engine)

    def pipeline(self, *args, **kwargs):
        report = {"config_sha256": self.controller.config_hash, "run_id": "mock-run",
                  "final_status": "completed", "workflow_status": "completed_simulation"}
        for stage in ("codex", "validation", "publication"):
            try:
                kwargs["stage_callback"](stage, report)
            except ExecutionError as exc:
                return {**report, "final_status": exc.status}
        return report

    def opened(self, **kwargs):
        return self.controller.handle("issues", {"action": "opened", "repository": {"full_name": "example/sample"},
                                                "issue": self.github.issue(1)}, **kwargs)

    def edited(self):
        return self.controller.handle("issues", {"action": "edited", "repository": {"full_name": "example/sample"},
                                                "issue": self.github.issue(1)})

    def test_opened_analyzes_posts_all_sections_and_does_not_execute(self):
        before = workspace.inventory(self.fixture.root / "sample")
        state = self.opened()
        self.assertEqual(state["status"], "awaiting_approval")
        self.analyzer.analyze.assert_called_once()
        self.engine.assert_not_called()
        plan = self.github.comment(state["plan_comment_id"])["body"]
        for text in ("작업 목적", "요구사항 요약", "예상 변경 영역", "예상 변경 파일", "실행 계획",
                     "검증 계획", "위험 요소", "추가 확인", "/approve", "/reject", state["plan_id"], state["snapshot_hash"]):
            self.assertIn(text, plan)
        self.assertEqual(workspace.inventory(self.fixture.root / "sample"), before)
        self.assertTrue((self.controller.receipt_dir / "issue.json").is_file())

    def test_approved_runs_all_stages_and_records_human_and_issue_data(self):
        self.opened()
        event = self.github.event(" /approve   \n")
        state = self.controller.handle("issue_comment", event)
        self.assertEqual(state["status"], "completed", state)
        self.engine.assert_called_once()
        self.assertEqual([item["status"] for item in state["history"]],
                         ["received", "analyzing", "awaiting_approval", "approved", "executing", "validating", "publishing", "completed"])
        context = self.engine.call_args.kwargs["issue_context"]
        self.assertEqual(context["approval_comment_id"], event["comment"]["id"])
        self.assertEqual(context["approver"], "maintainer")
        self.assertEqual(context["body"], self.github.current["body"])
        self.assertEqual(context["approved_plan"], PLAN)
        self.assertEqual(state["approval"]["comment_id"], event["comment"]["id"])

    def test_reject_is_persistent_and_never_calls_engine(self):
        self.opened()
        state = self.controller.handle("issue_comment", self.github.event("/reject"))
        self.assertEqual(state["status"], "rejected")
        self.assertEqual(self.new_controller().load(1)["status"], "rejected")
        self.assertEqual(state["rejection"]["login"], "maintainer")
        self.engine.assert_not_called()

    def test_failure_comment_redacts_credentials_and_escapes_output_markup(self):
        token = "ghp_" + "a" * 36
        check = {"id": "unit", "kind": "unit", "status": "failed", "return_code": 1,
                 "command": {"program": "offline-tests", "args": []}, "reason": "Controlled failure",
                 "stderr": "GITHUB_TOKEN=" + token + "\n</pre><script>alert(1)</script> @reviewer"}
        report = {"validation": {"tests": {"unit": [check], "e2e": []}}}
        comment = subject.test_failure_comment(report)
        self.assertNotIn(token, comment)
        self.assertNotIn("<script>", comment)
        self.assertNotIn("@reviewer", comment)
        self.assertIn("Controlled failure", comment)

    def test_permission_denied_issue_author_and_api_failure_never_execute(self):
        self.opened()
        for permission in ("read", "triage", "none", "unknown", None, "api_failure"):
            with self.subTest(permission=permission):
                self.github.permission.return_value = permission
                self.github.permission.side_effect = RuntimeError() if permission == "api_failure" else None
                state = self.controller.handle("issue_comment", self.github.event(login="author"))
                self.assertEqual(state["status"], "awaiting_approval")
        self.engine.assert_not_called()

    def test_admin_maintain_and_write_are_the_only_supported_permissions(self):
        for permission in ("admin", "maintain", "write"):
            with self.subTest(permission=permission):
                self.setUp()
                self.github.permission.return_value = permission
                self.opened()
                self.assertEqual(self.controller.handle("issue_comment", self.github.event())["status"], "completed")

    def test_missing_plan_is_ignored(self):
        self.assertEqual(self.controller.handle("issue_comment", self.github.event())["status"], "ignored")
        self.engine.assert_not_called()
        self.analyzer.analyze.assert_not_called()

    def test_embedded_and_malformed_commands_are_ignored(self):
        self.opened()
        for body in ("/approvement ", "Make the decision yourself./approve", "/Approve", "/approve 123",
                     "`/approve`", "/reject later", "/reject /approve"):
            with self.subTest(body=body):
                self.assertEqual(self.controller.handle("issue_comment", self.github.event(body))["status"], "ignored")
        self.engine.assert_not_called()
        self.github.permission.assert_not_called()

    def test_duplicate_comment_event_and_restarted_runner_do_not_rerun(self):
        self.opened()
        event = self.github.event()
        self.controller.handle("issue_comment", event)
        for controller in (self.controller, self.new_controller()):
            self.assertEqual(controller.handle("issue_comment", event)["status"], "ignored")
        self.assertEqual(self.engine.call_count, 1)

    def test_duplicate_opened_and_edited_do_not_reanalyze_same_snapshot(self):
        self.opened()
        self.opened()
        self.edited()
        self.analyzer.analyze.assert_called_once()

    def test_failed_analysis_can_be_retried_after_runner_recovery(self):
        self.analyzer.analyze.side_effect = ExecutionError("environment_error", "Mock environment failure")
        state = self.opened()
        self.assertEqual(state["status"], "analysis_failed")
        failed_id = state["plan_id"]
        self.analyzer.analyze.side_effect = None
        self.controller = self.new_controller()
        state = self.opened()
        self.assertEqual(state["status"], "awaiting_approval")
        self.assertNotEqual(state["plan_id"], failed_id)
        self.assertEqual(self.analyzer.analyze.call_count, 2)
        self.engine.assert_not_called()

    def test_provider_auth_failure_is_persisted_without_credentials_and_can_be_retried(self):
        self.analyzer.analyze.side_effect = ExecutionError("codex_provider_auth_missing", "synthetic-private-diagnostic", 1)
        state = self.opened()
        self.assertEqual(state["status"], "analysis_failed")
        self.assertEqual(state["failure_diagnostic"], {"reason": "codex_provider_auth_missing"})
        self.assertNotIn("synthetic-private-diagnostic", json.dumps(state))
        self.analyzer.analyze.side_effect = None
        self.controller = self.new_controller()
        self.assertEqual(self.opened()["status"], "awaiting_approval")
        self.engine.assert_not_called()

    def test_failed_reanalysis_retry_preserves_human_decisions(self):
        self.opened()
        self.analyzer.analyze.side_effect = ExecutionError("environment_error", "Mock environment failure")
        event = self.github.event("/plan Preserve the CLI output format")
        self.assertEqual(self.controller.handle("issue_comment", event)["status"], "analysis_failed")
        self.analyzer.analyze.side_effect = None
        self.controller = self.new_controller()
        state = self.opened()
        self.assertEqual(state["status"], "awaiting_approval")
        self.assertEqual(state["issue"]["additional_decisions"], ["Preserve the CLI output format"])
        self.assertEqual(state["decision_comments"][0]["id"], event["comment"]["id"])
        self.engine.assert_not_called()

    def test_approved_rejected_and_running_states_ignore_new_commands(self):
        self.opened()
        for status in ("approved", "rejected", "executing", "validating", "publishing", "completed"):
            with self.subTest(status=status):
                self.controller.persist(status)
                self.assertEqual(self.controller.handle("issue_comment", self.github.event())["status"], "ignored")
        self.engine.assert_not_called()

    def test_title_and_body_snapshot_mismatch_reanalyze_with_new_plan(self):
        self.opened()
        for field in ("title", "body"):
            with self.subTest(field=field):
                previous = self.controller.state["plan_id"]
                self.github.current[field] += " changed"
                state = self.controller.handle("issue_comment", self.github.event())
                self.assertEqual(state["status"], "awaiting_approval")
                self.assertNotEqual(state["plan_id"], previous)
                self.assertEqual(state["snapshot_hash"], subject.snapshot(self.github.current))
                self.assertIsNone(state["approval"])
        self.engine.assert_not_called()

    def test_edited_invalidates_an_already_approved_ticket(self):
        self.opened()
        event = self.github.event()
        state = self.controller.handle("issue_comment", event, defer_execution=True)
        old_id = state["plan_id"]
        self.github.current["title"] += " changed"
        self.edited()
        self.assertEqual(self.controller.handle("issue_comment", event, execute_plan=old_id)["status"], "ignored")
        self.engine.assert_not_called()

    def test_modified_plan_comment_or_plan_id_is_invalidated(self):
        self.opened()
        plan_id = self.controller.state["plan_comment_id"]
        record = next(comment for comment in self.github.records if comment["id"] == plan_id)
        record["body"] = record["body"].replace(self.controller.state["plan_id"], "another-plan")
        state = self.controller.handle("issue_comment", self.github.event())
        self.assertEqual(state["status"], "awaiting_approval")
        self.assertNotEqual(state["plan_comment_id"], plan_id)
        self.engine.assert_not_called()

    def test_forged_human_state_comment_cannot_override_bot_state(self):
        self.opened()
        body = next(comment["body"] for comment in reversed(self.github.records) if comment["body"].startswith(subject.MARKER))
        self.github.create_comment(1, body, "attacker", "User")
        self.assertEqual(self.controller.handle("issue_comment", self.github.event())["status"], "completed")

    def test_corrupt_trusted_journal_blocks_without_fallback(self):
        self.opened()
        self.github.records[-1]["body"] = self.github.records[-1]["body"].replace('"status": "awaiting_approval"', '"status": "approved"')
        with self.assertRaises(ExecutionError):
            self.controller.handle("issue_comment", self.github.event())
        self.engine.assert_not_called()

    def test_ambiguous_or_incomplete_analysis_is_not_executable(self):
        for change in ({"questions": ["Which behavior is desired?"]}, {"requires_clarification": True}, {"steps": []}):
            with self.subTest(change=change):
                self.analyzer.analyze.return_value = {**copy.deepcopy(PLAN), **change,
                                                      "plan_reply_example": "기존 계산 방식은 유지해 주세요."}
                self.github.current["body"] += " changed"
                state = self.edited()
                self.assertFalse(state["plan_ready"])
                self.assertIn("추가 확인 필요", self.github.comment(state["plan_comment_id"])["body"])
                self.controller.handle("issue_comment", self.github.event())
        self.engine.assert_not_called()

    def test_analysis_failure_or_out_of_scope_files_block(self):
        for value in (None, {}, {**PLAN, "files": ["../outside.py"]}, {**PLAN, "files": ["workflow/runtime/run.py"]}):
            self.analyzer.analyze.return_value = value
            self.github.current["body"] += " changed"
            self.assertEqual(self.edited()["status"], "analysis_failed")
        self.engine.assert_not_called()

    def test_approval_must_be_a_real_unedited_human_comment_on_this_issue(self):
        self.opened()
        for change in ("body", "sender", "created", "issue", "bot", "edited", "action"):
            with self.subTest(change=change):
                event = self.github.event(user_type="Bot" if change == "bot" else "User")
                if change == "body": self.github.records[-1]["body"] = "different"
                if change == "sender": event["sender"]["login"] = "attacker"
                if change == "created": event["comment"]["created_at"] = "forged"
                if change == "issue": self.github.records[-1]["issue_url"] += "2"
                if change == "edited": self.github.records[-1]["updated_at"] = "later"
                if change == "action": event["action"] = "edited"
                self.controller.handle("issue_comment", event)
        self.engine.assert_not_called()

    def test_old_comment_before_new_plan_cannot_approve_it(self):
        event = self.github.event()
        self.opened()
        self.assertEqual(self.controller.handle("issue_comment", event)["status"], "ignored")
        self.engine.assert_not_called()

    def test_deferred_ticket_revalidated_in_new_process_and_only_runs_once(self):
        self.opened()
        event = self.github.event()
        state = self.controller.handle("issue_comment", event, defer_execution=True)
        self.assertEqual(state["status"], "approved")
        self.engine.assert_not_called()
        controller = self.new_controller()
        self.assertEqual(controller.handle("issue_comment", event, execute_plan=state["plan_id"])["status"], "completed")
        self.assertEqual(controller.handle("issue_comment", event, execute_plan=state["plan_id"])["status"], "ignored")
        self.engine.assert_called_once()

    def test_deferred_approval_title_body_and_permission_changes_block_execution(self):
        for field in ("title", "body", "permission"):
            with self.subTest(field=field):
                self.setUp()
                self.opened()
                event = self.github.event()
                state = self.controller.handle("issue_comment", event, defer_execution=True)
                if field == "permission": self.github.permission.return_value = "read"
                else: self.github.current[field] += " changed"
                self.controller.handle("issue_comment", event, execute_plan=state["plan_id"])
                self.engine.assert_not_called()

    def test_changes_at_worker_validation_and_publication_boundaries_block(self):
        for target in ("codex", "validation", "publication"):
            with self.subTest(target=target):
                self.setUp()
                self.opened()
                def pipeline(*args, **kwargs):
                    report = {"config_sha256": self.controller.config_hash, "final_status": "completed"}
                    for stage in ("codex", "validation", "publication"):
                        if stage == target: self.github.current["body"] += " changed"
                        try: kwargs["stage_callback"](stage, report)
                        except ExecutionError as exc: return {**report, "final_status": exc.status}
                    return report
                self.engine.side_effect = pipeline
                state = self.controller.handle("issue_comment", self.github.event())
                self.assertEqual(state["status"], "awaiting_approval")
                self.assertIsNone(state["approval"])

    def test_config_change_invalidates_approval(self):
        self.opened()
        self.fixture.config["notes"] = ["Updated policy context"]
        self.fixture.write()
        controller = self.new_controller()
        self.assertEqual(controller.handle("issue_comment", self.github.event())["status"], "awaiting_approval")
        self.engine.assert_not_called()

    def test_journal_write_failure_never_starts_engine(self):
        self.opened()
        event = self.github.event()
        self.github.fail_write = True
        with self.assertRaises(ExecutionError):
            self.controller.handle("issue_comment", event)
        self.engine.assert_not_called()

    def test_analysis_changes_are_reanalyzed_once_and_not_approved(self):
        def analyze(*args):
            self.github.current["body"] += " edited"
            return copy.deepcopy(PLAN)
        self.analyzer.analyze.side_effect = analyze
        self.assertEqual(self.opened()["status"], "approval_invalidated")
        self.assertEqual(self.analyzer.analyze.call_count, 2)
        self.engine.assert_not_called()

    def test_execution_validation_and_publication_failures_are_distinct(self):
        for final, expected in (("codex_failed", "execution_failed"), ("validation_failed", "validation_failed"),
                                ("publication_failed", "publishing_failed")):
            with self.subTest(final=final):
                self.setUp()
                self.opened()
                self.engine.side_effect = None
                self.engine.return_value = {"final_status": final}
                self.assertEqual(self.controller.handle("issue_comment", self.github.event())["status"], expected)

    def test_wrong_repository_and_pr_comments_are_ignored(self):
        for change in ("repo", "pr"):
            event = self.github.event()
            if change == "repo": event["repository"]["full_name"] = "other/repo"
            else: event["issue"]["pull_request"] = {}
            self.assertEqual(self.controller.handle("issue_comment", event)["status"], "ignored")
        self.engine.assert_not_called()

    def test_main_defers_and_recovers_approval_output_in_separate_actions_steps(self):
        self.opened()
        event = self.github.event()
        event_path = self.fixture.base / "event.json"
        output_path = self.fixture.base / "output.txt"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        env = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_PATH": str(event_path),
               "GITHUB_EVENT_NAME": "issue_comment", "GITHUB_REPOSITORY": "example/sample",
               "GITHUB_OUTPUT": str(output_path), "WORKFLOW_STATE_KEY": KEY.decode(), "WORKFLOW_BOT_LOGIN": BOT}
        args = ["--config", str(self.fixture.path), "--repo-root", str(self.fixture.root),
                "--results-dir", str(self.fixture.results)]
        with patch.dict(os.environ, env), patch.object(subject, "IssueGitHub", return_value=self.github), patch.object(
                subject, "PlanAnalyzer", return_value=self.analyzer), patch.object(
                subject.orchestrator, "execute_workflow", self.engine), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(subject.main(args + ["--defer-execution"]), 0)
            self.engine.assert_not_called()
            plan_id = output_path.read_text().strip().split("=", 1)[1]
            self.assertEqual(subject.main(args + ["--execute-plan", plan_id]), 0)
        self.engine.assert_called_once()

    def test_main_refuses_synthetic_context_outside_actions(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), contextlib.redirect_stdout(io.StringIO()), patch.object(subject, "IssueGitHub") as api:
            self.assertEqual(subject.main(["--config", str(self.fixture.path), "--results-dir", str(self.fixture.results)]), 1)
        api.assert_not_called()

    def test_main_reports_repository_mismatch_before_analysis(self):
        self.fixture.config["repository"] = {"provider": "github", "owner": "example-owner",
                                              "name": "example-repository"}
        self.fixture.write()
        event_path = self.fixture.base / "event.json"
        output_path = self.fixture.base / "output.txt"
        event_path.write_text(json.dumps({"action": "opened", "repository": {"full_name": "example/sample"},
                                         "issue": self.github.issue(1)}), encoding="utf-8")
        env = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_PATH": str(event_path),
               "GITHUB_EVENT_NAME": "issues", "GITHUB_REPOSITORY": "example/sample",
               "GITHUB_OUTPUT": str(output_path), "WORKFLOW_STATE_KEY": KEY.decode(), "WORKFLOW_BOT_LOGIN": BOT}
        stdout = io.StringIO()
        with patch.dict(os.environ, env), patch.object(subject, "IssueGitHub", return_value=self.github), \
                patch.object(subject, "PlanAnalyzer", return_value=self.analyzer), contextlib.redirect_stdout(stdout):
            self.assertEqual(subject.main(["--config", str(self.fixture.path), "--repo-root", str(self.fixture.root),
                                           "--results-dir", str(self.fixture.results), "--defer-execution"]), 1)
        diagnostic = json.loads(stdout.getvalue())
        self.assertEqual(diagnostic, {"status": "blocked", "stage": "load workflow configuration",
                                      "reason": "repository_mismatch"})
        self.assertEqual(json.loads(output_path.read_text().strip().split("=", 1)[1]), diagnostic)
        self.analyzer.analyze.assert_not_called()
        self.engine.assert_not_called()
        self.assertEqual(self.github.records, [])

    def test_missing_or_reassigned_plan_comment_cannot_execute(self):
        self.opened()
        other = self.github.create_comment(1, "Another plan")
        self.controller.state["plan_comment_id"] = other["id"]
        self.controller.persist("awaiting_approval")
        self.controller.handle("issue_comment", self.github.event())
        self.engine.assert_not_called()

    def test_worker_report_config_mismatch_blocks_before_worker_boundary(self):
        self.opened()
        def wrong_config(*args, **kwargs):
            try:
                kwargs["stage_callback"]("codex", {"config_sha256": "changed"})
            except ExecutionError as exc:
                return {"final_status": exc.status}
        self.engine.side_effect = wrong_config
        state = self.controller.handle("issue_comment", self.github.event())
        self.assertEqual(state["status"], "awaiting_approval")
        self.assertIsNone(state["approval"])


class BoundaryTests(unittest.TestCase):
    def test_prj_analysis_prepares_account_sources_without_a_model_call(self):
        root = Path(__file__).resolve().parents[3]
        config_path = root / "workflow/config/projects/prj.json"
        config, _ = subject.run._load(config_path, root)
        adapter = Mock()
        adapter.analyze.return_value = {}
        subject.PlanAnalyzer(adapter).analyze({"title": "Remove the header settings button", "body": "Keep the menu entry"},
                                             config, config_path, root)
        adapter.analyze.assert_called_once()
        prompt = adapter.analyze.call_args.args[0]
        for relative in ("PRJ/frontend/src/accounts/server.ts", "PRJ/backend/app/manage.py",
                         "PRJ/frontend/tests/supabase-accounts.spec.ts", "PRJ/backend/tests/test_accounts.py",
                         "PRJ/frontend/tests/server-fixture.ts", "PRJ/frontend/tests/app-drafts.spec.ts",
                         "PRJ/frontend/tests/app-journey-regressions.spec.ts"):
            self.assertIn(relative, prompt)
        adapter.execute.assert_not_called()

    def test_environment_diagnostic_identifies_missing_options_without_arbitrary_text(self):
        error = ExecutionError("environment_error", "synthetic-private-value",
                               operation="check_codex_options", option="--strict-config")
        self.assertEqual(subject.error_diagnostic(error), {"reason": "environment_error",
                         "operation": "check_codex_options", "option": "--strict-config"})
        error.option = "synthetic-private-value"
        self.assertNotIn("synthetic-private-value", json.dumps(subject.error_diagnostic(error)))

    def test_active_project_configs_accept_the_actions_repository(self):
        root = Path(__file__).resolve().parents[3]
        github = Mock(repository="JunSuHeo/kosa_final-public")
        with tempfile.TemporaryDirectory() as directory:
            for name in ("prj.json", "sandbox.json"):
                with self.subTest(config=name):
                    controller = subject.IssueController(root / "workflow/config/projects" / name, root,
                        Path(directory) / "results", github, KEY, BOT, analyzer=Mock(), engine=Mock())
                    self.assertEqual(controller.repository, github.repository)
        self.assertEqual(github.mock_calls, [])

    def test_analysis_reports_sensitive_source_before_the_model_reads_it(self):
        fixture = test_run.EngineTests(methodName="test_task_parsing")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.write()
        (fixture.root / "sample/src/secret.ts").write_text('const password = "synthetic-private-value";\n')
        adapter = Mock()
        analyzer = subject.PlanAnalyzer(adapter)
        with self.assertRaises(ExecutionError) as failure:
            analyzer.analyze(MemoryGitHub().current, fixture.config, fixture.path, fixture.root)
        self.assertEqual(subject.error_diagnostic(failure.exception), {"reason": "sensitive_content"})
        self.assertNotIn("synthetic-private-value", str(failure.exception))
        adapter.analyze.assert_not_called()

    def test_analysis_reads_real_structure_and_disallows_file_changes(self):
        fixture = test_run.EngineTests(methodName="test_task_parsing")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.write()
        adapter = Mock()
        adapter.analyze.return_value = copy.deepcopy(PLAN)
        analyzer = subject.PlanAnalyzer(adapter)
        analyzer.analyze(MemoryGitHub().current, fixture.config, fixture.path, fixture.root)
        prompt = adapter.analyze.call_args.args[0]
        self.assertIn("sample/src/main.py", prompt)
        self.assertIn("value = 1", prompt)
        self.assertIn("Do not modify", prompt)
        adapter.execute.assert_not_called()
        def modify(prompt, destination, settings, schema):
            (destination / "sample/src/main.py").write_text("changed")
            return copy.deepcopy(PLAN)
        adapter.analyze.side_effect = modify
        with self.assertRaises(ExecutionError):
            analyzer.analyze(MemoryGitHub().current, fixture.config, fixture.path, fixture.root)
        self.assertEqual((fixture.root / "sample/src/main.py").read_text(), "value = 1\n")

    def test_secrets_not_in_worker_environment_and_publication_credential_is_separate(self):
        with patch.dict(os.environ, {"GH_TOKEN": "issue-token", "GITHUB_TOKEN": "issue-token",
                                    "WORKFLOW_STATE_KEY": "signing-key", "WORKFLOW_PUBLISH_TOKEN": "publish-token"}):
            worker_env = restricted_environment()
            issue_env = IssueGitHub("example/sample", Path.cwd()).transport_environment()
            publishing_env = environment()
        for key in ("GH_TOKEN", "GITHUB_TOKEN", "WORKFLOW_STATE_KEY", "WORKFLOW_PUBLISH_TOKEN"):
            self.assertNotIn(key, worker_env)
        self.assertEqual(issue_env["GH_TOKEN"], "issue-token")
        self.assertEqual(publishing_env["GH_TOKEN"], "publish-token")

    def test_issue_api_paginated_reads_and_structured_json_writes(self):
        github = IssueGitHub("example/sample", Path.cwd())
        with patch.object(github, "call", return_value=json.dumps([[{"id": 1}], [{"id": 2}]])) as api:
            self.assertEqual(github.comments(1), [{"id": 1}, {"id": 2}])
            self.assertIn("--paginate", api.call_args.args[0])
        def call(args, cwd):
            path = Path(args[args.index("--input") + 1])
            self.assertEqual(json.loads(path.read_text())["body"], "line1\nline2; $(literal)")
            return '{"id": 3}'
        with patch.object(github, "call", side_effect=call):
            self.assertEqual(github.create_comment(1, "line1\nline2; $(literal)")["id"], 3)

    def test_read_only_analysis_cli_contract_without_real_codex(self):
        adapter = CodexCLI()
        adapter.executable = "/fake/codex"
        process = Mock(returncode=0)
        def spawn(command, **kwargs):
            self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
            self.assertEqual(command[-1], "-")
            self.assertNotIn("workspace-write", command)
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(json.dumps(PLAN), encoding="utf-8")
            return process
        process.communicate.return_value = (None, "")
        with patch.object(adapter, "_inspect", return_value="--output-schema --output-last-message"), patch(
                "workflow.runtime.codex_adapter.subprocess.Popen", side_effect=spawn):
            self.assertEqual(adapter.analyze("analyze", Path.cwd(),
                                            {"model": "fake", "timeout_seconds": 10}, subject.PLAN_SCHEMA), PLAN)


@unittest.skipUnless(shutil.which("git") and os.name == "posix", "Local Git fixtures require Linux")
class IntegratedIssueTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_publish.PublishTests(methodName="test_valid_prepare_creates_only_isolated_commit_and_preview")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.github = MemoryGitHub()
        self.analyzer = Mock()
        self.analyzer.analyze.return_value = copy.deepcopy(PLAN)
        self.controller = subject.IssueController(self.fixture.config_path, self.fixture.root, self.fixture.results,
                                                  self.github, KEY, BOT, analyzer=self.analyzer)

    def test_issue_approval_reuses_real_orchestrator_and_simulated_publisher(self):
        remote = SimulatedGitHubCLI()
        worker = test_run.FakeCodex(lambda root: (root / "sample/src/main.py").write_text("value = 2\n"))
        tests = test_publish.Tests()
        event = {"action": "opened", "repository": {"full_name": "example/sample"}, "issue": self.github.issue(1)}
        before = self.fixture.git.run("status", "--porcelain")
        with patch.object(GitHubCLI, "preflight", side_effect=AssertionError("No real gh")), patch(
                "workflow.runtime.publish.authenticated_git", side_effect=AssertionError("No credentials")):
            self.controller.handle("issues", event)
            self.assertFalse(worker.called)
            state = self.controller.handle("issue_comment", self.github.event(), adapter=worker,
                                           test_executor=tests, simulation_github=remote)
        self.assertEqual(state["status"], "completed", state)
        self.assertTrue(worker.called)
        self.assertIn('"approved_issue"', worker.prompt)
        self.assertIn("untrusted task data", worker.prompt)
        result = json.loads(Path(state["execution"]["workflow_result_path"]).read_text())
        self.assertEqual(result["validation_status"], "passed")
        self.assertEqual(result["approved_issue"]["plan_id"], state["plan_id"])
        self.assertEqual([call["operation"] for call in remote.calls].count("pr_create"), 1)
        self.assertFalse(result["publication"]["attempted"])
        self.assertEqual(self.fixture.git.run("status", "--porcelain"), before)
        self.assertEqual((self.fixture.root / "sample/src/main.py").read_text(), "value = 1\n")

    def test_issue_branch_template_reaches_publisher_with_approved_title_and_login(self):
        self.fixture.config["publishing"].update(branch_template="ai_feature/{date}/{approver}/{issue_title}",
                                                 manual_branch_template="ai/{project_id}/{run_id}")
        self.fixture.write_config()
        self.controller = subject.IssueController(self.fixture.config_path, self.fixture.root, self.fixture.results,
                                                  self.github, KEY, BOT, analyzer=self.analyzer)
        self.github.current["title"] = "로그인 화면 개선"
        self.controller.handle("issues", {"action": "opened", "repository": {"full_name": "example/sample"},
                                          "issue": self.github.issue(1)})
        remote = SimulatedGitHubCLI()
        with patch.object(GitHubCLI, "preflight", side_effect=AssertionError("No real gh")):
            state = self.controller.handle("issue_comment", self.github.event(login="JunSuHeo"), adapter=test_publish.Worker(),
                                           test_executor=test_publish.Tests(), simulation_github=remote)
        self.assertEqual(state["status"], "completed", state)
        result = json.loads(Path(state["execution"]["workflow_result_path"]).read_text())
        self.assertRegex(result["publication"]["branch"], r"^ai_feature/\d{2}\.\d{2}\.\d{2}/JunSuHeo/로그인-화면-개선$")
        self.assertFalse(result["publication"]["attempted"])
        self.assertEqual([call["operation"] for call in remote.calls].count("pr_create"), 1)

    def test_failed_tests_are_commented_before_draft_creation_and_do_not_rerun(self):
        self.fixture.config["pr_policy"]["allow_draft_on_failure"] = True
        self.fixture.config["publishing"]["draft"] = False
        self.fixture.write_config()
        self.controller = subject.IssueController(self.fixture.config_path, self.fixture.root, self.fixture.results,
                                                  self.github, KEY, BOT, analyzer=self.analyzer)
        self.controller.handle("issues", {"action": "opened", "repository": {"full_name": "example/sample"},
                                          "issue": self.github.issue(1)})
        event = self.github.event()
        remote = SimulatedGitHubCLI()
        original = remote.create_pr
        def create_after_comment(*args):
            comments = [comment["body"] for comment in self.github.records if "### 테스트 실패" in comment["body"]]
            self.assertEqual(len(comments), 1)
            self.assertIn("unit", comments[0])
            self.assertIn("unavailable", comments[0])
            self.assertIn("Controlled test error", comments[0])
            return original(*args)
        with patch.object(remote, "create_pr", side_effect=create_after_comment), patch.object(
                GitHubCLI, "preflight", side_effect=AssertionError("No real gh")), patch(
                "workflow.runtime.publish.authenticated_git", side_effect=AssertionError("No credentials")):
            state = self.controller.handle("issue_comment", event, adapter=test_publish.Worker(),
                                           test_executor=test_publish.Tests("unavailable"), simulation_github=remote)
        self.assertEqual(state["status"], "completed", state)
        self.assertEqual(state["execution"]["validation_status"], "failed")
        self.assertTrue(next(call["draft"] for call in remote.calls if call["operation"] == "pr_create"))
        self.assertIn("테스트 검증은 실패", self.github.records[-1]["body"])
        self.assertEqual(self.controller.handle("issue_comment", event)["status"], "ignored")
        self.assertEqual([call["operation"] for call in remote.calls].count("pr_create"), 1)

    def test_rejection_never_reaches_real_generation_validation_or_publisher(self):
        self.controller.handle("issues", {"action": "opened", "repository": {"full_name": "example/sample"},
                                          "issue": self.github.issue(1)})
        with patch("workflow.runtime.run.execute_request") as coding, patch("workflow.runtime.publish.publish") as publishing:
            self.assertEqual(self.controller.handle("issue_comment", self.github.event("/reject"))["status"], "rejected")
        coding.assert_not_called()
        publishing.assert_not_called()

    def test_issue_edit_during_remote_checks_blocks_push_and_pr_creation(self):
        self.controller.handle("issues", {"action": "opened", "repository": {"full_name": "example/sample"},
                                          "issue": self.github.issue(1)})
        remote = SimulatedGitHubCLI()
        original = remote.check_repository
        def change_issue(*args):
            original(*args)
            self.github.current["title"] += " changed"
        remote.check_repository = change_issue
        with patch.object(GitHubCLI, "preflight", side_effect=AssertionError("No real gh")):
            state = self.controller.handle("issue_comment", self.github.event(), adapter=test_publish.Worker(),
                                           test_executor=test_publish.Tests(), simulation_github=remote)
        self.assertEqual(state["status"], "awaiting_approval", state)
        self.assertNotIn("pr_create", [call["operation"] for call in remote.calls])
        # The invalidated run receipt still records that no simulated push occurred.
        reports = list(self.fixture.results.glob("*/workflow.json"))
        result = json.loads(reports[-1].read_text())
        self.assertEqual(result["final_status"], "approval_invalidated")
        self.assertFalse(result["publication"]["simulated_attempted"])
        self.assertFalse(any(call[0] == "push" for call in result["publication"]["simulation"]["git_transport_requests"]))

    def test_issue_edit_after_simulated_push_blocks_pr_and_preserves_attempt(self):
        self.controller.handle("issues", {"action": "opened", "repository": {"full_name": "example/sample"},
                                          "issue": self.github.issue(1)})
        remote = SimulatedGitHubCLI()
        transport = SimulatedNetworkGit("main", self.fixture.head)
        original = transport.run
        def change_after_push(*args):
            result = original(*args)
            if args[0] == "push": self.github.current["body"] += " changed"
            return result
        transport.run = change_after_push
        state = self.controller.handle("issue_comment", self.github.event(), adapter=test_publish.Worker(),
                                       test_executor=test_publish.Tests(), simulation_github=remote, simulation_git=transport)
        self.assertEqual(state["status"], "awaiting_approval")
        self.assertTrue(any(call[0] == "push" for call in transport.calls))
        self.assertNotIn("pr_create", [call["operation"] for call in remote.calls])
        result = json.loads(list(self.fixture.results.glob("*/workflow.json"))[-1].read_text())
        self.assertEqual(result["final_status"], "approval_invalidated")
        self.assertTrue(result["publication"]["simulated_attempted"])
        self.assertFalse(result["publication"]["attempted"])

    def test_issue_edit_during_generation_preparation_never_calls_worker(self):
        self.controller.handle("issues", {"action": "opened", "repository": {"full_name": "example/sample"},
                                          "issue": self.github.issue(1)})
        original = workspace.prepare
        worker = test_run.FakeCodex()
        def change_during_prepare(*args):
            result = original(*args)
            self.github.current["body"] += " changed"
            return result
        # After the guard invalidates, reanalysis uses a Mock and cannot create code.
        with patch.object(workspace, "prepare", side_effect=change_during_prepare):
            state = self.controller.handle("issue_comment", self.github.event(), adapter=worker,
                                           test_executor=test_publish.Tests())
        self.assertFalse(worker.called)
        self.assertEqual(state["status"], "awaiting_approval")


if __name__ == "__main__":
    unittest.main()

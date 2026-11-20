"""Offline engine tests. Fake workers never call Codex, GitHub, or product tools."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from workflow.runtime import run, workspace
from workflow.runtime.codex_adapter import ExecutionError


class FakeCodex:
    def __init__(self, action=None, failure=None):
        self.action = action
        self.failure = failure
        self.called = False
        self.prompt = None

    def preflight(self, settings):
        return {"adapter": "offline_fake", "version": settings["version"], "platform": "linux"}

    def execute(self, prompt, destination, settings):
        self.called = True
        self.prompt = prompt
        if self.action:
            self.action(destination)
        if self.failure:
            raise self.failure
        return 0


class FakeTests:
    def __init__(self, status="passed"):
        self.status = status
        self.calls = []

    def run(self, root, cwd, command, timeout):
        self.calls.append((root, cwd, command, timeout))
        return {"status": self.status, "return_code": 0 if self.status == "passed" else 1,
                "duration_seconds": 0.01, "stdout": "", "stderr": "", "reason": None}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "repo"
        self.root.mkdir()
        (self.root / ".git").mkdir()
        for path in ("sample/src", "sample/docs", "sample/tests", "other"):
            (self.root / path).mkdir(parents=True)
        (self.root / "sample/src/main.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / "sample/docs/design.md").write_text("# Confirmed contract\n", encoding="utf-8")
        (self.root / "sample/AGENTS.md").write_text("Use small, focused changes.\n", encoding="utf-8")
        self.path = self.root / "project.json"
        self.config = {
            "schema_version": 1, "configuration_status": "ready", "project_id": "sample",
            "repository": {"provider": "github", "owner": "example", "name": "sample"},
            "base_branch": "main", "project_root": "sample",
            "allowed_paths": ["sample/src", "sample/docs", "sample/tests"],
            "design_documents": ["sample/docs/design.md"],
            "tests": {kind: [{"id": kind, "required": True, "cwd": "sample/tests",
                             "command": {"program": "test-tool", "args": [kind]}}] for kind in ("unit", "e2e")},
            "pr_policy": {"target_branch": "main", "allow_draft_on_failure": False,
                          "require_human_approval": True, "allow_auto_merge": False},
            "execution": {"instructions": ["sample/AGENTS.md"],
                          "environment": {"platform": "linux", "required_programs": []},
                          "codex": {"version": "1.2.3", "model": "test-model", "timeout_seconds": 30}},
        }
        self.results = self.base / "results"
        self.fake = FakeCodex()
        self.test_executor = FakeTests()

    def write(self):
        self.path.write_text(json.dumps(self.config), encoding="utf-8")
        return self.path

    def execute(self, **kwargs):
        self.write()
        return run.execute_request(self.path, kwargs.get("task", "Add input validation"), self.root,
                                   kwargs.get("results", self.results), adapter=kwargs.get("adapter", self.fake), test_executor=self.test_executor)

    def test_task_parsing(self):
        parsed = run.parser().parse_args(["--config", "project.json", "--task", "  로그인 검증 추가  "])
        self.assertEqual(parsed.task, "로그인 검증 추가")
        self.assertEqual(parsed.config, Path("project.json"))

    def test_missing_arguments_and_empty_task(self):
        for arguments in ([], ["--config", "a"], ["--task", "text"], ["--config", "a", "--task", "  "]):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    run.parser().parse_args(arguments)
                self.assertEqual(error.exception.code, 2)

    def test_successful_request_saves_result_and_preserves_source(self):
        self.fake.action = lambda destination: (destination / "sample/src/main.py").write_text("value = 2\n", encoding="utf-8")
        result = self.execute()
        self.assertEqual(result["final_status"], "completed")
        self.assertEqual(result["codex_status"], "succeeded")
        self.assertEqual(result["validation_status"], "passed")
        self.assertEqual(len(self.test_executor.calls), 2)
        self.assertEqual(result["changed_files"], ["sample/src/main.py"])
        self.assertEqual(result["changes"][0]["change"], "modified")
        self.assertEqual(json.loads(Path(result["result_path"]).read_text()), result)
        self.assertEqual((self.root / "sample/src/main.py").read_text(), "value = 1\n")
        self.assertFalse(Path(result["workspace_path"]).is_relative_to(self.root))
        self.assertIsNotNone(result["started_at"])
        self.assertGreaterEqual(result["ended_at"], result["started_at"])

    def test_unique_execution_ids(self):
        first, second = self.execute(), self.execute()
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(uuid.UUID(first["run_id"]).version, 4)

    def test_prompt_contains_configuration_design_instructions_and_structure(self):
        self.execute(task="Requested change")
        for text in ("Requested change", "sample/src/main.py", "Confirmed contract", "focused changes",
                     "automation_requirements", "automation_architecture", "allowed_paths", "spec-first"):
            self.assertIn(text, self.fake.prompt)

    def test_invalid_configuration_blocks_codex_and_is_saved(self):
        del self.config["base_branch"]
        result = self.execute()
        self.assertEqual(result["final_status"], "config_error")
        self.assertFalse(self.fake.called)
        self.assertTrue(Path(result["result_path"]).is_file())

    def test_invalid_json(self):
        self.path.write_text('{"schema_version": }', encoding="utf-8")
        result = run.execute_request(self.path, "Task", self.root, self.results, adapter=self.fake)
        self.assertEqual(result["final_status"], "config_error")
        self.assertFalse(self.fake.called)

    def test_missing_config_file(self):
        result = run.execute_request(self.path, "Task", self.root, self.results, adapter=self.fake)
        self.assertEqual(result["final_status"], "config_error")

    def test_old_offline_config_requires_execution_section(self):
        del self.config["execution"]
        result = self.execute()
        self.assertEqual(result["final_status"], "config_error")
        self.assertFalse(self.fake.called)

    def test_invalid_timeout_is_not_defaulted(self):
        for seconds in (0, -1, 3601):
            with self.subTest(seconds=seconds):
                self.config["execution"]["codex"]["timeout_seconds"] = seconds
                self.assertEqual(self.execute()["final_status"], "config_error")

    def test_codex_missing(self):
        self.write()
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value=None):
            result = run.execute_request(self.path, "Task", self.root, self.results)
        self.assertEqual(result["final_status"], "codex_missing")
        self.assertEqual(result["codex_status"], "not_started")

    def test_missing_project_tool(self):
        self.config["execution"]["environment"]["required_programs"] = ["missing-tool"]
        with patch("workflow.runtime.run.shutil.which", return_value=None):
            result = self.execute()
        self.assertEqual(result["final_status"], "environment_error")
        self.assertFalse(self.fake.called)

    def test_not_a_git_root(self):
        (self.root / ".git").rmdir()
        self.assertEqual(self.execute()["final_status"], "environment_error")

    def test_missing_repository_root_is_an_environment_error(self):
        self.write()
        result = run.execute_request(self.path, "Task", self.root / "missing", self.results, adapter=self.fake)
        self.assertEqual(result["final_status"], "environment_error")
        self.assertFalse(self.fake.called)

    def test_execution_failure_and_timeout_are_distinct(self):
        for status in ("codex_failed", "timeout"):
            with self.subTest(status=status):
                result = self.execute(adapter=FakeCodex(failure=ExecutionError(status, "Controlled failure")))
                self.assertEqual(result["final_status"], status)
                self.assertEqual(result["codex_status"], status)
                self.assertIsNone(result["workspace_path"])

    def test_unexpected_exception_does_not_leak_details(self):
        result = self.execute(adapter=FakeCodex(failure=RuntimeError("synthetic-private-value")))
        self.assertEqual(result["final_status"], "unexpected_error")
        self.assertEqual(result["codex_status"], "unexpected_error")
        self.assertNotIn("synthetic-private-value", json.dumps(result))

    def test_collection_failure(self):
        with patch("workflow.runtime.run.workspace.collect", side_effect=OSError("private details")):
            result = self.execute()
        self.assertEqual(result["final_status"], "result_collection_failed")
        self.assertNotIn("private details", json.dumps(result))

    def test_save_failure_is_not_reported_as_success(self):
        with patch("workflow.runtime.run._save", side_effect=OSError("write failure")):
            result = self.execute()
        self.assertEqual(result["final_status"], "result_collection_failed")
        self.assertIsNone(result["result_path"])

    def test_results_inside_repository_are_rejected(self):
        result = self.execute(results=self.root / "results")
        self.assertEqual(result["final_status"], "path_violation")
        self.assertFalse(self.fake.called)
        self.assertFalse((self.root / "results").exists())

    def test_instruction_outside_project_is_blocked(self):
        (self.root / "other/guide.md").write_text("Other project", encoding="utf-8")
        self.config["execution"]["instructions"] = ["other/guide.md"]
        self.assertEqual(self.execute()["final_status"], "path_violation")
        self.assertFalse(self.fake.called)

    def test_credential_file_cannot_be_context(self):
        (self.root / "sample/.env").write_text("not-a-document", encoding="utf-8")
        self.config["execution"]["instructions"] = ["sample/.env"]
        self.assertEqual(self.execute()["final_status"], "path_violation")
        self.assertFalse(self.fake.called)

    def test_another_project_uses_same_engine(self):
        (self.root / "other/design.md").write_text("# Other approved project", encoding="utf-8")
        self.config["project_id"] = "other"
        self.config["project_root"] = "other"
        self.config["allowed_paths"] = ["other"]
        self.config["design_documents"] = ["other/design.md"]
        self.config["execution"]["instructions"] = []
        for category in ("unit", "e2e"):
            self.config["tests"][category][0]["cwd"] = "other"
        result = self.execute()
        self.assertEqual(result["final_status"], "completed")
        self.assertEqual(result["project_id"], "other")
        self.assertNotIn("sample/src/main.py", self.fake.prompt)

    def test_new_file_and_deleted_file_are_collected(self):
        def action(destination):
            (destination / "sample/src/main.py").unlink()
            (destination / "sample/src/new.py").write_text("value = 3\n", encoding="utf-8")
        result = self.execute(adapter=FakeCodex(action))
        self.assertEqual([item["change"] for item in result["changes"]], ["deleted", "added"])

    def test_unauthorized_new_file_is_blocked_and_workspace_removed(self):
        def action(destination):
            (destination / "other").mkdir()
            (destination / "other/new.py").write_text("unsafe", encoding="utf-8")
        result = self.execute(adapter=FakeCodex(action))
        self.assertEqual(result["final_status"], "path_violation")
        self.assertFalse((Path(result["result_path"]).parent / "workspace").exists())
        self.assertFalse((self.root / "other/new.py").exists())

    def test_unauthorized_empty_directory_is_blocked(self):
        self.fake.action = lambda destination: (destination / "other").mkdir()
        self.assertEqual(self.execute()["final_status"], "path_violation")

    def test_protected_file_is_blocked(self):
        self.fake.action = lambda destination: (destination / "sample/src/AGENTS.md").write_text("Widen access", encoding="utf-8")
        self.assertEqual(self.execute()["final_status"], "path_violation")

    def test_secret_source_files_are_not_copied(self):
        (self.root / "sample/src/.env").write_text("password=synthetic-value", encoding="utf-8")
        result = self.execute()
        self.assertEqual(result["final_status"], "completed")
        self.assertFalse((Path(result["workspace_path"]) / "sample/src/.env").exists())

    def test_generated_sensitive_content_is_discarded(self):
        self.fake.action = lambda destination: (destination / "sample/src/main.py").write_text("password=synthetic-private-value", encoding="utf-8")
        result = self.execute()
        self.assertEqual(result["final_status"], "sensitive_content")
        self.assertIsNone(result["workspace_path"])
        self.assertNotIn("synthetic-private-value", json.dumps(result))

    def test_normal_source_declarations_and_references_allow_changes(self):
        source = self.root / "sample/src/auth.ts"
        source.write_text('type Login = { login(password: string): void };\nlet accessToken = sessionStorage.getItem("local");\n')
        self.fake.action = lambda destination: (destination / "sample/src/auth.ts").write_text(
            'type Login = { password: string };\naccessToken = token;\n')
        result = self.execute()
        self.assertEqual(result["final_status"], "completed", result["errors"])
        self.assertIn("sample/src/auth.ts", result["changed_files"])

    def test_known_fixture_does_not_allow_a_different_literal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "PRJ/backend/tests/test_auth_and_recovery.py"
            source.parent.mkdir(parents=True)
            source.write_text('settings = Settings(llm_api_key="secret-do-not-print")\n')
            self.assertIn(source.relative_to(root).as_posix(), workspace.inventory(root))
            source.write_text('settings = Settings(llm_api_key="secret-do-not-print synthetic-extra")\n')
            with self.assertRaises(ExecutionError) as failure:
                workspace.inventory(root)
            self.assertEqual(failure.exception.status, "sensitive_content")

    def test_task_redaction(self):
        with patch.dict(os.environ, {"WORKFLOW_TEST_TOKEN": "synthetic-private-value"}):
            result = self.execute(task="Use synthetic-private-value and password=made-up-value")
        text = Path(result["result_path"]).read_text()
        self.assertNotIn("synthetic-private-value", text)
        self.assertNotIn("made-up-value", text)
        self.assertIn("[REDACTED]", result["task"])
        self.assertNotIn("synthetic-private-value", self.fake.prompt)

    def test_generated_symlink_is_rejected(self):
        if os.name == "nt":
            self.skipTest("symlink enforcement is checked on the Linux execution platform")
        self.fake.action = lambda destination: (destination / "sample/src/link").symlink_to(self.root / "other", target_is_directory=True)
        self.assertEqual(self.execute()["final_status"], "path_violation")

    def test_failed_tests_preserve_candidate_but_never_mark_completed(self):
        self.test_executor = FakeTests("failed")
        report = self.execute()
        self.assertEqual(report["codex_status"], "succeeded")
        self.assertEqual(report["final_status"], "validation_failed")
        self.assertEqual(report["validation_status"], "failed")
        self.assertTrue(Path(report["workspace_path"]).is_dir())
        self.assertEqual(json.loads(Path(report["result_path"]).read_text()), report)

    def test_existing_user_changes_form_baseline_not_codex_changes(self):
        (self.root / "sample/src/main.py").write_text("user_change = 7\n", encoding="utf-8")
        result = self.execute()
        self.assertEqual(result["changes"], [])
        self.assertEqual((self.root / "sample/src/main.py").read_text(), "user_change = 7\n")

    def test_config_changed_by_worker_does_not_replace_frozen_test_policy(self):
        def action(destination):
            self.config["tests"]["unit"][0]["required"] = False
            self.config["tests"]["unit"][0]["run_if"] = "never"
            self.config["tests"]["unit"][0]["skip_reason"] = "skip"
            self.write()
        result = self.execute(adapter=FakeCodex(action))
        self.assertTrue(result["validation"]["tests"]["unit"][0]["required"])
        self.assertEqual(len(self.test_executor.calls), 2)

    def test_cli_main_reports_failure_exit_code(self):
        self.write()
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value=None), contextlib.redirect_stdout(io.StringIO()) as output:
            code = run.main(["--config", str(self.path), "--task", "Task", "--repo-root", str(self.root), "--results-dir", str(self.results)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["final_status"], "codex_missing")


if __name__ == "__main__":
    unittest.main()

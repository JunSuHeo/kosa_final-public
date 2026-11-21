"""Offline validation policy tests; no Codex, GitHub or product dependencies."""

import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from workflow.runtime import test_runner, workspace, validate_config


class FakeProcess:
    def __init__(self, statuses=None, action=None, stdout="", stderr=""):
        self.statuses = list(statuses or ["passed", "passed"])
        self.action = action
        self.stdout, self.stderr = stdout, stderr
        self.calls = []

    def run(self, root, cwd, command, timeout):
        self.calls.append((root, cwd, command, timeout))
        if self.action:
            self.action(root)
        status = self.statuses.pop(0)
        return {"status": status, "return_code": 0 if status == "passed" else None if status == "unavailable" else 1,
                "duration_seconds": 0.1, "stdout": self.stdout, "stderr": self.stderr, "reason": None}


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.candidate = Path(self.temp.name) / "candidate"
        for path in ("sample/src", "sample/specs", "sample/tests"):
            (self.candidate / path).mkdir(parents=True, exist_ok=True)
        (self.candidate / "sample/src/main.py").write_text("value = 1\n")
        (self.candidate / "sample/specs/design.md").write_text("# Contract\n")
        self.config = {
            "schema_version": 1, "configuration_status": "ready", "project_id": "sample",
            "repository": {"provider": "github", "owner": "example", "name": "sample"},
            "project_root": "sample", "base_branch": "main",
            "allowed_paths": ["sample/src", "sample/specs", "sample/tests"],
            "design_documents": ["sample/specs/design.md"],
            "tests": {kind: [{"id": kind, "required": True, "cwd": "sample/tests",
                             "command": {"program": "test-tool", "args": [kind]}, "timeout_seconds": 2}]
                      for kind in ("unit", "e2e")},
            "pr_policy": {"target_branch": "main", "allow_draft_on_failure": False,
                          "require_human_approval": True, "allow_auto_merge": False},
            "execution": {"instructions": [], "environment": {"platform": "linux", "required_programs": []},
                          "codex": {"version": "1.2.3", "model": "test", "timeout_seconds": 10}},
        }
        self.before = workspace.inventory(self.candidate)
        self.executor = FakeProcess()

    def validate(self):
        return test_runner.validate_workspace(self.candidate, self.config, self.before, "project.json", executor=self.executor)

    def test_required_unit_and_e2e_pass_in_order(self):
        result = self.validate()
        self.assertEqual(result["status"], "passed")
        self.assertEqual([c[2]["args"] for c in self.executor.calls], [["unit"], ["e2e"]])
        self.assertEqual(result["tests"]["unit"][0]["status"], "passed")
        self.assertEqual(result["tests"]["e2e"][0]["status"], "passed")
        self.assertIsNotNone(result["candidate_sha256"])
        self.assertGreaterEqual(result["ended_at"], result["started_at"])
        self.assertEqual(workspace.inventory(self.candidate), self.before)

    def test_unit_failure_still_collects_e2e(self):
        self.executor.statuses = ["failed", "passed"]
        result = self.validate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["tests"]["e2e"][0]["status"], "passed")

    def test_e2e_failure_blocks(self):
        self.executor.statuses = ["passed", "failed"]
        self.assertEqual(self.validate()["status"], "failed")

    def test_required_unavailable_and_timeout_fail_validation(self):
        for status in ("unavailable", "timeout"):
            with self.subTest(status=status):
                self.executor = FakeProcess(["passed", status])
                result = self.validate()
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["tests"]["e2e"][0]["status"], status)

    def test_optional_not_applicable_is_not_a_passed_test(self):
        self.config["tests"]["e2e"][0].update(required=False, run_if="never", skip_reason="No applicable browser scenario.")
        result = self.validate()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["tests"]["e2e"][0]["status"], "not_run")
        self.assertIn("No applicable", result["tests"]["e2e"][0]["reason"])
        self.assertEqual(len(self.executor.calls), 1)

    def test_all_skipped_is_never_validation_success(self):
        for tests in self.config["tests"].values():
            tests[0].update(required=False, run_if="never", skip_reason="Explicit policy.")
        self.assertEqual(self.validate()["status"], "not_run")
        self.assertEqual(self.executor.calls, [])

    def test_optional_failure_block_and_record_policies(self):
        for policy, expected in (("block", "failed"), ("record", "passed")):
            with self.subTest(policy=policy):
                self.config["tests"]["e2e"][0].update(required=False, on_failure=policy)
                self.executor = FakeProcess(["passed", "failed"])
                result = self.validate()
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["tests"]["e2e"][0]["status"], "failed")

    def test_changed_paths_condition_skips_and_matches_added_or_deleted_files(self):
        self.config["tests"]["e2e"][0].update(required=False, run_if="changed_paths", changed_paths=["sample/src"])
        self.assertEqual(self.validate()["tests"]["e2e"][0]["status"], "not_run")
        (self.candidate / "sample/src/main.py").unlink()
        (self.candidate / "sample/src/new.py").write_text("value=2\n")
        self.executor = FakeProcess()
        self.assertEqual(self.validate()["tests"]["e2e"][0]["status"], "passed")
        self.assertEqual([c["change"] for c in workspace.collect(self.candidate, self.config, self.before, "project.json")], ["deleted", "added"])

    def test_unauthorized_change_blocks_all_test_execution(self):
        (self.candidate / "outside").mkdir()
        (self.candidate / "outside/new.py").write_text("value=2\n")
        result = self.validate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["scope_status"], "failed")
        self.assertEqual(self.executor.calls, [])

    def test_existing_user_content_is_baseline(self):
        (self.candidate / "sample/src/main.py").write_text("user_change=5\n")
        self.before = workspace.inventory(self.candidate)
        self.assertEqual(workspace.collect(self.candidate, self.config, self.before, "project.json"), [])
        self.assertEqual(self.validate()["status"], "passed")

    def test_bad_command_is_rejected_before_execution(self):
        self.config["tests"]["unit"][0]["command"]["args"] = "shell string"
        result = self.validate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.executor.calls, [])

    def test_zero_tests_with_zero_exit_does_not_pass(self):
        self.executor.stdout = "Ran 0 tests in 0.000s\nOK"
        self.assertEqual(self.validate()["status"], "failed")

    def test_test_cannot_modify_inputs_and_get_success(self):
        self.executor.action = lambda root: (root / "sample/src/main.py").write_text("value=3\n")
        result = self.validate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["tests"]["e2e"][0]["status"], "not_run")
        self.assertEqual(workspace.inventory(self.candidate), self.before)

    def test_candidate_changed_externally_invalidates_results(self):
        self.executor.action = lambda root: (self.candidate / "sample/src/main.py").write_text("value=9\n")
        self.assertEqual(self.validate()["status"], "failed")

    def test_output_is_redacted_and_results_round_trip(self):
        self.executor.stdout = "api_key=synthetic-secret"
        self.executor.stderr = "Bearer synthetic-token-value"
        result = self.validate()
        text = json.dumps(result)
        self.assertNotIn("synthetic-secret", text)
        self.assertNotIn("synthetic-token-value", text)
        self.assertEqual(json.loads(text), result)

    def test_executor_exception_is_unavailable_not_success(self):
        with patch.object(self.executor, "run", side_effect=OSError("secret exception")):
            result = self.validate()
        self.assertEqual(result["tests"]["unit"][0]["status"], "unavailable")
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("secret exception", json.dumps(result))

    def test_credentials_in_test_arguments_are_blocked_before_execution(self):
        self.config["tests"]["unit"][0]["command"]["args"] = ["api_key=synthetic-secret"]
        result = self.validate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.executor.calls, [])
        self.assertNotIn("synthetic-secret", json.dumps(result))

    def test_private_key_body_and_unterminated_block_are_redacted(self):
        for ending in ("\n-----END PRIVATE KEY-----", ""):
            with self.subTest(ending=ending):
                self.executor = FakeProcess(stdout="-----BEGIN PRIVATE KEY-----\nsynthetic-key-body" + ending)
                result = self.validate()
                self.assertNotIn("synthetic-key-body", json.dumps(result))
                self.assertIn("[REDACTED]", result["tests"]["unit"][0]["stdout"])

    def test_required_policies_cannot_weaken_checks(self):
        for policy in ({"run_if": "never", "skip_reason": "skip"}, {"on_failure": "record"}, {"timeout_seconds": 0}):
            with self.subTest(policy=policy):
                saved = copy.deepcopy(self.config)
                self.config["tests"]["unit"][0].update(policy)
                self.assertEqual(self.validate()["status"], "failed")
                self.config = saved

    def test_missing_change_condition_paths_or_outside_paths_are_invalid(self):
        for value in (None, ["outside"]):
            with self.subTest(value=value):
                self.config["tests"]["e2e"][0].update(required=False, run_if="changed_paths")
                if value is not None:
                    self.config["tests"]["e2e"][0]["changed_paths"] = value
                self.assertEqual(self.validate()["status"], "failed")

    def test_bubblewrap_missing_has_no_host_fallback(self):
        with patch("workflow.runtime.test_runner.shutil.which", return_value=None):
            result = test_runner.IsolatedTestProcess().run(self.candidate, "sample/tests", {"program": "python3", "args": []}, 1)
        self.assertEqual(result["status"], "unavailable")

    def test_namespace_failure_is_unavailable(self):
        with patch("workflow.runtime.test_runner.sys.platform", "linux"), patch("workflow.runtime.test_runner.shutil.which", return_value="/fake/bwrap"), patch("workflow.runtime.test_runner._process", return_value={"status": "failed"}):
            result = test_runner.IsolatedTestProcess().run(self.candidate, "sample/tests", {"program": "python3", "args": []}, 1)
        self.assertEqual(result["status"], "unavailable")

    def test_missing_program_is_unavailable(self):
        executor = test_runner.IsolatedTestProcess()
        executor.checked, executor.executable = True, "/fake/bwrap"
        with patch("workflow.runtime.test_runner.shutil.which", return_value=None):
            result = executor.run(self.candidate, "sample/tests", {"program": "missing", "args": []}, 1)
        self.assertEqual(result["status"], "unavailable")

    def test_sandbox_command_contains_no_interpolated_shell_or_credentials(self):
        executor = test_runner.IsolatedTestProcess()
        executor.executable = "/fake/bwrap"
        command = executor._command(self.candidate, "sample/tests", ["python3", "literal; echo injected"])
        self.assertIn("--unshare-all", command)
        self.assertIn("--clearenv", command)
        self.assertNotIn("--share-net", command)
        self.assertEqual(command[-1], "literal; echo injected")
        self.assertNotIn(str(Path.home()), command)

    def test_prj_backend_check_without_prepared_cache_is_unavailable(self):
        executor = test_runner.IsolatedTestProcess()
        executor.checked, executor.executable = True, "/fake/bwrap"
        with patch.dict(os.environ, {"WORKFLOW_PRJ_UV_CACHE": ""}), patch.object(test_runner, "_process") as process:
            result = executor.run(self.candidate, "sample/tests", {"program": "prj-backend-check", "args": []}, 2)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("WORKFLOW_PRJ_UV_CACHE", result["reason"])
        process.assert_not_called()

    def test_prj_backend_check_mounts_only_trusted_launcher_and_read_only_cache(self):
        executor = test_runner.IsolatedTestProcess()
        executor.checked, executor.executable = True, "/fake/bwrap"
        cache = Path(self.temp.name) / "uv-cache"
        cache.mkdir()
        (cache / "CACHEDIR.TAG").touch()
        passed = {"status": "passed", "return_code": 0, "stderr": "", "stdout": ""}
        with patch.dict(os.environ, {"WORKFLOW_PRJ_UV_CACHE": str(cache)}), \
                patch.object(test_runner, "_process", return_value=passed) as process:
            result = executor.run(self.candidate, "sample/tests", {"program": "prj-backend-check", "args": []}, 2)
        self.assertEqual(result["status"], "passed")
        command = process.call_args.args[0]
        self.assertEqual(command[-3:], ["--", "/bin/bash", "/workflow/prj_backend_check.sh"])
        index = command.index("/workflow/uv-cache")
        self.assertEqual(command[index - 2:index], ["--ro-bind", str(cache.resolve())])
        self.assertIn("--unshare-all", command)
        self.assertIn("--clearenv", command)
        self.assertNotIn("--share-net", command)

    def test_macos_backend_check_uses_native_launcher_and_private_scratch(self):
        executor = test_runner.IsolatedTestProcess()
        executor.checked, executor.executable = True, "/fake/sandbox-exec"
        cache = Path(self.temp.name) / "uv-cache"
        cache.mkdir()
        (cache / "CACHEDIR.TAG").touch()
        def execute(command, timeout, *, cwd, env):
            self.assertEqual(command[:2], ["/fake/sandbox-exec", "-f"])
            launcher = Path(command[-1])
            self.assertEqual(launcher.read_bytes(), Path(test_runner.__file__).with_name("prj_backend_check.sh").read_bytes())
            self.assertEqual(env["WORKFLOW_PRJ_UV_CACHE"], str(cache.resolve()))
            scratch = Path(env["WORKFLOW_PRJ_SCRATCH"])
            self.assertTrue(scratch.is_dir())
            self.assertTrue(scratch.is_relative_to(Path("/tmp").resolve()))
            profile = Path(command[2]).read_text()
            self.assertIn('(local unix-socket (subpath ', profile)
            self.assertIn('(remote unix-socket (subpath ', profile)
            self.assertIn(str(scratch / "pg-socket"), profile)
            self.assertNotIn('(allow network*)', profile)
            self.assertIn('"com.apple.system.opendirectoryd.libinfo"', profile)
            self.assertIn(f'(allow file-read* (subpath "{cache.resolve()}"))', profile)
            self.assertNotIn(f'(allow file-write* (subpath "{cache.resolve()}"))', profile)
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("AI_WORKSPACE_API_KEY", env)
            self.assertEqual(cwd, self.candidate / "sample/tests")
            return {"status": "passed", "return_code": 0, "stdout": "", "stderr": ""}
        with patch("workflow.runtime.test_runner.sys.platform", "darwin"), \
                patch.dict(os.environ, {"WORKFLOW_PRJ_UV_CACHE": str(cache), "GH_TOKEN": "synthetic", "AI_WORKSPACE_API_KEY": "synthetic"}), \
                patch.object(executor, "_macos_isolation_ready", return_value=True) as probe, \
                patch.object(test_runner, "_process", side_effect=execute):
            result = executor.run(self.candidate, "sample/tests", {"program": "prj-backend-check", "args": []}, 2)
        self.assertEqual(result["status"], "passed")
        probe.assert_called_once_with(prj_cache=cache.resolve())

    def test_macos_backend_policy_probe_failure_prevents_test_execution(self):
        executor = test_runner.IsolatedTestProcess()
        executor.checked, executor.executable = True, "/fake/sandbox-exec"
        cache = Path(self.temp.name) / "uv-cache"
        cache.mkdir()
        (cache / "CACHEDIR.TAG").touch()
        with patch("workflow.runtime.test_runner.sys.platform", "darwin"), \
                patch.dict(os.environ, {"WORKFLOW_PRJ_UV_CACHE": str(cache)}), \
                patch.object(executor, "_macos_isolation_ready", return_value=False), \
                patch.object(test_runner, "_process") as process:
            result = executor.run(self.candidate, "sample/tests", {"program": "prj-backend-check", "args": []}, 2)
        self.assertEqual(result["status"], "unavailable")

        process.assert_not_called()

    def test_active_prj_config_requires_the_backend_check_on_every_execution(self):
        repo = Path(__file__).resolve().parents[3]
        config = json.loads((repo / "workflow/config/projects/prj.json").read_text())
        check = next(test for test in config["tests"]["unit"] if test["command"]["program"] == "prj-backend-check")
        self.assertTrue(check["required"])
        self.assertEqual(check["run_if"], "always")
        self.assertEqual(check["on_failure"], "block")

    def test_macos_backend_setup_failure_is_unavailable(self):
        executor = test_runner.IsolatedTestProcess()
        executor.checked, executor.executable = True, "/fake/sandbox-exec"
        cache = Path(self.temp.name) / "uv-cache"
        cache.mkdir()
        (cache / "CACHEDIR.TAG").touch()
        with patch("workflow.runtime.test_runner.sys.platform", "darwin"), \
                patch.dict(os.environ, {"WORKFLOW_PRJ_UV_CACHE": str(cache)}), \
                patch.object(executor, "_macos_isolation_ready", return_value=True), \
                patch.object(test_runner, "_process", return_value={"status": "failed", "return_code": 78, "stdout": "", "stderr": "setup failed"}):
            result = executor.run(self.candidate, "sample/tests", {"program": "prj-backend-check", "args": []}, 2)
        self.assertEqual(result["status"], "unavailable")

    def test_oversized_output_is_omitted_entirely(self):
        output = test_runner._Output(io.BytesIO(b"x" * (test_runner.OUTPUT_LIMIT + 1)))
        output.drain()
        self.assertEqual(output.data, b"")
        self.assertIn("omitted", output.text())


@unittest.skipUnless(sys.platform == "linux", "process-group behavior is Linux-specific")
class ProcessTests(unittest.TestCase):
    def test_success_captures_both_streams_and_code(self):
        result = test_runner._process([sys.executable, "-B", "-c", "import sys;print('ok');print('detail',file=sys.stderr)"], 5)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["return_code"], 0)
        self.assertEqual(result["stdout"], "ok\n")
        self.assertEqual(result["stderr"], "detail\n")

    def test_nonzero_and_partial_timeout_output(self):
        failed = test_runner._process([sys.executable, "-B", "-c", "raise SystemExit(3)"], 5)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["return_code"], 3)
        timed = test_runner._process([sys.executable, "-B", "-c", "import time; print('began',flush=True);time.sleep(10)"], 0.2)
        self.assertEqual(timed["status"], "timeout")
        self.assertIn("began", timed["stdout"])
        self.assertLess(timed["duration_seconds"], 5)

    def test_missing_process_is_unavailable(self):
        self.assertEqual(test_runner._process(["/no/such/test-tool"], 1)["status"], "unavailable")

    def test_oversized_process_output_is_not_a_success(self):
        result = test_runner._process([sys.executable, "-B", "-c", "print('x'*300000)"], 5)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("omitted", result["stdout"])

    def test_background_descendant_is_terminated_after_parent_exit(self):
        import time
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "child-marker"
            child = f"import time,pathlib;time.sleep(0.4);pathlib.Path({str(marker)!r}).write_text('alive')"
            parent = "import subprocess,sys;subprocess.Popen([sys.executable,'-B','-c',sys.argv[1]])"
            result = test_runner._process([sys.executable, "-B", "-c", parent, child], 5)
            self.assertEqual(result["status"], "passed")
            time.sleep(0.6)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()

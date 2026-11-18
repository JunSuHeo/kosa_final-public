"""CLI invocation contract tests using mocks; no real Codex calls."""

from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

from workflow.runtime.codex_adapter import CodexCLI, ExecutionError, failure_message, restricted_environment


SETTINGS = {"version": "1.2.3", "model": "test-model", "timeout_seconds": 10}
GLOBAL_HELP = "--ask-for-approval --strict-config"
EXEC_HELP = "--sandbox --skip-git-repo-check --ephemeral --ignore-user-config --ignore-rules --config --model"


class AdapterTests(unittest.TestCase):
    def test_missing_cli_does_not_probe_or_execute(self):
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value=None), patch("workflow.runtime.codex_adapter.subprocess.run") as probe:
            with self.assertRaises(ExecutionError) as error:
                CodexCLI().preflight(SETTINGS)
        self.assertEqual(error.exception.status, "codex_missing")
        probe.assert_not_called()

    def test_preflight_checks_exact_version_and_options(self):
        outputs = [subprocess.CompletedProcess([], 0, "codex-cli 1.2.3", ""),
                   subprocess.CompletedProcess([], 0, GLOBAL_HELP, ""),
                   subprocess.CompletedProcess([], 0, EXEC_HELP, "")]
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value="/fake/codex"), patch("workflow.runtime.codex_adapter.sys.platform", "linux"), patch("workflow.runtime.codex_adapter.subprocess.run", side_effect=outputs):
            self.assertEqual(CodexCLI().preflight(SETTINGS)["version"], "1.2.3")

    def test_wrong_version_is_rejected(self):
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value="/fake/codex"), patch("workflow.runtime.codex_adapter.sys.platform", "linux"), patch("workflow.runtime.codex_adapter.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "codex-cli 9.9.9", "")):
            with self.assertRaises(ExecutionError) as error:
                CodexCLI().preflight(SETTINGS)
        self.assertEqual(error.exception.status, "environment_error")

    def test_missing_safety_flags_are_rejected(self):
        outputs = [subprocess.CompletedProcess([], 0, "codex-cli 1.2.3", ""),
                   subprocess.CompletedProcess([], 0, "--help", ""),
                   subprocess.CompletedProcess([], 0, EXEC_HELP, "")]
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value="/fake/codex"), patch("workflow.runtime.codex_adapter.sys.platform", "linux"), patch("workflow.runtime.codex_adapter.subprocess.run", side_effect=outputs):
            with self.assertRaises(ExecutionError):
                CodexCLI().preflight(SETTINGS)

    def test_native_windows_execution_is_blocked(self):
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value="codex.exe"), patch("workflow.runtime.codex_adapter.sys.platform", "win32"):
            with self.assertRaises(ExecutionError) as error:
                CodexCLI().preflight(SETTINGS)
        self.assertEqual(error.exception.status, "environment_error")

    def test_secret_environment_is_not_inherited(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "synthetic", "OPENAI_API_KEY": "synthetic", "BASH_ENV": "/unsafe", "PATH": "/tools"}):
            environment = restricted_environment()
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("BASH_ENV", environment)
        self.assertEqual(environment["PATH"], "/tools")

    def test_prompt_uses_stdin_and_raw_output_is_not_logged(self):
        adapter = CodexCLI()
        adapter.executable = "/fake/codex"
        process = Mock(returncode=0)
        process.communicate.return_value = (None, "")
        with patch("workflow.runtime.codex_adapter.subprocess.Popen", return_value=process) as spawn:
            self.assertEqual(adapter.execute("task; shell syntax", Path("/workspace"), SETTINGS), 0)
        command = spawn.call_args.args[0]
        self.assertNotIn("task; shell syntax", command)
        self.assertEqual(command[-1], "-")
        self.assertIn("workspace-write", command)
        self.assertIn("sandbox_workspace_write.exclude_slash_tmp=true", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(spawn.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(spawn.call_args.kwargs["stderr"], subprocess.PIPE)
        process.communicate.assert_called_once_with("task; shell syntax", timeout=10)

    def test_nonzero_execution_exit_is_a_failure(self):
        adapter = CodexCLI()
        adapter.executable = "/fake/codex"
        process = Mock(returncode=7)
        process.communicate.return_value = (None, "unknown failure")
        with patch("workflow.runtime.codex_adapter.subprocess.Popen", return_value=process):
            with self.assertRaises(ExecutionError) as error:
                adapter.execute("task", Path("/workspace"), SETTINGS)
        self.assertEqual(error.exception.status, "codex_failed")
        self.assertEqual(error.exception.return_code, 7)

    def test_unsupported_account_model_is_explained_without_raw_output(self):
        adapter = CodexCLI()
        adapter.executable = "/fake/codex"
        process = Mock(returncode=1)
        process.communicate.return_value = (None,
            "ERROR: The 'private-model' model is not supported when using Codex with a ChatGPT account.\n"
            "secret=synthetic-secret")
        with patch("workflow.runtime.codex_adapter.subprocess.Popen", return_value=process):
            with self.assertRaises(ExecutionError) as error:
                adapter.execute("task", Path("/workspace"), SETTINGS)
        self.assertEqual(error.exception.status, "codex_failed")
        self.assertIn("not supported", str(error.exception))
        self.assertNotIn("private-model", str(error.exception))
        self.assertNotIn("synthetic-secret", str(error.exception))

    def test_failure_diagnostics_are_fixed_and_do_not_echo_secrets(self):
        for raw, expected in [
            ("ERROR: 401 Unauthorized Bearer synthetic-secret", "authentication failed"),
            ("ERROR: Usage limit exceeded secret=synthetic-secret", "usage or rate limit"),
            ("ERROR: unexpected synthetic-secret", "withheld"),
            (None, "withheld"),
            ("user\n401 Unauthorized", "withheld"),
        ]:
            with self.subTest(raw=raw):
                message = failure_message(raw)
                self.assertIn(expected, message)
                self.assertNotIn("synthetic-secret", message)

    def test_timeout_terminates_process_group_before_returning(self):
        adapter = CodexCLI()
        adapter.executable = "/fake/codex"
        process = Mock(pid=123, returncode=-9)
        process.communicate.side_effect = [subprocess.TimeoutExpired("codex", 10), (None, None)]
        with patch("workflow.runtime.codex_adapter.subprocess.Popen", return_value=process), patch("workflow.runtime.codex_adapter.os.killpg", create=True) as kill, patch("workflow.runtime.codex_adapter.signal.SIGKILL", 9, create=True):
            with self.assertRaises(ExecutionError) as error:
                adapter.execute("task", Path("/workspace"), SETTINGS)
        self.assertEqual(error.exception.status, "timeout")
        kill.assert_called_once()
        self.assertEqual(process.communicate.call_count, 2)


if __name__ == "__main__":
    unittest.main()

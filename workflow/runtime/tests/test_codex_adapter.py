"""CLI invocation contract tests using mocks; no real Codex calls."""

from pathlib import Path
import json
import subprocess
import tomllib
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

    def test_macos_preflight_accepts_arm64_and_x86_64_python(self):
        for machine in ("arm64", "aarch64", "x86_64"):
            outputs = [subprocess.CompletedProcess([], 0, "codex-cli 1.2.3", ""),
                       subprocess.CompletedProcess([], 0, GLOBAL_HELP, ""),
                       subprocess.CompletedProcess([], 0, EXEC_HELP, "")]
            with self.subTest(machine=machine), patch("workflow.runtime.codex_adapter.shutil.which", return_value="/fake/codex"), \
                    patch("workflow.runtime.codex_adapter.sys.platform", "darwin"), \
                    patch("workflow.runtime.codex_adapter.host_platform.machine", return_value=machine), \
                    patch("workflow.runtime.codex_adapter.subprocess.run", side_effect=outputs):
                self.assertEqual(CodexCLI().preflight(SETTINGS)["platform"], "macos")

    def test_wrong_version_is_rejected(self):
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value="/fake/codex"), patch("workflow.runtime.codex_adapter.sys.platform", "linux"), patch("workflow.runtime.codex_adapter.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "codex-cli 9.9.9", "")):
            with self.assertRaises(ExecutionError) as error:
                CodexCLI().preflight(SETTINGS)
        self.assertEqual(error.exception.status, "environment_error")
        self.assertEqual(error.exception.operation, "check_codex_version")

    def test_missing_safety_flags_are_rejected(self):
        outputs = [subprocess.CompletedProcess([], 0, "codex-cli 1.2.3", ""),
                   subprocess.CompletedProcess([], 0, "--help", ""),
                   subprocess.CompletedProcess([], 0, EXEC_HELP, "")]
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value="/fake/codex"), patch("workflow.runtime.codex_adapter.sys.platform", "linux"), patch("workflow.runtime.codex_adapter.subprocess.run", side_effect=outputs):
            with self.assertRaises(ExecutionError) as error:
                CodexCLI().preflight(SETTINGS)
        self.assertEqual(error.exception.operation, "check_codex_options")
        self.assertEqual(error.exception.option, "--ask-for-approval")

    def test_failed_cli_inspection_identifies_the_probe_without_raw_output(self):
        adapter = CodexCLI()
        adapter.executable = "/fake/codex"
        for args, operation in ((("--version",), "inspect_codex_version"),
                                (("--help",), "inspect_codex_help"),
                                (("exec", "--help"), "inspect_codex_exec_help")):
            with self.subTest(args=args), patch("workflow.runtime.codex_adapter.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 1, "", "synthetic-private-value")):
                with self.assertRaises(ExecutionError) as error:
                    adapter._inspect(*args)
                self.assertEqual(error.exception.operation, operation)
                self.assertNotIn("synthetic-private-value", str(error.exception))

    def test_native_windows_execution_is_blocked(self):
        with patch("workflow.runtime.codex_adapter.shutil.which", return_value="codex.exe"), patch("workflow.runtime.codex_adapter.sys.platform", "win32"):
            with self.assertRaises(ExecutionError) as error:
                CodexCLI().preflight(SETTINGS)
        self.assertEqual(error.exception.status, "environment_error")
        self.assertEqual(error.exception.operation, "check_codex_platform")

    def test_secret_environment_is_not_inherited(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "synthetic", "OPENAI_API_KEY": "synthetic", "AI_WORKSPACE_API_KEY": "synthetic", "BASH_ENV": "/unsafe", "PATH": "/tools"}):
            environment = restricted_environment()
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("AI_WORKSPACE_API_KEY", environment)
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

    def test_ai_workspace_key_authenticates_analysis_and_execution_only(self):
        adapter = CodexCLI()
        adapter.executable = "/fake/codex"
        credentials = {"AI_WORKSPACE_API_KEY": "synthetic-provider-credential",
                       "GH_TOKEN": "synthetic-issue-credential", "OPENAI_API_KEY": "synthetic-openai-credential",
                       "WORKFLOW_STATE_KEY": "synthetic-state-credential", "WORKFLOW_PUBLISH_TOKEN": "synthetic-publish-credential"}
        for analyze in (False, True):
            with self.subTest(analyze=analyze):
                process = Mock(returncode=0)
                process.communicate.return_value = (None, "")
                def spawn(command, **kwargs):
                    self.assertEqual(kwargs["env"]["AI_WORKSPACE_API_KEY"], credentials["AI_WORKSPACE_API_KEY"])
                    for key in credentials.keys() - {"AI_WORKSPACE_API_KEY"}:
                        self.assertNotIn(key, kwargs["env"])
                    for value in credentials.values():
                        self.assertNotIn(value, " ".join(command))
                    overrides = [command[i + 1] for i, arg in enumerate(command) if arg == "--config"]
                    policy = next(tomllib.loads(value)["shell_environment_policy"] for value in overrides
                                  if value.startswith("shell_environment_policy="))
                    self.assertEqual(policy["inherit"], "core")
                    self.assertEqual(policy["set"], {})
                    self.assertEqual(policy["filters"], {"AI_WORKSPACE_API_KEY": "exclude"})
                    self.assertFalse(policy["experimental_use_profile"])
                    self.assertFalse(any(value.startswith("model_provider=") for value in overrides))
                    self.assertNotIn("--ignore-user-config", command)
                    if analyze:
                        Path(command[command.index("--output-last-message") + 1]).write_text(
                            json.dumps({"ready": True}), encoding="utf-8")
                    return process
                with patch.dict("os.environ", credentials), patch.object(adapter, "_inspect",
                        return_value="--output-schema --output-last-message"), patch(
                        "workflow.runtime.codex_adapter.subprocess.Popen", side_effect=spawn):
                    if analyze:
                        self.assertEqual(adapter.analyze("task", Path("/workspace"), SETTINGS, {}), {"ready": True})
                    else:
                        self.assertEqual(adapter.execute("task", Path("/workspace"), SETTINGS), 0)

    def test_cli_inspection_does_not_receive_provider_credentials(self):
        adapter = CodexCLI()
        adapter.executable = "/fake/codex"
        with patch.dict("os.environ", {"AI_WORKSPACE_API_KEY": "synthetic-provider-credential"}), patch(
                "workflow.runtime.codex_adapter.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "version", "")) as probe:
            adapter._inspect("--version")
        self.assertNotIn("AI_WORKSPACE_API_KEY", probe.call_args.kwargs["env"])

    def test_missing_ai_workspace_auth_is_reported_without_raw_output(self):
        adapter = CodexCLI()
        adapter.executable = "/fake/codex"
        for raw, expected in [
            ("Error: Missing environment variable: `AI_WORKSPACE_API_KEY`.\nsecret=synthetic-secret", "codex_provider_auth_missing"),
            ("Error: Missing environment variable: `OTHER_API_KEY`.\n", "codex_failed"),
            ("user\nMissing environment variable: `AI_WORKSPACE_API_KEY`", "codex_failed"),
        ]:
            with self.subTest(raw=raw):
                process = Mock(returncode=1)
                process.communicate.return_value = (None, raw)
                with patch("workflow.runtime.codex_adapter.subprocess.Popen", return_value=process):
                    with self.assertRaises(ExecutionError) as error:
                        adapter.execute("task", Path("/workspace"), SETTINGS)
                self.assertEqual(error.exception.status, expected)
                self.assertEqual(error.exception.return_code, 1)
                self.assertNotIn("synthetic-secret", str(error.exception))

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

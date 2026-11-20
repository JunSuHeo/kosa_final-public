"""Codex CLI boundary; help/version inspection never invokes a coding task.

Verified official interfaces (2026-11-13):
https://learn.chatgpt.com/docs/developer-commands?surface=cli
https://learn.chatgpt.com/docs/non-interactive-mode
https://learn.chatgpt.com/docs/config-file/config-reference

The adapter supports Linux (including WSL) and macOS. It requires a pinned CLI
version and rejects unsupported flags. Authentication uses existing CLI login;
API keys and GitHub credentials are not inherited through environment variables.
"""

from __future__ import annotations

import os
import platform as host_platform
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import json
import tempfile
from typing import Any


class ExecutionError(Exception):
    def __init__(self, status: str, message: str, return_code: int | None = None):
        super().__init__(message)
        self.status = status
        self.return_code = return_code


def runtime_platform() -> str | None:
    if sys.platform == "linux":
        return "linux"
    if sys.platform == "darwin" and host_platform.machine().lower() in ("arm64", "aarch64"):
        return "macos"
    return None


def restricted_environment() -> dict[str, str]:
    # Do not pass arbitrary inherited variables, including API/GitHub tokens,
    # LD_PRELOAD, BASH_ENV, PYTHONPATH, or application secrets.
    allowed = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def failure_message(stderr: str | None) -> str:
    """Return only fixed diagnostics; never interpolate CLI output or secrets.

    Stderr is inspected in memory and is not persisted. Unknown failures stay
    redacted rather than disclosing arbitrary model output, URLs or headers.
    """
    lines = (stderr or "")[-65536:].splitlines()
    errors = "\n".join(line.lower() for line in lines
                       if line.lower().startswith(("error:", "error ")))
    if "model is not supported when using codex with a chatgpt account" in errors:
        return "The configured model is not supported by this ChatGPT account. Select a model available in Codex for this account."
    if "401" in errors or "unauthorized" in errors or "not logged in" in errors:
        return "Codex authentication failed. Check CLI login status in the same execution environment."
    if "usage limit" in errors or "quota" in errors or "429" in errors:
        return "Codex reported a usage or rate limit. Check account limits before retrying."
    return "Codex execution failed; unrecognized raw output is withheld to protect secrets."


class CodexCLI:
    def __init__(self) -> None:
        self.executable: str | None = None
        self.version: str | None = None

    def _inspect(self, *args: str) -> str:
        try:
            result = subprocess.run(
                [self.executable, *args], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10,
                env=restricted_environment(), check=False,
            )
        except FileNotFoundError as exc:
            raise ExecutionError("codex_missing", "Codex CLI was not found on PATH.") from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExecutionError("environment_error", "Cannot inspect Codex CLI help/version.") from exc
        if result.returncode:
            raise ExecutionError("environment_error", "Codex CLI help/version inspection failed.", result.returncode)
        return result.stdout + result.stderr

    def preflight(self, settings: dict[str, Any]) -> dict[str, str]:
        self.executable = shutil.which("codex")
        if not self.executable:
            raise ExecutionError("codex_missing", "Codex CLI was not found on PATH; no task was executed.")
        platform = runtime_platform()
        if platform is None:
            raise ExecutionError("environment_error", "This adapter supports Linux/WSL and macOS ARM64 only.")
        version_output = self._inspect("--version")
        match = re.search(r"\b([0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?)\b", version_output)
        if not match or match.group(1) != settings["version"]:
            raise ExecutionError("environment_error", "Installed Codex CLI version does not match the configured version.")
        self.version = match.group(1)
        global_help = self._inspect("--help")
        exec_help = self._inspect("exec", "--help")
        for flag in ("--ask-for-approval", "--strict-config"):
            if flag not in global_help:
                raise ExecutionError("environment_error", "Installed Codex CLI lacks required global safety options.")
        for flag in ("--sandbox", "--skip-git-repo-check", "--ephemeral", "--ignore-rules", "--config", "--model"):
            if flag not in exec_help:
                raise ExecutionError("environment_error", "Installed Codex CLI lacks required execution/safety options.")
        return {"adapter": "codex_cli", "version": self.version, "platform": platform}

    def execute(self, prompt: str, workspace: Path, settings: dict[str, Any]) -> int:
        return self._execute(prompt, workspace, settings)

    def analyze(self, prompt: str, workspace: Path, settings: dict[str, Any], schema: dict) -> dict:
        """Read-only planning, using the same pinned CLI and credential filtering."""
        help_text = self._inspect("exec", "--help")
        if any(flag not in help_text for flag in ("--output-schema", "--output-last-message")):
            raise ExecutionError("analysis_failed", "Codex lacks structured read-only analysis options.")
        with tempfile.TemporaryDirectory(prefix="workflow-analysis-output-") as temporary:
            schema_path = Path(temporary) / "schema.json"
            output_path = Path(temporary) / "analysis.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            self._execute(prompt, workspace, settings, sandbox="read-only", extra=[
                "--output-schema", str(schema_path), "--output-last-message", str(output_path)])
            try:
                if output_path.stat().st_size > 32000:
                    raise ValueError()
                return json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ExecutionError("analysis_failed", "Codex did not return a bounded JSON execution plan.") from exc

    def _execute(self, prompt, workspace, settings, *, sandbox="workspace-write", extra=()):
        if self.executable is None:
            raise ExecutionError("environment_error", "Codex preflight must complete before execution.")
        command = [
            self.executable, "--strict-config", "--ask-for-approval", "never", "exec",
            "--sandbox", sandbox, "--skip-git-repo-check",
            "--ephemeral", "--ignore-rules",
            "--model", settings["model"],
        ]
        for override in ((
            "sandbox_workspace_write.network_access=false",
            "sandbox_workspace_write.writable_roots=[]",
            "sandbox_workspace_write.exclude_slash_tmp=true",
            "sandbox_workspace_write.exclude_tmpdir_env_var=true",
        ) if sandbox == "workspace-write" else ("sandbox_workspace_write.network_access=false",)):
            command.extend(["--config", override])
        command.extend(extra)
        command.append("-")  # Official prompt-from-stdin interface; no shell interpolation.
        try:
            process = subprocess.Popen(
                command, cwd=workspace, env=restricted_environment(),
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise ExecutionError("codex_missing", "Codex CLI disappeared before task execution.") from exc
        except OSError as exc:
            raise ExecutionError("codex_failed", "Codex process could not be started.") from exc
        try:
            _, stderr = process.communicate(prompt, timeout=settings["timeout_seconds"])
        except BaseException as exc:
            # Stop descendants as well before scanning or removing the workspace.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            status = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "unexpected_error"
            raise ExecutionError(status, "Codex execution timed out." if status == "timeout" else "Codex execution was interrupted.") from exc
        if process.returncode:
            raise ExecutionError("codex_failed", failure_message(stderr), process.returncode)
        return process.returncode

"""Independent test execution on a disposable candidate copy (stdlib only).

Linux Bubblewrap is required for real execution. No host fallback is provided:
missing/unsupported isolation is unavailable, never a successful test. The
trusted configuration is supplied by the controller, not by generated files.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from . import validate_config as validator, workspace
from .codex_adapter import ExecutionError


SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"
OUTPUT_LIMIT = 256 * 1024
_NO_TESTS = re.compile(r"\bRan\s+0\s+tests?\b|\bno tests (?:ran|collected|found)\b", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Output:
    """Drain even oversized output; never spool raw output to disk."""
    def __init__(self, stream):
        self.stream = stream
        self.data = bytearray()
        self.omitted = False
        self.error = False

    def drain(self):
        try:
            with self.stream:
                while chunk := self.stream.read(8192):
                    if not self.omitted:
                        if len(self.data) + len(chunk) > OUTPUT_LIMIT:
                            self.data.clear()
                            self.omitted = True
                        else:
                            self.data.extend(chunk)
        except OSError:
            self.error = True

    def text(self):
        if self.omitted:
            return "[output omitted: exceeded 256 KiB limit]"
        return workspace.redact(self.data.decode("utf-8", errors="replace"))


def _process(command: list[str], timeout: float) -> dict[str, Any]:
    """Collect actual process results, kill descendants and bound both streams."""
    started = time.monotonic()
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, shell=False, start_new_session=True,
                                   env={"PATH": SYSTEM_PATH, "LANG": "C.UTF-8"})
    except OSError:
        return {"status": "unavailable", "return_code": None, "duration_seconds": time.monotonic() - started,
                "stdout": "", "stderr": "", "reason": "The configured process could not be started."}
    outputs = [_Output(process.stdout), _Output(process.stderr)]
    threads = [threading.Thread(target=output.drain, daemon=True) for output in outputs]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        # Even a successfully exited parent may leave background descendants.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for thread in threads:
            thread.join(timeout=5)
    stdout, stderr = (output.text() for output in outputs)
    status = "timeout" if timed_out else "passed" if process.returncode == 0 else "failed"
    reason = "Test exceeded its wall-clock limit." if timed_out else None if status == "passed" else "Test process returned a nonzero exit code."
    if any(thread.is_alive() for thread in threads) or any(output.error for output in outputs):
        status, reason = "unavailable", "Test output could not be fully collected."
    elif not timed_out and any(output.omitted for output in outputs):
        status, reason = "unavailable", "Test output exceeded the collection limit; complete evidence is unavailable."
    return {"status": status, "return_code": process.returncode,
            "duration_seconds": round(time.monotonic() - started, 6),
            "stdout": stdout, "stderr": stderr, "reason": reason}


class IsolatedTestProcess:
    """No shell, credentials, host home, original checkout or host networking."""
    def __init__(self):
        self.executable = None
        self.error = None
        self.checked = False

    def _command(self, root: Path, cwd: str, argv: list[str]) -> list[str]:
        command = [self.executable, "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL"]
        # Approved system runtime only; no /root, /home, /mnt or full /etc bind.
        for value in ("/usr", "/bin", "/lib", "/lib64", "/etc/alternatives", "/etc/ld.so.cache"):
            if Path(value).exists():
                command.extend(["--ro-bind", value, value])
        command.extend(["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                        "--dir", "/home/test", "--bind", str(root), "/workspace",
                        "--chdir", "/workspace" if cwd == "." else "/workspace/" + cwd,
                        "--clearenv", "--setenv", "PATH", SYSTEM_PATH,
                        "--setenv", "HOME", "/home/test", "--setenv", "TMPDIR", "/tmp",
                        "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
                        "--", *argv])
        return command

    def run(self, root: Path, cwd: str, command: dict[str, Any], timeout: float) -> dict[str, Any]:
        if not self.checked:
            self.checked = True
            self.executable = shutil.which("bwrap", path=SYSTEM_PATH) if sys.platform == "linux" else None
            if self.executable is None:
                self.error = "Linux Bubblewrap isolation is unavailable; host execution is prohibited."
            else:
                probe = _process(self._command(root, ".", ["/bin/true"]), 10)
                if probe["status"] != "passed":
                    self.error = "Bubblewrap namespace isolation could not be initialized."
        if self.error:
            return {"status": "unavailable", "return_code": None, "duration_seconds": 0,
                    "stdout": "", "stderr": "", "reason": self.error}
        executable = shutil.which(command["program"], path=SYSTEM_PATH)
        if executable is None:
            return {"status": "unavailable", "return_code": None, "duration_seconds": 0,
                    "stdout": "", "stderr": "", "reason": "Configured test executable is not available on the isolated system PATH."}
        result = _process(self._command(root, cwd, [executable, *command["args"]]), timeout)
        if result["stderr"].startswith("bwrap:"):
            result.update(status="unavailable", reason="The isolated runtime or executable could not be initialized.")
        elif result["status"] == "failed" and re.search(
            r"ModuleNotFoundError: No module named|Error: Cannot find module|Executable doesn't exist",
            result["stderr"] + result["stdout"],
        ):
            result.update(status="unavailable", reason="The runner reported a missing module or runtime dependency.")
        return result


def _skip(test: dict[str, Any], changes: list[dict[str, Any]]) -> str | None:
    condition = test.get("run_if", "always")
    if condition == "never":
        return workspace.redact(test["skip_reason"])
    if condition == "changed_paths":
        if not any(Path(change["path"]).is_relative_to(Path(scope))
                   for change in changes for scope in test["changed_paths"]):
            return "No added, modified or deleted file matches the configured changed_paths condition."
    return None


def judge(results: list[dict[str, Any]]) -> tuple[str, list[str]]:
    reasons = []
    for result in results:
        if result["required"] and result["status"] != "passed":
            reasons.append(f"Required check {result['id']} is {result['status']}.")
        elif not result["required"] and result["status"] in ("failed", "unavailable", "timeout") and result["on_failure"] == "block":
            reasons.append(f"Optional check {result['id']} is {result['status']} and blocks validation.")
    if reasons:
        return "failed", reasons
    if not any(result["status"] == "passed" for result in results):
        return "not_run", ["No test completed successfully; validation cannot pass without executed checks."]
    return "passed", []


def validate_workspace(candidate: Path, config: dict[str, Any], before: dict[str, Any],
                       config_relative: str, *, executor=None, stop_on_failure=False) -> dict[str, Any]:
    """Verify candidate boundaries then run Unit/E2E checks using frozen policy."""
    validation = {"status": "running", "started_at": _now(), "ended_at": None,
                  "scope_status": "not_run", "tests": {"unit": [], "e2e": []}, "errors": [],
                  "environment": "linux-bubblewrap", "candidate_sha256": None}
    try:
        changes = workspace.collect(candidate, config, before, config_relative)
        validation["scope_status"] = "passed"
        schema = validator._read_json(validator.SCHEMA_PATH)
        validator._check_schema(schema, schema)
        errors = validator._validate_node(config, schema, schema, "$")
        if not errors:
            errors = validator._check_semantics(config, candidate)
        if errors:
            raise ExecutionError("validation_failed", "Candidate test configuration or required paths are invalid: " + "; ".join(errors))
        config_text = json.dumps(config)
        if workspace.redact(config_text) != config_text:
            raise ExecutionError("validation_failed", "Sensitive configuration content was detected; tests were blocked.")
        content = workspace.inventory(candidate)
        validation["candidate_sha256"] = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
        executor = executor if executor is not None else IsolatedTestProcess()
        with tempfile.TemporaryDirectory(prefix="workflow-validation-") as temporary:
            root = Path(temporary) / "workspace"
            shutil.copytree(candidate, root, symlinks=True)
            if workspace.inventory(root) != content:
                raise ExecutionError("validation_failed", "Candidate changed while preparing the independent test snapshot.")
            inputs_changed = False
            earlier_failure = False
            for kind in ("unit", "e2e"):
                for test in config["tests"][kind]:
                    started = _now()
                    result = {"id": test["id"], "kind": kind, "required": test["required"],
                              "command": {"program": workspace.redact(test["command"]["program"]),
                                          "args": [workspace.redact(arg) for arg in test["command"]["args"]]},
                              "cwd": test["cwd"], "timeout_seconds": test.get("timeout_seconds", 300),
                              "on_failure": test.get("on_failure", "block"), "started_at": started,
                              "status": "not_run", "return_code": None, "duration_seconds": 0,
                              "stdout": "", "stderr": "", "reason": None}
                    reason = ("A previous test changed candidate input files; further execution is blocked." if inputs_changed
                              else "A previous blocking test failed; later checks were not run." if earlier_failure else _skip(test, changes))
                    if reason:
                        result["reason"] = reason
                    elif not workspace.resolve(test["cwd"], root).is_dir():
                        result.update(status="unavailable", reason="The test working directory is unavailable.")
                    else:
                        try:
                            result.update(executor.run(root, test["cwd"], test["command"], test.get("timeout_seconds", 300)))
                        except (OSError, ValueError):
                            result.update(status="unavailable", reason="Test process execution was unavailable; exception details are withheld.")
                        result["stdout"] = workspace.redact(result["stdout"])
                        result["stderr"] = workspace.redact(result["stderr"])
                        if result["status"] == "passed" and _NO_TESTS.search(result["stdout"] + "\n" + result["stderr"]):
                            result.update(status="failed", reason="The runner reported zero tests; exit code 0 is not sufficient.")
                        after = workspace.inventory(root)
                        if any(after.get(path) != info for path, info in content.items()):
                            inputs_changed = True
                            validation["errors"].append("A test modified or deleted candidate input files.")
                    result["ended_at"] = _now()
                    validation["tests"][kind].append(result)
                    if stop_on_failure and ((result["required"] and result["status"] != "passed")
                            or (result["status"] in ("failed", "unavailable", "timeout") and result["on_failure"] == "block")):
                        earlier_failure = True
            validation["status"], reasons = judge(validation["tests"]["unit"] + validation["tests"]["e2e"])
            validation["errors"].extend(reasons)
            if inputs_changed:
                validation["status"] = "failed"
        if workspace.inventory(candidate) != content:
            raise ExecutionError("validation_failed", "Candidate changed during validation; test results no longer apply.")
    except ExecutionError as exc:
        validation["status"] = "failed"
        if exc.status == "path_violation":
            validation["scope_status"] = "failed"
        validation["errors"].append(workspace.redact(str(exc)))
    except (OSError, ValueError, TypeError):
        validation["status"] = "failed"
        validation["errors"].append("Independent test preparation or result collection failed; details are withheld.")
    finally:
        validation["ended_at"] = _now()
    return validation

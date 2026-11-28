"""Independent test execution on a disposable candidate copy (stdlib only).

Linux Bubblewrap or macOS seatbelt isolation is required for real execution.
No host fallback is provided: missing/unsupported isolation is unavailable,
never a successful test. Configuration comes from the trusted controller.
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
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from . import validate_config as validator, workspace
from .codex_adapter import ExecutionError


SYSTEM_PATH = ("/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
               if sys.platform == "darwin" else "/usr/local/bin:/usr/bin:/bin")
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


def _process(command: list[str], timeout: float, *, cwd: Path | None = None,
             env: dict[str, str] | None = None) -> dict[str, Any]:
    """Collect actual process results, kill descendants and bound both streams."""
    started = time.monotonic()
    try:
        process_env = {"PATH": SYSTEM_PATH, "LANG": "C.UTF-8"}
        if env:
            process_env.update(env)
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, shell=False, start_new_session=True,
                                   cwd=cwd, env=process_env)
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
        self._isolation_failure = None

    @staticmethod
    def _profile_path(path: Path) -> str:
        value = str(path.resolve())
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _macos_command(self, root: Path, cwd: str, argv: list[str], scratch: Path, *, prj_cache: Path | None = None):
        scratch = scratch.resolve()
        home = scratch / "home"
        temporary = scratch / "tmp"
        home.mkdir(mode=0o700, exist_ok=True)
        temporary.mkdir(mode=0o700, exist_ok=True)
        host_home = Path.home().resolve()
        profile_path = scratch / "workflow-test.sb"
        allowed_reads = (
            "/System", "/usr", "/bin", "/sbin", "/Library/Apple",
            "/Library/Frameworks", "/Library/Developer/CommandLineTools",
            "/opt/homebrew/bin", "/opt/homebrew/Cellar", "/opt/homebrew/Frameworks",
            "/usr/local/bin", "/usr/local/Cellar", "/usr/local/Frameworks",
            "/private/etc", "/dev/null", "/dev/zero", "/dev/random", "/dev/urandom",
        )
        rules = ["(version 1)", "(deny default)", "(allow process-exec)", "(allow process-fork)",
                 "(allow sysctl-read)"]
        rules.extend(f"(allow file-read* (subpath {self._profile_path(Path(value))}))"
                     for value in allowed_reads if Path(value).exists())
        rules.append('(allow file-read-metadata (literal "/") (literal "/opt") (literal "/Library") '
                     '(literal "/tmp") (literal "/private/tmp") (subpath "/opt/homebrew") '
                     '(literal "/private") (literal "/private/var") (subpath "/private/var/folders"))')
        rules.append(f"(allow file-read-metadata (literal {self._profile_path(root.parent)}) "
                     f"(literal {self._profile_path(scratch.parent)}))")
        rules.append(f"(allow file-read* (subpath {self._profile_path(root)}))")
        rules.append(f"(allow file-read* (subpath {self._profile_path(scratch)}))")
        rules.append(f"(allow file-write* (subpath {self._profile_path(root)}))")
        rules.append(f"(allow file-write* (subpath {self._profile_path(scratch)}))")
        rules.append(f"(deny file-read* (subpath {self._profile_path(host_home)}))")
        if prj_cache is None:
            rules.append("(deny network*)")
        else:
            # Default-deny still blocks IP networking and every other Unix socket.
            socket_path = self._profile_path(temporary / "pg-socket")
            rules.extend([
                f"(allow file-read* (subpath {self._profile_path(prj_cache)}))",
                "(allow system-socket (socket-domain AF_UNIX))",
                f"(allow network-bind (local unix-socket (subpath {socket_path})))",
                f"(allow network-outbound (remote unix-socket (subpath {socket_path})))",
                f"(allow network-inbound (local unix-socket (subpath {socket_path})))",
                # PostgreSQL on Darwin uses System V semaphores, not shared memory.
                "(allow ipc-sysv-sem)",
                '(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo"))',
            ])
            launcher = Path(__file__).resolve().with_name("prj_backend_check.sh")
            shutil.copyfile(launcher, scratch / launcher.name)
        profile_path.write_text("\n".join(rules) + "\n", encoding="utf-8")
        profile_path.chmod(0o600)
        environment = {"PATH": SYSTEM_PATH, "HOME": str(home), "TMPDIR": str(temporary),
                       "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
        if prj_cache is not None:
            environment.update(WORKFLOW_PRJ_UV_CACHE=str(prj_cache), WORKFLOW_PRJ_SCRATCH=str(temporary))
        if Path(argv[0]).name == "uv":
            environment.update(UV_PROJECT_ENVIRONMENT=str(temporary / "uv-venv"),
                               UV_CACHE_DIR=str(temporary / "uv-cache"))
        workdir = root if cwd == "." else workspace.resolve(cwd, root)
        return [self.executable, "-f", str(profile_path), *argv], environment, workdir

    def _macos_isolation_ready(self, *, prj_cache: Path | None = None) -> bool:
        self._isolation_failure = None
        python = shutil.which("python3", path=SYSTEM_PATH)
        host_home = Path.home().resolve()
        result = {"status": "unavailable", "return_code": None, "duration_seconds": 0,
                  "stdout": "", "stderr": "", "reason": None}
        if python is None or not host_home.is_dir():
            stage = "python_lookup" if python is None else "host_home"
            self._isolation_failure = {**result, "isolation_stage": stage,
                                       "reason": f"macOS sandbox isolation prerequisite is unavailable at {stage}; the configured test was not started."}
            return False
        probe = (
            "import os, socket, sys\n"
            "def stage(name):\n"
            "    print('workflow-isolation-stage=' + name, file=sys.stderr, flush=True)\n"
            "workspace, temporary, host_home = sys.argv[1:4]\n"
            "for name, directory in (('workspace_write', workspace), ('scratch_write', temporary)):\n"
            "    stage(name)\n"
            "    path = os.path.join(directory, '.sandbox-probe')\n"
            "    with open(path, 'x', encoding='utf-8') as stream: stream.write('ok')\n"
            "    os.unlink(path)\n"
            "stage('host_home_block')\n"
            "try:\n"
            "    with os.scandir(host_home): pass\n"
            "except PermissionError:\n"
            "    pass\n"
            "else:\n"
            "    raise SystemExit(31)\n"
            "stage('network_block')\n"
            "try:\n"
            "    with socket.socket() as connection: connection.bind(('127.0.0.1', 0))\n"
            "except PermissionError:\n"
            "    pass\n"
            "else:\n"
            "    raise SystemExit(32)\n"
        )
        if prj_cache is not None:
            probe += (
                "stage('user_lookup')\n"
                "import pwd\n"
                "pwd.getpwuid(os.getuid())\n"
                "stage('cache_read')\n"
                "tag = os.path.join(sys.argv[4], 'CACHEDIR.TAG')\n"
                "with open(tag, 'rb') as stream: stream.read(1)\n"
                "stage('cache_write_block')\n"
                "try:\n"
                "    with open(tag, 'wb'): pass\n"
                "except PermissionError:\n"
                "    pass\n"
                "else:\n"
                "    raise SystemExit(33)\n"
                "stage('postgresql_socket')\n"
                "directory = os.path.join(temporary, 'pg-socket')\n"
                "os.mkdir(directory)\n"
                "path = os.path.join(directory, 'probe')\n"
                "with socket.socket(socket.AF_UNIX) as server:\n"
                "    server.bind(path)\n"
                "    server.listen(1)\n"
                "    with socket.socket(socket.AF_UNIX) as client: client.connect(path)\n"
                "    connection, _ = server.accept()\n"
                "    connection.close()\n"
                "stage('external_socket_block')\n"
                "try:\n"
                "    with socket.socket(socket.AF_UNIX) as client: client.connect(sys.argv[5])\n"
                "except PermissionError:\n"
                "    pass\n"
                "else:\n"
                "    raise SystemExit(34)\n"
            )
        stage = "initialization"
        try:
            with tempfile.TemporaryDirectory(prefix="workflow-sandbox-probe-" if prj_cache is None else "wpg-",
                                             dir="/private/tmp") as temporary:
                base = Path(temporary).resolve()
                scratch = base / "sandbox"
                scratch.mkdir(mode=0o700)
                root = base / "workspace"
                root.mkdir(mode=0o700)
                argv = [python, "-c", probe, str(root), str(scratch / "tmp"), str(host_home)]
                outside_socket = None
                try:
                    if prj_cache is not None:
                        stage = "external_socket_setup"
                        outside_path = base / "outside-socket"
                        outside_socket = socket.socket(socket.AF_UNIX)
                        outside_socket.bind(str(outside_path))
                        outside_socket.listen(1)
                        argv.extend([str(prj_cache), str(outside_path)])
                    stage = "initialization"
                    command, environment, workdir = self._macos_command(root, ".", argv, scratch, prj_cache=prj_cache)
                    result = _process(command, 10, cwd=workdir, env=environment)
                finally:
                    if outside_socket is not None:
                        outside_socket.close()
        except (OSError, ValueError) as exc:
            result.update(status="unavailable", reason="The macOS isolation probe could not be prepared or cleaned up.")
            result["stderr"] += workspace.redact(f"\n{type(exc).__name__}: {exc}")
        if result["status"] == "passed" and not result["stdout"]:
            return True
        stages = re.findall(r"(?m)^workflow-isolation-stage=([a-z_]+)$", result["stderr"])
        if stages:
            stage = stages[-1]
        if result["status"] == "passed":
            stage = "unexpected_output"
        reason = f"macOS sandbox isolation probe failed at {stage}; the configured test was not started."
        if result.get("reason"):
            reason += " " + result["reason"]
        self._isolation_failure = {**result, "status": "unavailable", "isolation_stage": stage, "reason": reason}
        return False

    def _command(self, root: Path, cwd: str, argv: list[str], *, prj_cache: Path | None = None) -> list[str]:
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
                        "--setenv", "LANG", "C.UTF-8", "--setenv", "PYTHONDONTWRITEBYTECODE", "1"])
        if Path(argv[0]).name == "uv":
            # uv otherwise puts venv symlinks in the test copy, which inventory rejects.
            command.extend(["--setenv", "UV_PROJECT_ENVIRONMENT", "/tmp/uv-venv",
                            "--setenv", "UV_CACHE_DIR", "/tmp/uv-cache"])
        if prj_cache is not None:
            if os.geteuid() == 0:
                # initdb refuses root. Map the caller to a non-root UID only in this namespace.
                command.extend(["--uid", "65534", "--gid", "65534"])
            launcher = Path(__file__).resolve().with_name("prj_backend_check.sh")
            command.extend(["--ro-bind", str(launcher), "/workflow/prj_backend_check.sh",
                            "--ro-bind", str(prj_cache), "/workflow/uv-cache"])
        return [*command, "--", *argv]

    def run(self, root: Path, cwd: str, command: dict[str, Any], timeout: float) -> dict[str, Any]:
        if not self.checked:
            self.checked = True
            if sys.platform == "linux":
                self.executable = shutil.which("bwrap", path=SYSTEM_PATH)
            elif sys.platform == "darwin":
                self.executable = shutil.which("sandbox-exec", path=SYSTEM_PATH)
            if self.executable is None:
                self.error = {
                    "linux": "Linux Bubblewrap isolation is unavailable; host execution is prohibited.",
                    "darwin": "macOS sandbox-exec isolation is unavailable; host execution is prohibited.",
                }.get(sys.platform, "No supported OS sandbox is available; host execution is prohibited.")
            elif sys.platform == "linux":
                probe = _process(self._command(root, ".", ["/bin/true"]), 10)
                if probe["status"] != "passed":
                    self.error = "Bubblewrap namespace isolation could not be initialized."
            elif sys.platform == "darwin" and not self._macos_isolation_ready():
                self.error = "macOS sandbox isolation could not be initialized or failed its access checks."
        if self.error:
            if self._isolation_failure is not None:
                return dict(self._isolation_failure)
            return {"status": "unavailable", "return_code": None, "duration_seconds": 0,
                    "stdout": "", "stderr": "", "reason": self.error}
        prj_check = command["program"] == "prj-backend-check"
        if prj_check:
            cache = Path(os.environ.get("WORKFLOW_PRJ_UV_CACHE", ""))
            if not cache.is_absolute() or not (cache / "CACHEDIR.TAG").is_file():
                return {"status": "unavailable", "return_code": None, "duration_seconds": 0,
                        "stdout": "", "stderr": "", "reason": "WORKFLOW_PRJ_UV_CACHE must point to a prepared offline uv cache."}
            cache = cache.resolve()
            if sys.platform == "darwin":
                if not self._macos_isolation_ready(prj_cache=cache):
                    if self._isolation_failure is not None:
                        return dict(self._isolation_failure)
                    return {"status": "unavailable", "return_code": None, "duration_seconds": 0,
                            "stdout": "", "stderr": "", "reason": "macOS PostgreSQL socket or cache isolation failed its access checks."}
            else:
                sandbox_command = self._command(root, cwd, ["/bin/bash", "/workflow/prj_backend_check.sh"], prj_cache=cache)
        else:
            executable = shutil.which(command["program"], path=SYSTEM_PATH)
            if executable is None:
                return {"status": "unavailable", "return_code": None, "duration_seconds": 0,
                        "stdout": "", "stderr": "", "reason": "Configured test executable is not available on the isolated system PATH."}
            test_argv = [executable, *command["args"]]
        if sys.platform == "darwin":
            # Keep PostgreSQL Unix socket paths below Darwin's 104-byte limit.
            with tempfile.TemporaryDirectory(prefix="wpg-" if prj_check else "workflow-test-sandbox-",
                                             dir="/private/tmp") as temporary:
                scratch = Path(temporary).resolve()
                if prj_check:
                    test_argv = ["/bin/bash", str(scratch.resolve() / "prj_backend_check.sh")]
                sandbox_command, environment, workdir = self._macos_command(
                    root, cwd, test_argv, scratch, prj_cache=cache if prj_check else None)
                result = _process(sandbox_command, timeout, cwd=workdir, env=environment)
        else:
            if not prj_check:
                sandbox_command = self._command(root, cwd, test_argv)
            result = _process(sandbox_command, timeout)
        if result["stderr"].startswith(("bwrap:", "sandbox-exec:")):
            result.update(status="unavailable", reason="The isolated runtime or executable could not be initialized.")
        elif prj_check and result["status"] == "failed" and result["return_code"] == 78:
            result.update(status="unavailable", reason="Offline dependencies or isolated studio_test PostgreSQL could not be prepared.")
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


def allow_failure_publication(config: dict[str, Any], validation: dict[str, Any]) -> bool:
    results = validation.get("tests", {}).get("unit", []) + validation.get("tests", {}).get("e2e", [])
    status, reasons = judge(results)
    return ((config["pr_policy"]["allow_draft_on_failure"] or config["pr_policy"].get("allow_pr_on_failure", False))
            and validation.get("scope_status") == "passed" and validation.get("status") == "failed"
            and status == "failed" and validation.get("errors") == reasons
            and any(result["status"] in ("failed", "timeout", "unavailable") for result in results))


def validate_workspace(candidate: Path, config: dict[str, Any], before: dict[str, Any],
                       config_relative: str, *, executor=None, stop_on_failure=False) -> dict[str, Any]:
    """Verify candidate boundaries then run Unit/E2E checks using frozen policy."""
    environment = {"linux": "linux-bubblewrap", "darwin": "macos-sandbox-exec"}.get(sys.platform, "unsupported")
    validation = {"status": "running", "started_at": _now(), "ended_at": None,
                  "scope_status": "not_run", "tests": {"unit": [], "e2e": []}, "errors": [],
                  "environment": environment, "candidate_sha256": None}
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
        with tempfile.TemporaryDirectory(prefix="workflow-validation-",
                                         dir="/private/tmp" if sys.platform == "darwin" else None) as temporary:
            root = (Path(temporary) / "workspace").resolve()
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
        if exc.status in ("path_violation", "sensitive_content"):
            validation["scope_status"] = "failed"
            if exc.status == "sensitive_content":
                validation["scope_failure_reason"] = exc.status
        validation["errors"].append(workspace.redact(str(exc)))
    except (OSError, ValueError, TypeError):
        validation["status"] = "failed"
        validation["errors"].append("Independent test preparation or result collection failed; details are withheld.")
    finally:
        validation["ended_at"] = _now()
    return validation

"""Portable launcher checks with fake PostgreSQL/uv; no database or model calls."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "launcher requires a POSIX shell")
class LauncherTests(unittest.TestCase):
    def launch(self, platform, exit_code=0):
        with tempfile.TemporaryDirectory(prefix="workflow-launcher-test-") as temporary:
            root = Path(temporary)
            tools = root / "bin"
            tools.mkdir()
            cache = root / "prepared"
            cache.mkdir()
            (cache / "CACHEDIR.TAG").write_text("prepared")
            ledger = root / "calls.jsonl"
            helper = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["LEDGER"], "a") as stream:
    stream.write(json.dumps({"name": name, "args": args, "database": os.environ.get("DATABASE_URL"),
                            "data": os.environ.get("PGDATA"), "venv": os.environ.get("UV_PROJECT_ENVIRONMENT")}) + "\\n")
if name == "uname": print(os.environ["FAKE_PLATFORM"])
elif name == "getent" and os.environ["FAKE_PLATFORM"] == "Darwin": raise SystemExit(99)
elif name == "cp":
    if os.environ["FAKE_PLATFORM"] == "Darwin" and any(arg.startswith("--") for arg in args): raise SystemExit(99)
    raise SystemExit(subprocess.call(["/bin/cp", *args]))
elif name == "uv" and args[0] == "run":
    print("3 passed")
    raise SystemExit(int(os.environ["FAKE_EXIT_CODE"]))
'''
            for name in ("uname", "getent", "cp", "uv", "pg_ctl", "initdb", "createdb"):
                program = tools / name
                program.write_text(helper)
                program.chmod(0o755)
            launcher = Path(__file__).resolve().parents[1] / "prj_backend_check.sh"
            environment = {"PATH": str(tools) + os.pathsep + os.defpath, "HOME": str(root),
                           "WORKFLOW_PRJ_SCRATCH": str(root / "scratch"), "WORKFLOW_PRJ_UV_CACHE": str(cache),
                           "LEDGER": str(ledger), "FAKE_PLATFORM": platform, "FAKE_EXIT_CODE": str(exit_code)}
            result = subprocess.run(["bash", str(launcher)], env=environment, cwd=root,
                                    capture_output=True, text=True, timeout=10)
            calls = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual((root / "scratch/uv-cache/CACHEDIR.TAG").read_text(), "prepared")
            self.assertEqual((cache / "CACHEDIR.TAG").read_text(), "prepared")
            return result, calls

    def test_linux_and_macos_use_private_database_and_offline_dependencies(self):
        for platform in ("Linux", "Darwin"):
            with self.subTest(platform=platform):
                result, calls = self.launch(platform)
                self.assertEqual(result.returncode, 0, result.stderr)
                sync = next(call for call in calls if call["name"] == "uv" and call["args"][0] == "sync")
                for option in ("--offline", "--frozen", "--no-build", "--no-python-downloads"):
                    self.assertIn(option, sync["args"])
                self.assertTrue(sync["venv"].endswith("/scratch/uv-venv"))
                start = next(call for call in calls if call["name"] == "pg_ctl" and call["args"][-1] == "start")
                self.assertIn("listen_addresses=''", " ".join(start["args"]))
                self.assertIn("shared_memory_type=mmap", " ".join(start["args"]))
                check = next(call for call in calls if call["name"] == "uv" and call["args"][0] == "run")
                self.assertIn("postgresql:///studio_test?host=", check["database"])
                self.assertIn("/scratch/pg-socket&user=studio", check["database"])
                self.assertEqual(calls[-1]["args"][-1], "stop")
                if platform == "Darwin":
                    self.assertFalse(any(call["name"] == "getent" for call in calls))

    def test_failed_tests_keep_the_exit_code_and_stop_postgresql(self):
        result, calls = self.launch("Darwin", exit_code=1)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(calls[-1]["args"][-1], "stop")

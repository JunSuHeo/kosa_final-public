"""Opt-in real demo tests and Linux isolation checks; never calls Codex.

WORKFLOW_DEMO_TESTS=1 python3 -B -m unittest discover \
    -s workflow/runtime/tests/integration -p test_demo_validation.py -v
"""

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from workflow.runtime import run, test_runner, workspace


@unittest.skipUnless(os.environ.get("WORKFLOW_DEMO_TESTS") == "1", "real demo tests require explicit opt-in")
class DemoValidationTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parents[4]
        self.config_path = self.repo / "workflow/config/projects/sandbox.json"
        self.config, _ = run._load(self.config_path, self.repo)
        self.temp = tempfile.TemporaryDirectory(prefix="workflow-demo-check-")
        self.addCleanup(self.temp.cleanup)
        self.candidate = Path(self.temp.name) / "candidate"
        self.before = workspace.prepare(self.repo, self.candidate, self.config, self.config_path)
        self.relative = self.config_path.relative_to(self.repo).as_posix()

    def validate(self):
        return test_runner.validate_workspace(self.candidate, self.config, self.before, self.relative)

    def test_actual_unit_and_e2e_commands_pass(self):
        result = self.validate()
        self.assertEqual(result["status"], "passed", result)
        for kind in ("unit", "e2e"):
            self.assertEqual(result["tests"][kind][0]["status"], "passed", result)
            self.assertIn("Ran 4 tests", result["tests"][kind][0]["stderr"])
        self.assertEqual(workspace.inventory(self.candidate), self.before)

    def test_broken_candidate_fails_actual_unit_and_e2e(self):
        source = self.candidate / "sandbox/manual-engine-demo/src/calculator.py"
        source.write_text(source.read_text().replace("return left + right", "return left - right"))
        result = self.validate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["tests"]["unit"][0]["status"], "failed")
        self.assertEqual(result["tests"]["e2e"][0]["status"], "failed")

    @unittest.skipUnless(shutil.which("uv", path=test_runner.SYSTEM_PATH), "uv is not installed")
    def test_uv_run_uses_sandbox_scratch_instead_of_creating_candidate_venv(self):
        unit = self.config["tests"]["unit"][0]
        (self.candidate / unit["cwd"] / "pyproject.toml").write_text(
            '[project]\nname = "workflow-test-fixture"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n'
        )
        lock = test_runner.IsolatedTestProcess().run(
            self.candidate, unit["cwd"], {"program": "uv", "args": ["lock", "--offline"]}, 30
        )
        self.assertEqual(lock["status"], "passed", lock)
        self.before = workspace.inventory(self.candidate)

        unit["command"] = {"program": "uv", "args": [
            "run", "--frozen", "--offline", "python", "-c", "import sys; print(sys.prefix)"
        ]}
        result = self.validate()
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue(result["tests"]["unit"][0]["stdout"].startswith("/tmp/"), result)
        self.assertEqual(workspace.inventory(self.candidate), self.before)

    def test_symlink_in_test_copy_still_blocks_validation(self):
        self.config["tests"]["unit"][0]["command"] = {
            "program": "python3", "args": ["-B", "-c", "from pathlib import Path; Path('link').symlink_to('/tmp')"]
        }
        result = self.validate()
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["scope_status"], "failed", result)
        self.assertTrue(any("Symlink" in error for error in result["errors"]), result)
        self.assertEqual(workspace.inventory(self.candidate), self.before)

    def test_real_missing_program_is_unavailable(self):
        self.config["tests"]["unit"][0]["command"] = {"program": "workflow-missing-test-tool", "args": []}
        result = self.validate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["tests"]["unit"][0]["status"], "unavailable")
        self.assertEqual(result["tests"]["e2e"][0]["status"], "passed")

    def test_real_timeout_and_partial_logs(self):
        self.config["tests"]["unit"][0].update(timeout_seconds=1,
            command={"program": "python3", "args": ["-B", "-c", "import time;print('started',flush=True);time.sleep(30)"]})
        result = self.validate()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["tests"]["unit"][0]["status"], "timeout")
        self.assertIn("started", result["tests"]["unit"][0]["stdout"])

    def test_optional_e2e_is_explicitly_not_run(self):
        self.config["tests"]["e2e"][0].update(required=False, run_if="never", skip_reason="Explicit demo scenario policy.")
        result = self.validate()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["tests"]["e2e"][0]["status"], "not_run")

    def test_isolation_hides_original_files_environment_and_host_network(self):
        code = (
            "import os,pathlib,socket;"
            f"assert not pathlib.Path({str(self.repo)!r}).exists();"
            "assert 'WORKFLOW_TEST_TOKEN' not in os.environ;"
            "assert all(name=='lo' for _,name in socket.if_nameindex());"
            "assert os.environ['HOME']=='/home/test';print('isolated')"
        )
        self.config["tests"]["unit"][0]["command"] = {"program": "python3", "args": ["-B", "-c", code]}
        with patch.dict(os.environ, {"WORKFLOW_TEST_TOKEN": "synthetic-isolation-marker"}):
            result = self.validate()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["tests"]["unit"][0]["stdout"], "isolated\n")

    def test_arguments_are_literal_not_shell_commands(self):
        self.config["tests"]["unit"][0]["command"] = {
            "program": "python3", "args": ["-B", "-c", "import sys;print(sys.argv[1])", "hello; exit 99"]}
        result = self.validate()
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["tests"]["unit"][0]["stdout"], "hello; exit 99\n")

    def test_empty_unittest_discovery_is_rejected(self):
        self.config["tests"]["unit"][0]["command"] = {
            "program": "python3", "args": ["-B", "-m", "unittest", "discover", "-s", ".", "-p", "no_matches_*.py"]}
        result = self.validate()
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["tests"]["unit"][0]["status"], "failed")
        # Python 3.14 returns 5; older unittest versions return 0 for no tests.
        self.assertIn(result["tests"]["unit"][0]["return_code"], (0, 5))

    def test_exit_zero_with_zero_test_report_is_rejected(self):
        self.config["tests"]["unit"][0]["command"] = {
            "program": "python3", "args": ["-B", "-c", "print('Ran 0 tests in 0.000s')"]}
        result = self.validate()
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["tests"]["unit"][0]["status"], "failed")
        self.assertEqual(result["tests"]["unit"][0]["return_code"], 0)


if __name__ == "__main__":
    unittest.main()

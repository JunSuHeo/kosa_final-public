"""Opt-in PostgreSQL backend checks on Linux/macOS; never invokes Codex.

Prepare WORKFLOW_PRJ_UV_CACHE from the trusted base lock file first, then run:
WORKFLOW_PRJ_TESTS=1 python3 -B -m unittest discover \
    -s workflow/runtime/tests/integration -p test_prj_validation.py -v
"""

import os
from pathlib import Path
import tempfile
import unittest

from workflow.runtime import run, test_runner, workspace


@unittest.skipUnless(os.environ.get("WORKFLOW_PRJ_TESTS") == "1", "backend integration requires explicit opt-in")
class PRJValidationTests(unittest.TestCase):
    def setUp(self):
        self.repo = Path(__file__).resolve().parents[4]
        config_path = self.repo / "workflow/config/projects/prj.json"
        self.config, _ = run._load(config_path, self.repo)
        temporary = tempfile.TemporaryDirectory(prefix="workflow-prj-check-")
        self.addCleanup(temporary.cleanup)
        self.candidate = Path(temporary.name) / "candidate"
        self.before = workspace.prepare(self.repo, self.candidate, self.config, config_path)
        self.relative = config_path.relative_to(self.repo).as_posix()

    def test_backend_passes_with_isolated_postgresql(self):
        check = self.config["tests"]["unit"][0]
        self.assertTrue(check["required"])
        self.assertEqual(check["run_if"], "always")
        result = test_runner.validate_workspace(self.candidate, self.config, self.before, self.relative)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["tests"]["unit"][0]["status"], "passed", result)
        self.assertEqual(workspace.inventory(self.candidate), self.before)

    def test_broken_backend_is_a_failed_check(self):
        source = self.candidate / "PRJ/backend/app/main.py"
        source.write_text(source.read_text() + "\ndef malformed(:\n", encoding="utf-8")
        result = test_runner.validate_workspace(self.candidate, self.config, self.before, self.relative)
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["tests"]["unit"][0]["status"], "failed", result)

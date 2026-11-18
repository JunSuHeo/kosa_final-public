"""Opt-in real CLI smoke test; excluded from ordinary Unit Test discovery.

Requires WORKFLOW_CODEX_SMOKE_CONFIG=/absolute/path/to/ready/project.json and
WORKFLOW_CODEX_SMOKE_REPO=/absolute/path/to/repository, plus existing Codex login.
Setting these variables explicitly authorizes a real, possibly billable call.
No credentials are requested or recorded. This test never changes the checkout.
"""

import os
from pathlib import Path
import tempfile
import unittest

from workflow.runtime.run import execute_request


@unittest.skipUnless(os.environ.get("WORKFLOW_CODEX_SMOKE_CONFIG") and os.environ.get("WORKFLOW_CODEX_SMOKE_REPO"),
                     "real Codex smoke test requires explicit config and repository opt-in")
class CodexSmokeTest(unittest.TestCase):
    def test_real_codex_read_only_request(self):
        with tempfile.TemporaryDirectory(prefix="workflow-smoke-") as results:
            report = execute_request(
                Path(os.environ["WORKFLOW_CODEX_SMOKE_CONFIG"]),
                "Read the supplied design context and describe it briefly. Do not change any files or run product tests.",
                Path(os.environ["WORKFLOW_CODEX_SMOKE_REPO"]), Path(results),
            )
            self.assertEqual(report["final_status"], "completed", report["errors"])
            self.assertEqual(report["validation_status"], "passed")
            self.assertEqual(report["codex_status"], "succeeded")
            self.assertEqual(report["changed_files"], [])
            self.assertTrue(Path(report["result_path"]).is_file())


if __name__ == "__main__":
    unittest.main()

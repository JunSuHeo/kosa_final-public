"""Opt-in CLI integration with real demo tests, fake Codex and virtual GitHub.

WORKFLOW_DEMO_TESTS=1 python3 -B -m unittest discover \
    -s workflow/runtime/tests/integration -p test_demo_workflow.py -v
"""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from workflow.runtime import git_tools, run, workspace
from workflow.runtime.github_adapter import GitHubCLI


class DemoWorker:
    def __init__(self, project_root, broken=False):
        self.project_root = project_root
        self.broken = broken

    def preflight(self, settings):
        return {"adapter": "offline_fake", "version": settings["version"], "platform": "linux"}

    def execute(self, prompt, destination, settings):
        project = destination / self.project_root
        source = project / "src/calculator.py"
        expression = "return left - right" if self.broken else "return sum((left, right))"
        source.write_text(source.read_text(encoding="utf-8").replace("return left + right", expression), encoding="utf-8")
        design = project / "specs/design.md"
        design.write_text(design.read_text(encoding="utf-8") + "\nAddition keeps the integer contract after the implementation refactor.\n", encoding="utf-8")
        return 0


@unittest.skipUnless(os.environ.get("WORKFLOW_DEMO_TESTS") == "1", "real demo tests require explicit opt-in")
class DemoWorkflowTests(unittest.TestCase):
    def setUp(self):
        source_repo = Path(__file__).resolve().parents[4]
        self.temp = tempfile.TemporaryDirectory(prefix="workflow-integrated-demo-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.config_path = self.root / "workflow/config/projects/demo.json"
        self.config_path.parent.mkdir(parents=True)
        self.config = json.loads((source_repo / "workflow/config/projects/sandbox.json").read_text(encoding="utf-8"))
        self.config["project_id"] = "temp-calculator"
        self.config["repository"].update(owner="example", name="temp-workflow")
        self.config["publishing"]["commit_author"] = {"name": "Local Test", "email": "test@example.test"}
        self.project_root = self.config["project_root"]
        self.source_demo = source_repo / self.project_root
        self.source_before = workspace.inventory(self.source_demo)
        shutil.copytree(self.source_demo, self.root / self.project_root,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".venv"))
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.git = git_tools.Git(self.root)
        self.git.run("init", "--quiet", "--template=", "-b", "main")
        self.git.run("config", "user.name", "Local Test")
        self.git.run("config", "user.email", "test@example.test")
        self.git.run("add", ".")
        self.git.run("commit", "--quiet", "-m", "local fixture baseline")
        self.git.run("remote", "add", "origin", "https://github.com/example/temp-workflow.git")
        self.head = self.git.text("rev-parse", "HEAD")
        self.before = self.git.run("status", "--porcelain")

    def execute_cli(self, broken=False):
        original = git_tools.Git.run

        def local_only(git, *args, **kwargs):
            if args[0] in ("push", "ls-remote") or (args[0] == "fetch" and any(
                    str(arg).startswith(("https:", "ssh:", "git@")) for arg in args)):
                raise AssertionError("Real remote operations forbidden in demo integration")
            return original(git, *args, **kwargs)

        output = io.StringIO()
        with patch.object(run, "CodexCLI", return_value=DemoWorker(self.project_root, broken)), \
                patch.object(git_tools.Git, "run", local_only), \
                patch.object(GitHubCLI, "preflight", side_effect=AssertionError("Real gh forbidden")), \
                patch("workflow.runtime.publish.authenticated_git", side_effect=AssertionError("Real credentials forbidden")), \
                contextlib.redirect_stdout(output):
            code = run.main(["--config", str(self.config_path), "--task", "Refactor addition and update its design",
                             "--repo-root", str(self.root), "--results-dir", str(Path(self.temp.name) / "runs")])
        result = json.loads(output.getvalue())
        self.assertEqual(self.git.text("rev-parse", "HEAD"), self.head)
        self.assertEqual(self.git.run("status", "--porcelain"), self.before)
        self.assertEqual(workspace.inventory(self.source_demo), self.source_before)
        self.assertIn("return left + right", (self.root / self.project_root / "src/calculator.py").read_text())
        return code, result

    def test_actual_cli_and_unit_e2e_reach_simulated_pr(self):
        code, result = self.execute_cli()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["workflow_status"], "completed_simulation", result)
        self.assertEqual(len(result["changed_files"]), 2)
        for kind in ("unit", "e2e"):
            test = result["validation"]["tests"][kind][0]
            self.assertEqual(test["status"], "passed", test)
            self.assertIn("Ran 4 tests", test["stderr"])
        publication = result["publication"]
        self.assertEqual(publication["status"], "simulated")
        self.assertFalse(publication["attempted"])
        self.assertIsNone(publication["pr_url"])
        self.assertIn("pr_create", [request["operation"] for request in publication["simulation"]["github_requests"]])
        self.assertEqual(json.loads(Path(result["workflow_result_path"]).read_text()), result)

    def test_actual_unit_failure_prevents_e2e_and_publication(self):
        code, result = self.execute_cli(broken=True)
        self.assertEqual(code, 1, result)
        self.assertEqual(result["validation"]["tests"]["unit"][0]["status"], "failed")
        self.assertEqual(result["validation"]["tests"]["e2e"][0]["status"], "not_run")
        self.assertEqual(result["publication"]["status"], "not_run")
        self.assertFalse(result["publication"]["attempted"])


if __name__ == "__main__":
    unittest.main()

"""End-to-end local fixtures; Codex/test processes and all remote operations mocked."""

import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from workflow.runtime import evidence, git_tools, orchestrator, publish, run
from workflow.runtime.codex_adapter import ExecutionError
from workflow.runtime.github_adapter import GitHubCLI
from workflow.runtime.simulated_github import SimulatedGitHubCLI, SimulatedNetworkGit
from workflow.runtime.tests import test_publish as fixtures


class TraceTests(fixtures.Tests):
    def __init__(self, status="passed"):
        self.status = status
        self.calls = []

    def run(self, root, cwd, command, timeout):
        self.calls.append(command)
        result = super().run(root, cwd, command, timeout)
        result.update(status=self.status, return_code=0 if self.status == "passed" else 1)
        return result


@unittest.skipUnless(fixtures.shutil.which("git") and fixtures.os.name == "posix", "local integration fixtures require Linux Git")
class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PublishTests(methodName="test_valid_prepare_creates_only_isolated_commit_and_preview")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.test_process = TraceTests()
        self.github = SimulatedGitHubCLI()

    def execute(self, worker=None, **kwargs):
        # Real Git may operate locally, but a URL transport, push, or gh call is
        # forbidden even if an implementation regression reaches that boundary.
        original = git_tools.Git.run
        def local_only(git, *args, **options):
            if args[0] in ("push", "ls-remote") or (args[0] == "fetch" and any(str(arg).startswith(("https:", "ssh:", "git@")) for arg in args)):
                raise AssertionError("Real Git network operation forbidden in integration tests")
            return original(git, *args, **options)
        with patch.object(git_tools.Git, "run", local_only), patch.object(GitHubCLI, "preflight", side_effect=AssertionError("Real gh forbidden")), patch("workflow.runtime.publish.authenticated_git", side_effect=AssertionError("Real credential helper forbidden")):
            return orchestrator.execute_workflow(self.fixture.config_path, "Update sample calculation",
                self.fixture.root, self.fixture.results, adapter=worker or fixtures.Worker(),
                test_executor=self.test_process, simulation_github=self.github, **kwargs)

    def assert_publication_not_run(self, result):
        self.assertEqual(result["publication"]["status"], "not_run")
        self.assertEqual(self.github.calls, [])
        self.assertEqual(next(stage["status"] for stage in result["stages"] if stage["name"] == "publication"), "not_run")

    def test_complete_default_flow_reaches_simulated_pr_creation(self):
        before = self.fixture.git.run("status", "--porcelain")
        result = self.execute()
        self.assertEqual(result["workflow_status"], "completed_simulation", result)
        self.assertEqual(result["final_status"], "completed")
        self.assertEqual(result["workflow_mode"], "simulate")
        self.assertEqual(result["execution_id"], result["run_id"])
        self.assertEqual(result["project_name"], "sample")
        self.assertEqual(result["changed_files"], ["sample/src/main.py"])
        self.assertTrue(all(stage["status"] == "passed" for stage in result["stages"]))
        self.assertEqual([c["operation"] for c in self.github.calls].count("pr_create"), 1)
        self.assertEqual(result["publication"]["status"], "simulated")
        self.assertFalse(result["publication"]["attempted"])
        self.assertIsNone(result["publication"]["pr_url"])
        directory = Path(result["result_path"]).parent
        self.assertTrue((directory / "publish.simulated.json").is_file())
        self.assertFalse((directory / "publish.json").exists())
        self.assertEqual(json.loads(Path(result["workflow_result_path"]).read_text()), result)
        self.assertEqual(json.loads(Path(result["result_path"]).read_text())["final_status"], "completed")
        self.assertNotIn("publication", json.loads(Path(result["result_path"]).read_text()))
        self.assertEqual(self.fixture.git.run("status", "--porcelain"), before)
        self.assertEqual(self.fixture.git.text("rev-parse", "HEAD"), self.fixture.head)
        self.assertEqual((self.fixture.root / "sample/src/main.py").read_text(), "value = 1\n")

    def test_configuration_error_stops_before_worker_tests_and_publication(self):
        del self.fixture.config["base_branch"]
        self.fixture.write_config()
        worker = fixtures.Worker()
        with patch.object(worker, "execute") as coding:
            result = self.execute(worker)
        self.assertEqual(result["final_status"], "config_error")
        self.assertEqual(self.test_process.calls, [])
        coding.assert_not_called()
        self.assert_publication_not_run(result)

    def test_codex_failure_stops_collection_tests_and_publication(self):
        worker = fixtures.Worker()
        with patch.object(worker, "execute", side_effect=ExecutionError("codex_failed", "Controlled coding failure")):
            result = self.execute(worker)
        self.assertEqual(result["final_status"], "codex_failed")
        self.assertEqual(self.test_process.calls, [])
        self.assertEqual(next(s["status"] for s in result["stages"] if s["name"] == "collect"), "not_run")
        self.assert_publication_not_run(result)

    def test_missing_codex_execution_result_is_not_success(self):
        worker = fixtures.Worker()
        with patch.object(worker, "execute", return_value=None):
            result = self.execute(worker)
        self.assertEqual(result["final_status"], "codex_failed")
        self.assertEqual(self.test_process.calls, [])
        self.assert_publication_not_run(result)

    def test_missing_candidate_workspace_stops_validation(self):
        worker = fixtures.Worker(lambda root: fixtures.shutil.rmtree(root))
        result = self.execute(worker)
        self.assertEqual(result["final_status"], "path_violation")
        self.assertEqual(self.test_process.calls, [])
        self.assert_publication_not_run(result)

    def test_unapproved_file_blocks_testing_and_publication(self):
        def action(root):
            (root / "outside").mkdir()
            (root / "outside/file.py").write_text("outside scope\n")
        result = self.execute(fixtures.Worker(action))
        self.assertEqual(result["final_status"], "path_violation")
        self.assertEqual(self.test_process.calls, [])
        self.assert_publication_not_run(result)

    def test_unit_failure_stops_e2e_and_publication(self):
        self.test_process.status = "failed"
        result = self.execute()
        self.assertEqual(result["final_status"], "validation_failed")
        self.assertEqual(len(self.test_process.calls), 1)
        self.assertEqual(result["validation"]["tests"]["unit"][0]["status"], "failed")
        self.assertEqual(result["validation"]["tests"]["e2e"][0]["status"], "not_run")
        self.assert_publication_not_run(result)

    def test_timeout_stops_remaining_tests_and_publication(self):
        self.test_process.status = "timeout"
        result = self.execute()
        self.assertEqual(result["validation_status"], "failed")
        self.assertEqual(len(self.test_process.calls), 1)
        self.assert_publication_not_run(result)

    def test_failure_policy_reaches_simulated_draft_pr_and_preserves_skipped_checks(self):
        self.fixture.config["pr_policy"]["allow_draft_on_failure"] = True
        self.fixture.config["publishing"]["draft"] = False
        self.fixture.write_config()
        for status in ("failed", "timeout", "unavailable"):
            with self.subTest(status=status):
                self.github = SimulatedGitHubCLI()
                self.test_process = TraceTests(status)
                result = self.execute()
                self.assertEqual(result["workflow_status"], "completed_simulation", result)
                self.assertEqual(result["final_status"], "completed")
                self.assertEqual(result["validation_status"], "failed")
                self.assertEqual(len(self.test_process.calls), 1)
                self.assertEqual(result["validation"]["tests"]["unit"][0]["status"], status)
                self.assertEqual(result["validation"]["tests"]["e2e"][0]["status"], "not_run")
                self.assertTrue(next(call["draft"] for call in self.github.calls if call["operation"] == "pr_create"))
                sealed = json.loads(Path(result["result_path"]).read_text())
                self.assertEqual(sealed["final_status"], "validation_failed")
                self.assertTrue(sealed["errors"])

    def test_failure_policy_still_blocks_a_test_that_changes_input_files(self):
        self.fixture.config["pr_policy"]["allow_draft_on_failure"] = True
        self.fixture.write_config()
        original = self.test_process.run
        def mutate_input(root, *args):
            (root / "sample/src/main.py").write_text("modified during testing\n")
            return original(root, *args)
        with patch.object(self.test_process, "run", side_effect=mutate_input):
            result = self.execute()
        self.assertEqual(result["final_status"], "validation_failed")
        self.assert_publication_not_run(result)

    def test_optional_e2e_skip_is_legitimate_and_visible(self):
        self.fixture.config["tests"]["e2e"][0].update(required=False, run_if="never", skip_reason="Optional scenario not applicable")
        self.fixture.write_config()
        result = self.execute()
        self.assertEqual(result["workflow_status"], "completed_simulation", result)
        self.assertEqual(len(self.test_process.calls), 1)
        self.assertEqual(result["validation"]["tests"]["e2e"][0]["status"], "not_run")
        body = (Path(result["result_path"]).parent / "publication.simulated/pr-body.md").read_text()
        self.assertIn("e2e/e2e: not_run", body)

    def test_no_git_changes_block_before_simulated_authentication(self):
        result = self.execute(fixtures.Worker(lambda root: None))
        self.assertEqual(result["final_status"], "publication_failed")
        self.assertEqual(self.github.calls, [])
        self.assertIn("no_changes", str(result["errors"]))

    def test_missing_publishing_policy_blocks(self):
        del self.fixture.config["publishing"]
        self.fixture.write_config()
        result = self.execute()
        self.assertEqual(result["final_status"], "publication_failed")
        self.assertEqual(self.github.calls, [])

    def test_local_git_failure_blocks_before_mock_network(self):
        with patch("workflow.runtime.publish.prepare_git", side_effect=ExecutionError("git_failed", "Controlled Git failure")):
            result = self.execute()
        self.assertEqual(result["final_status"], "publication_failed")
        self.assertEqual(self.github.calls, [])

    def test_missing_simulated_authentication_has_no_push_or_pr(self):
        self.github = SimulatedGitHubCLI(authenticated=False)
        result = self.execute()
        self.assertEqual(result["final_status"], "publication_failed")
        self.assertIn("authentication_failed", str(result["errors"]))
        self.assertEqual([c["operation"] for c in self.github.calls], ["authentication"])
        self.assertFalse(result["publication"]["simulated_attempted"])

    def test_simulated_push_failure_stops_before_pr_creation(self):
        git = SimulatedNetworkGit("main", self.fixture.head)
        original = git.run
        def fail_push(*args):
            if args[0] == "push":
                git.calls.append(list(args))
                raise ExecutionError("git_failed", "Controlled simulated push failure")
            return original(*args)
        with patch.object(git, "run", side_effect=fail_push):
            result = self.execute(simulation_git=git)
        self.assertEqual(result["final_status"], "publication_failed")
        self.assertEqual(result["publication"]["status"], "simulation_failed")
        self.assertFalse(result["publication"]["attempted"])
        self.assertNotIn("pr_create", [c["operation"] for c in self.github.calls])
        saved = json.loads(Path(result["workflow_result_path"]).read_text())
        self.assertEqual(saved["publication"]["simulation"]["git_transport_requests"][-1][0], "push")

    def test_simulated_pr_failure_is_saved_without_real_publication(self):
        with patch.object(self.github, "create_pr", side_effect=ExecutionError("pr_failed", "Controlled simulated PR failure")):
            result = self.execute()
        self.assertEqual(result["final_status"], "publication_failed")
        self.assertEqual(result["publication"]["status"], "simulation_failed")
        self.assertFalse(result["publication"]["attempted"])
        self.assertIsNone(result["publication"]["pr_url"])
        self.assertIn("pr_failed", str(result["errors"]))

    def test_missing_sealed_execution_result_blocks_before_simulated_authentication(self):
        original = publish.publish
        def remove_evidence(result_path, *args, **kwargs):
            result_path.unlink()
            return original(result_path, *args, **kwargs)
        with patch("workflow.runtime.publish.publish", side_effect=remove_evidence):
            result = self.execute()
        self.assertEqual(result["final_status"], "publication_failed")
        self.assertEqual(result["publication"]["status"], "blocked")
        self.assertEqual(self.github.calls, [])

    def test_original_uncommitted_changes_are_preserved_and_not_published(self):
        (self.fixture.root / "sample/src/main.py").write_text("user_value=7\n")
        before = self.fixture.git.run("status", "--porcelain")
        result = self.execute()
        self.assertEqual(result["final_status"], "publication_failed")
        self.assertIn("user_changes", str(result["errors"]))
        self.assertEqual(self.fixture.git.run("status", "--porcelain"), before)
        self.assertEqual((self.fixture.root / "sample/src/main.py").read_text(), "user_value=7\n")

    def test_simulated_journal_is_never_reused_as_real_publication(self):
        result = self.execute()
        prepared = publish.publish(Path(result["result_path"]), self.fixture.config_path, self.fixture.root)
        self.assertEqual(prepared["status"], "prepared", prepared)
        self.assertFalse(prepared["attempted"])
        self.assertIsNone(prepared["pr_url"])

    def test_workflow_save_failure_is_not_reported_as_success(self):
        original = evidence.save_json
        def fail_workflow(directory, name, value):
            if name == "workflow.json":
                raise OSError("Synthetic save failure")
            return original(directory, name, value)
        with patch("workflow.runtime.evidence.save_json", side_effect=fail_workflow):
            result = self.execute()
        self.assertEqual(result["final_status"], "result_collection_failed")
        self.assertIsNone(result["workflow_result_path"])


class SafetyTests(unittest.TestCase):
    def test_default_cli_is_simulation_and_real_requires_explicit_selection(self):
        self.assertEqual(run.parser().parse_args(["--config", "a", "--task", "task"]).publish_mode, "simulate")
        self.assertEqual(run.parser().parse_args(["--config", "a", "--task", "task", "--publish-mode", "real"]).publish_mode, "real")
        with patch("workflow.runtime.orchestrator.execute_workflow", return_value={"final_status": "completed"}) as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run.main(["--config", "a", "--task", "task"]), 0)
        self.assertEqual(call.call_args.kwargs["publish_mode"], "simulate")

    def test_real_adapters_cannot_be_injected_into_simulation(self):
        with patch.object(GitHubCLI, "preflight") as remote:
            result = publish.publish(Path("result.json"), Path("config.json"), Path.cwd(), simulate=True, github=GitHubCLI())
        self.assertEqual(result["status"], "blocked")
        remote.assert_not_called()

    def test_simulation_and_real_execute_are_mutually_exclusive(self):
        with patch("workflow.runtime.publish.authenticated_git") as credentials:
            result = publish.publish(Path("result.json"), Path("config.json"), Path.cwd(), simulate=True, execute=True)
        self.assertEqual(result["status"], "blocked")
        credentials.assert_not_called()

    def test_simulated_transport_rejects_unknown_operations(self):
        git = SimulatedNetworkGit("main", "a" * 40)
        with self.assertRaises(ExecutionError):
            git.run("fetch", "https://github.com/example/repo")


if __name__ == "__main__":
    unittest.main()

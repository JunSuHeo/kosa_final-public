"""Hermetic local Git fixtures and mocked GitHub. No network, Codex or real push."""

import copy
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from workflow.runtime import evidence, git_tools, github_adapter, publish, run
from workflow.runtime.codex_adapter import ExecutionError, restricted_environment


class Worker:
    def __init__(self, action=None):
        self.action = action

    def preflight(self, settings):
        return {"adapter": "offline_fake", "version": settings["version"], "platform": "linux"}

    def execute(self, prompt, destination, settings):
        if self.action:
            self.action(destination)
        else:
            (destination / "sample/src/main.py").write_text("value = 2\n")
        return 0


class Tests:
    def run(self, root, cwd, command, timeout):
        return {"status": "passed", "return_code": 0, "duration_seconds": 0.1,
                "stdout": "", "stderr": "Ran 1 test\nOK\n", "reason": None}


class NetworkGit:
    def __init__(self, base, failure=None, collision=False):
        self.base, self.failure, self.collision = base, failure, collision
        self.calls = []

    def run(self, *args):
        self.calls.append(args)
        if args[0] == "ls-remote":
            if args[-1] == "refs/heads/main":
                return (self.base + "\trefs/heads/main\n").encode()
            return b"deadbeef\tbranch\n" if self.collision else b""
        if args[0] == "push" and self.failure:
            raise self.failure
        return b""


class GitHub:
    executable = "/fake/gh"

    def __init__(self, failure=None, lost_response=False):
        self.failure, self.lost_response = failure, lost_response
        self.prs = []
        self.calls = []

    def preflight(self, cwd):
        self.calls.append("auth")
        if self.failure == "auth":
            raise ExecutionError("authentication_failed", "Authentication is unavailable.")

    def check_repository(self, repo, branch, base, cwd):
        self.calls.append("permissions")

    def find_pr(self, repo, branch, cwd):
        self.calls.append("find")
        return self.prs

    def create_pr(self, repo, base, head, title, body_file, draft, cwd):
        self.calls.append("create")
        if self.failure == "pr":
            raise ExecutionError("pr_failed", "Synthetic PR failure.")
        self.prs = [{"number": 1, "url": "https://github.com/" + repo + "/pull/1",
                     "baseRefName": base, "headRefOid": git_tools.Git(cwd).text("rev-parse", "refs/heads/" + head),
                     "state": "OPEN", "body": body_file.read_text()}]
        if self.lost_response:
            raise ExecutionError("pr_failed", "Response was lost after creation.")


@unittest.skipUnless(shutil.which("git") and os.name == "posix", "local Git publishing fixtures require Linux Git")
class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workflow-publish-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "repo"
        for path in ("sample/src", "sample/docs", "sample/tests", "workflow/config/projects"):
            (self.root / path).mkdir(parents=True, exist_ok=True)
        (self.root / "sample/src/main.py").write_text("value = 1\n")
        (self.root / "sample/docs/design.md").write_text("# Contract\n")
        (self.root / "sample/tests/check.py").write_text("# Trusted test fixture\n")
        self.config_path = self.root / "workflow/config/projects/sample.json"
        self.config = {
            "schema_version": 1, "configuration_status": "ready", "project_id": "sample",
            "repository": {"provider": "github", "owner": "example", "name": "sample"},
            "base_branch": "main", "project_root": "sample",
            "allowed_paths": ["sample/src", "sample/docs", "sample/tests"],
            "design_documents": ["sample/docs/design.md"],
            "tests": {kind: [{"id": kind, "required": True, "cwd": "sample/tests",
                              "command": {"program": "offline-tests", "args": [kind]}}] for kind in ("unit", "e2e")},
            "pr_policy": {"target_branch": "main", "allow_draft_on_failure": False,
                          "require_human_approval": True, "allow_auto_merge": False},
            "execution": {"instructions": [], "environment": {"platform": "linux", "required_programs": []},
                          "codex": {"version": "1.2.3", "model": "fake", "timeout_seconds": 10}},
            "publishing": {"remote": "origin", "branch_template": "ai/{project_id}/{run_id}", "draft": True,
                           "commit_author": {"name": "Test Author", "email": "test@example.test"}},
        }
        self.write_config()
        self.git = git_tools.Git(self.root)
        self.git.run("init", "--quiet", "--template=", "-b", "main")
        self.git.run("config", "user.name", "Test Author")
        self.git.run("config", "user.email", "test@example.test")
        self.git.run("add", ".")
        self.git.run("commit", "--quiet", "-m", "local test baseline")
        self.git.run("remote", "add", "origin", "https://github.com/example/sample.git")
        self.head = self.git.text("rev-parse", "HEAD")
        self.results = self.base / "runs"
        self.generate()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config))

    def generate(self, worker=None):
        self.report = run.execute_request(self.config_path, "Improve the sample", self.root, self.results,
                                          adapter=worker or Worker(), test_executor=Tests())
        self.assertEqual(self.report["final_status"], "completed", self.report)
        self.result_path = Path(self.report["result_path"])

    def change_report(self, action):
        action(self.report)
        run._save(self.result_path.parent, self.report)

    def perform(self, **kwargs):
        return publish.publish(self.result_path, self.config_path, self.root, **kwargs)

    def test_valid_prepare_creates_only_isolated_commit_and_preview(self):
        original_status = self.git.run("status", "--porcelain")
        result = self.perform()
        self.assertEqual(result["status"], "prepared", result)
        self.assertTrue(result["local_eligible"])
        self.assertFalse(result["publishable"])
        self.assertFalse(result["attempted"])
        isolated = git_tools.Git(self.result_path.parent / "publication/git")
        self.assertEqual(isolated.text("diff", "--name-only", self.head, result["commit_sha"]), "sample/src/main.py")
        self.assertEqual(self.git.text("rev-parse", "HEAD"), self.head)
        self.assertEqual(self.git.run("status", "--porcelain"), original_status)
        self.assertEqual(json.loads((self.result_path.parent / "publish.json").read_text()), result)
        self.assertEqual(json.loads(self.result_path.read_text()), self.report)

    def test_failed_missing_or_timed_out_required_tests_block(self):
        for status in ("failed", "not_run", "unavailable", "timeout"):
            with self.subTest(status=status):
                self.generate()
                self.change_report(lambda r: r["validation"]["tests"]["unit"][0].update(status=status))
                self.assertEqual(self.perform()["status"], "blocked")

    def test_failed_final_validation_blocks(self):
        self.change_report(lambda r: r.update(validation_status="failed"))
        self.assertEqual(self.perform()["status"], "blocked")

    def test_missing_test_evidence_blocks(self):
        self.change_report(lambda r: r["validation"]["tests"].update(e2e=[]))
        self.assertEqual(self.perform()["status"], "blocked")

    def test_optional_policy_skip_is_visible_in_pr_and_does_not_block_required_pass(self):
        self.config["tests"]["e2e"][0].update(required=False, run_if="never", skip_reason="Explicit project policy")
        self.write_config()
        self.generate()
        result = self.perform()
        self.assertEqual(result["status"], "prepared", result)
        body = (self.result_path.parent / "publication/pr-body.md").read_text()
        self.assertIn("e2e/e2e: not_run", body)
        self.assertIn("Explicit project policy", body)

    def test_passed_test_with_bad_exit_code_blocks(self):
        self.change_report(lambda r: r["validation"]["tests"]["unit"][0].update(return_code=1))
        self.assertEqual(self.perform()["status"], "blocked")

    def test_missing_legacy_checksum_and_corrupt_result_block(self):
        (self.result_path.parent / "result.sha256").unlink()
        self.assertEqual(self.perform()["status"], "blocked")
        self.generate()
        self.result_path.write_text("invalid JSON")
        self.assertEqual(self.perform()["status"], "blocked")

    def test_baseline_tamper_blocks(self):
        baseline = self.result_path.parent / "baseline.json"
        baseline.write_text("{}")
        self.assertEqual(self.perform()["status"], "blocked")

    def test_corrupt_publication_history_is_not_replaced_or_retried(self):
        self.perform()
        journal = self.result_path.parent / "publish.json"
        journal.write_text('{"attempted":true,')
        with patch("workflow.runtime.publish.authenticated_git") as connect:
            result = self.perform(execute=True, github=GitHub())
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(journal.read_text(), '{"attempted":true,')
        connect.assert_not_called()

    def test_missing_result_blocks(self):
        self.result_path.unlink()
        self.assertEqual(self.perform()["status"], "blocked")

    def test_outside_path_and_candidate_tamper_block(self):
        candidate = Path(self.report["workspace_path"])
        (candidate / "outside").mkdir()
        (candidate / "outside/file.py").write_text("value=3\n")
        self.assertEqual(self.perform()["status"], "blocked")
        self.generate()
        (Path(self.report["workspace_path"]) / "sample/src/main.py").write_text("value=4\n")
        self.assertEqual(self.perform()["status"], "blocked")

    def test_no_changes_blocks(self):
        self.generate(Worker(lambda root: None))
        self.assertEqual(self.perform()["status"], "blocked")

    def test_user_changes_in_tested_scope_cannot_be_committed(self):
        (self.root / "sample/src/main.py").write_text("user_value=8\n")
        self.generate()
        result = self.perform()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("user_changes", str(result["blocked_reasons"]))
        self.assertEqual((self.root / "sample/src/main.py").read_text(), "user_value=8\n")

    def test_untracked_user_project_file_blocks(self):
        (self.root / "sample/src/user.py").write_text("user_value=8\n")
        self.generate()
        self.assertEqual(self.perform()["status"], "blocked")

    def test_unrelated_user_changes_are_preserved_and_not_staged(self):
        (self.root / "unrelated.txt").write_text("user work\n")
        self.generate()
        before = self.git.run("status", "--porcelain")
        result = self.perform()
        self.assertEqual(result["status"], "prepared", result)
        self.assertEqual(self.git.run("status", "--porcelain"), before)
        self.assertEqual((self.root / "unrelated.txt").read_text(), "user work\n")

    def test_additions_and_deletions_are_exactly_staged(self):
        def action(root):
            (root / "sample/src/main.py").unlink()
            (root / "sample/src/new.py").write_text("value=3\n")
        self.generate(Worker(action))
        result = self.perform()
        self.assertEqual(result["status"], "prepared", result)
        isolated = git_tools.Git(self.result_path.parent / "publication/git")
        diff = isolated.text("diff", "--name-status", "--no-renames", self.head, result["commit_sha"])
        self.assertIn("D\tsample/src/main.py", diff)
        self.assertIn("A\tsample/src/new.py", diff)

    def test_branch_and_pr_body_use_report_and_real_statuses(self):
        branch = publish.branch_name(self.config, self.report["run_id"])
        self.assertEqual(branch, "ai/sample/" + self.report["run_id"])
        title, body = publish.pr_text(self.config, self.report, 123)
        for text in ("Improve the sample", "sample/src/main.py", "unit/unit: passed", "e2e/e2e: passed", self.report["run_id"], "#123"):
            self.assertIn(text, body)
        self.assertIn("sample", title)
        modified = copy.deepcopy(self.report)
        modified["validation"]["tests"]["e2e"][0].update(status="not_run", reason="Policy skip")
        body = publish.pr_text(self.config, modified)[1]
        self.assertIn("e2e/e2e: not_run", body)
        self.assertIn("Policy skip", body)

    def test_authentication_failure_has_no_push(self):
        gh = GitHub(failure="auth")
        result = self.perform(execute=True, github=gh)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["attempted"])
        self.assertEqual(gh.calls, ["auth"])

    def test_authentication_can_be_fixed_before_first_external_attempt(self):
        first = self.perform(execute=True, github=GitHub(failure="auth"))
        with patch("workflow.runtime.publish.authenticated_git", return_value=NetworkGit(self.head)):
            second = self.perform(execute=True, github=GitHub())
        self.assertEqual(second["status"], "published", second)
        self.assertEqual(first["commit_sha"], second["commit_sha"])

    def test_remote_identity_and_source_base_mismatch_block(self):
        self.git.run("remote", "set-url", "origin", "https://github.com/other/repo.git")
        self.assertEqual(self.perform()["status"], "blocked")
        self.git.run("remote", "set-url", "origin", "https://github.com/example/sample.git")
        self.change_report(lambda r: r["git_baseline"].update(source_branch="other"))
        self.assertEqual(self.perform()["status"], "blocked")

    def test_configuration_change_requires_new_validation(self):
        self.config["publishing"]["draft"] = False
        self.write_config()
        self.assertEqual(self.perform()["status"], "blocked")

    def test_git_operation_failure_is_reported(self):
        with patch("workflow.runtime.publish.prepare_git", side_effect=ExecutionError("git_failed", "Git failed safely")):
            result = self.perform()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("git_failed", str(result["blocked_reasons"]))

    def test_mock_publication_saves_pr_and_does_not_approve_or_merge(self):
        gh = GitHub()
        network = NetworkGit(self.head)
        original = self.result_path.read_bytes()
        with patch("workflow.runtime.publish.authenticated_git", return_value=network):
            result = self.perform(execute=True, github=gh)
        self.assertEqual(result["status"], "published", result)
        self.assertEqual(result["pr_number"], 1)
        self.assertTrue(result["attempted"])
        self.assertEqual(self.result_path.read_bytes(), original)
        self.assertEqual(gh.calls.count("create"), 1)
        self.assertNotIn("approve", gh.calls)
        self.assertNotIn("merge", gh.calls)
        self.assertEqual([args[0] for args in network.calls], ["ls-remote", "ls-remote", "push"])
        self.assertNotIn("--force", str(network.calls))
        with patch("workflow.runtime.publish.authenticated_git") as spawn:
            repeated = self.perform(execute=True, github=gh)
        self.assertEqual(repeated["status"], "published")
        spawn.assert_not_called()
        self.assertEqual(json.loads((self.result_path.parent / "publish.json").read_text())["status"], "published")

    def test_push_failure_is_unknown_and_cannot_be_retried(self):
        gh = GitHub()
        network = NetworkGit(self.head, failure=ExecutionError("git_failed", "Push failed safely"))
        with patch("workflow.runtime.publish.authenticated_git", return_value=network):
            result = self.perform(execute=True, github=gh)
        self.assertEqual(result["status"], "outcome_unknown")
        self.assertTrue(result["attempted"])
        self.assertNotIn("create", gh.calls)
        repeated = self.perform(execute=True, github=gh)
        self.assertTrue(repeated["attempted"])
        self.assertEqual(repeated["status"], "outcome_unknown")

    def test_pr_failure_after_push_is_saved_without_second_create(self):
        gh = GitHub(failure="pr")
        with patch("workflow.runtime.publish.authenticated_git", return_value=NetworkGit(self.head)):
            result = self.perform(execute=True, github=gh)
        self.assertEqual(result["status"], "outcome_unknown")
        self.assertIsNotNone(result["commit_sha"])
        self.perform(execute=True, github=gh)
        self.assertEqual(gh.calls.count("create"), 1)

    def test_lost_creation_response_is_reconciled_by_query(self):
        gh = GitHub(lost_response=True)
        with patch("workflow.runtime.publish.authenticated_git", return_value=NetworkGit(self.head)):
            result = self.perform(execute=True, github=gh)
        self.assertEqual(result["status"], "published", result)
        self.assertEqual(gh.calls.count("create"), 1)

    def test_existing_remote_branch_blocks_before_push(self):
        network = NetworkGit(self.head, collision=True)
        with patch("workflow.runtime.publish.authenticated_git", return_value=network):
            result = self.perform(execute=True, github=GitHub())
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["attempted"])
        self.assertNotIn("push", [args[0] for args in network.calls])

    def test_prepared_result_can_be_explicitly_executed_later(self):
        prepared = self.perform()
        with patch("workflow.runtime.publish.authenticated_git", return_value=NetworkGit(self.head)):
            posted = self.perform(execute=True, github=GitHub())
        self.assertEqual(posted["status"], "published", posted)
        self.assertEqual(prepared["commit_sha"], posted["commit_sha"])

    def test_prepared_commit_tamper_blocks(self):
        prepared = self.perform()
        isolated = git_tools.Git(self.result_path.parent / "publication/git")
        isolated.run("update-ref", "refs/heads/" + prepared["branch"], self.head)
        self.assertEqual(self.perform()["status"], "blocked")


class AdapterPolicyTests(unittest.TestCase):
    def test_cli_never_executes_network_without_explicit_flag(self):
        with patch("workflow.runtime.publish.publish", return_value={"status": "prepared"}) as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(publish.main(["--config", "project.json", "--result", "result.json"]), 0)
        self.assertFalse(call.call_args.kwargs["execute"])

    def test_invalid_branch_placeholders_fail_without_commands(self):
        config = {"project_id": "sample", "base_branch": "main", "pr_policy": {"target_branch": "main"},
                  "publishing": {"branch_template": "ai/{unknown}/{run_id}"}}
        with self.assertRaises(ExecutionError):
            publish.branch_name(config, "00000000-0000-4000-8000-000000000000")

    def test_publishing_credentials_are_not_inherited_by_codex_or_git_reads(self):
        with patch.dict(os.environ, {"GH_TOKEN": "synthetic-token", "GITHUB_TOKEN": "synthetic-token"}):
            self.assertNotIn("GH_TOKEN", restricted_environment())
            self.assertNotIn("GITHUB_TOKEN", restricted_environment())
            self.assertNotIn("GH_TOKEN", git_tools.environment())
            self.assertEqual(github_adapter.environment()["GH_TOKEN"], "synthetic-token")

    def test_gh_missing_is_a_clear_failure(self):
        with patch("workflow.runtime.github_adapter.shutil.which", return_value=None):
            with self.assertRaises(ExecutionError) as error:
                github_adapter.GitHubCLI().preflight(Path.cwd())
        self.assertEqual(error.exception.status, "github_missing")

    def test_remote_protection_and_permission_checks(self):
        gh = github_adapter.GitHubCLI()
        repository = {"full_name": "example/sample", "permissions": {"push": True}}
        branch = {"commit": {"sha": "a" * 40}, "protected": True}
        protection = {"required_pull_request_reviews": {"required_approving_review_count": 1}, "enforce_admins": {"enabled": True}}
        with patch.object(gh, "call", side_effect=[json.dumps(v) for v in (repository, branch, protection)]):
            gh.check_repository("example/sample", "main", "a" * 40, Path.cwd())
        protection["required_pull_request_reviews"]["required_approving_review_count"] = 0
        with patch.object(gh, "call", side_effect=[json.dumps(v) for v in (repository, branch, protection)]):
            with self.assertRaises(ExecutionError) as error:
                gh.check_repository("example/sample", "main", "a" * 40, Path.cwd())
        self.assertEqual(error.exception.status, "protection_missing")

    def test_explicit_head_body_file_and_draft_no_implicit_push(self):
        gh = github_adapter.GitHubCLI()
        with patch.object(gh, "call") as call:
            gh.create_pr("example/sample", "main", "ai/sample/id", "title", Path("/private/body.md"), True, Path.cwd())
        args = call.call_args.args[0]
        self.assertIn("--head", args)
        self.assertIn("--body-file", args)
        self.assertIn("--draft", args)
        self.assertNotIn("--dry-run", args)


if __name__ == "__main__":
    unittest.main()

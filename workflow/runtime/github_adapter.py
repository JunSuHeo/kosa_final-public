"""Publishing-only GitHub CLI boundary; never approves or merges a PR.

GitHub CLI interface documentation:
https://cli.github.com/manual/gh_pr_create
https://cli.github.com/manual/gh_pr_list
https://cli.github.com/manual/gh_auth_status
https://cli.github.com/manual/gh_auth_token
https://cli.github.com/manual/gh_api
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import quote

from .codex_adapter import ExecutionError


def environment():
    env = {name: os.environ[name] for name in
           ("PATH", "HOME", "LANG", "GH_CONFIG_DIR", "GH_TOKEN", "GITHUB_TOKEN") if name in os.environ}
    env.update(GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1")
    if os.environ.get("WORKFLOW_PUBLISH_TOKEN"):
        env["GH_TOKEN"] = os.environ["WORKFLOW_PUBLISH_TOKEN"]
    return env


class GitHubCLI:
    def __init__(self):
        self.executable = None

    def transport_environment(self):
        return environment()

    def call(self, args, cwd, status="github_failed"):
        try:
            result = subprocess.run([self.executable, *args], cwd=cwd, env=self.transport_environment(),
                                    capture_output=True, text=True, encoding="utf-8", timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExecutionError(status, "GitHub CLI operation could not complete; raw output is withheld.") from exc
        if result.returncode:
            error = ExecutionError(status, "GitHub CLI operation failed. Check authentication, repository permissions and connectivity; raw output is withheld.", result.returncode)
            http_status = re.search(r"\bHTTP\s+([45][0-9]{2})\b", result.stderr or "", re.IGNORECASE)
            if http_status:
                error.http_status = int(http_status.group(1))
            raise error
        return result.stdout

    def preflight(self, cwd):
        self.executable = shutil.which("gh")
        if not self.executable:
            raise ExecutionError("github_missing", "GitHub CLI (gh) is not installed on the publishing PATH.")
        self.call(["--version"], cwd)
        for args, required in [
            (["auth", "status", "--help"], ["--hostname"]),
            (["auth", "token", "--help"], ["--hostname"]),
            (["pr", "create", "--help"], ["--repo", "--base", "--head", "--title", "--body-file", "--draft"]),
            (["pr", "list", "--help"], ["--repo", "--head", "--state", "--json"]),
            (["api", "--help"], ["--method"]),
        ]:
            text = self.call(args, cwd)
            if any(flag not in text for flag in required):
                raise ExecutionError("github_missing", "Installed gh lacks required documented publishing options.")
        # Never --show-token or auth-status JSON (JSON mode may exit 0 on failure).
        self.call(["auth", "status", "--hostname", "github.com"], cwd, "authentication_failed")

    def check_repository(self, repository, branch, base_sha, cwd, *, require_branch_protection=True):
        operation = "get_repository"
        try:
            data = json.loads(self.call(["api", "repos/" + repository, "--method", "GET"], cwd, "authentication_failed"))
            if data["full_name"].casefold() != repository.casefold() or not data["permissions"].get("push"):
                raise ExecutionError("permission_denied", "The authenticated account cannot push to the configured repository.")
            endpoint = "repos/" + repository + "/branches/" + quote(branch, safe="")
            operation = "get_base_branch"
            branch_data = json.loads(self.call(["api", endpoint, "--method", "GET"], cwd))
            if branch_data["commit"]["sha"] != base_sha:
                raise ExecutionError("base_mismatch", "The remote base branch differs from the validated baseline. Run generation and validation again.")
            if not require_branch_protection:
                return
            operation = "get_branch_protection"
            protection = json.loads(self.call(["api", endpoint + "/protection", "--method", "GET"], cwd))
            reviews = protection.get("required_pull_request_reviews") or {}
            bypass = reviews.get("bypass_pull_request_allowances") or {}
            if (not branch_data.get("protected") or reviews.get("required_approving_review_count", 0) < 1
                    or not protection.get("enforce_admins", {}).get("enabled") or any(bypass.values())):
                raise ExecutionError("protection_missing", "Verified human-review branch protection without bypass is required; no repository settings were changed.")
        except ExecutionError as exc:
            exc.operation = operation
            raise
        except (ValueError, KeyError, TypeError) as exc:
            error = ExecutionError("github_failed", "GitHub returned incomplete repository or protection data.")
            error.operation = operation
            raise error from exc

    def find_pr(self, repository, branch, cwd):
        try:
            value = json.loads(self.call(["pr", "list", "--repo", repository, "--head", branch,
                                         "--state", "all", "--json", "number,url,headRefOid,baseRefName,state,body"], cwd))
            if not isinstance(value, list):
                raise ValueError()
            return value
        except (ValueError, TypeError) as exc:
            raise ExecutionError("github_failed", "GitHub PR lookup returned invalid data.") from exc

    def create_pr(self, repository, base, head, title, body_file: Path, draft, cwd):
        args = ["pr", "create", "--repo", repository, "--base", base, "--head", head,
                "--title", title, "--body-file", str(body_file)]
        if draft:
            args.append("--draft")
        # Explicit head prevents gh from choosing a fork or pushing implicitly.
        self.call(args, cwd, "pr_failed")

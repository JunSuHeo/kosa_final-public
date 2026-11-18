"""Issue API extension of the existing gh boundary. No Git/PR operations."""

import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote

from .github_adapter import GitHubCLI, environment
from .codex_adapter import ExecutionError


class IssueGitHub(GitHubCLI):
    def __init__(self, repository, cwd):
        super().__init__()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*", repository):
            raise ValueError("Invalid repository identity")
        self.repository, self.cwd = repository, cwd
        self.prefix = "repos/" + repository

    def transport_environment(self):
        env = environment()
        env.pop("GH_TOKEN", None)
        if os.environ.get("GH_TOKEN"):
            env["GH_TOKEN"] = os.environ["GH_TOKEN"]
        return env

    def preflight(self):
        self.executable = shutil.which("gh")
        if not self.executable:
            raise ExecutionError("github_missing", "GitHub CLI is required for Issue intake.")
        self.call(["auth", "status", "--hostname", "github.com"], self.cwd, "authentication_failed")

    def api(self, endpoint, *, operation, data=None, paginate=False):
        args = ["api", endpoint, "--method", "GET" if data is None else "POST"]
        if paginate:
            # --slurp is not available in older GitHub CLI releases (including
            # 2.46 on the self-hosted runner). --paginate itself prints each
            # page as a separate JSON value, so decode and flatten those values
            # here instead of requiring the newer --slurp flag.
            args.append("--paginate")
        try:
            if data is None:
                raw = self.call(args, self.cwd)
            else:
                with tempfile.TemporaryDirectory(prefix="workflow-issue-api-") as directory:
                    path = Path(directory) / "body.json"
                    path.write_text(json.dumps(data), encoding="utf-8")
                    path.chmod(0o600)
                    raw = self.call(args + ["--input", str(path)], self.cwd)
            if not paginate:
                return json.loads(raw)

            decoder = json.JSONDecoder()
            comments = []
            offset = 0
            while offset < len(raw):
                while offset < len(raw) and raw[offset].isspace():
                    offset += 1
                if offset == len(raw):
                    break
                page, offset = decoder.raw_decode(raw, offset)
                if not isinstance(page, list):
                    raise ValueError("Paginated GitHub API response was not a list")
                # Also accept --slurp-shaped output in case a newer gh version
                # or a test double provides it.
                if all(isinstance(item, list) for item in page):
                    comments.extend(comment for sub_page in page for comment in sub_page)
                else:
                    comments.extend(page)
            return comments
        except ExecutionError as exc:
            exc.operation = operation
            raise
        except (ValueError, TypeError) as exc:
            error = ExecutionError("github_failed", "GitHub returned invalid Issue API data.")
            error.operation = operation
            raise error from exc

    def issue(self, number):
        return self.api(self.prefix + f"/issues/{number}", operation="get_issue")

    def comments(self, number):
        return self.api(self.prefix + f"/issues/{number}/comments?per_page=100",
                        operation="list_issue_comments", paginate=True)

    def comment(self, comment_id):
        return self.api(self.prefix + f"/issues/comments/{comment_id}", operation="get_issue_comment")

    def create_comment(self, number, body):
        return self.api(self.prefix + f"/issues/{number}/comments", operation="create_issue_comment",
                        data={"body": body})

    def permission(self, login):
        data = self.api(self.prefix + "/collaborators/" + quote(login, safe="") + "/permission",
                        operation="check_collaborator_permission")
        # GitHub's permission field normalizes custom roles to their base level.
        return data["permission"]

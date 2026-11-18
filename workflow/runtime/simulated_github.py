"""In-memory GitHub/transport; local Git reads only, no network or credentials."""

from .codex_adapter import ExecutionError
from .git_tools import Git


class SimulatedNetworkGit:
    is_simulated = True

    def __init__(self, base_branch, base_sha):
        self.base_branch, self.base_sha = base_branch, base_sha
        self.refs = {}
        self.calls = []

    def run(self, *args):
        self.calls.append(list(args))
        if args[0] == "ls-remote":
            ref = args[-1]
            sha = self.base_sha if ref == "refs/heads/" + self.base_branch else self.refs.get(ref)
            return (sha + "\t" + ref + "\n").encode() if sha else b""
        if args[0] == "push":
            sha, ref = args[-1].split(":", 1)
            if ref == "refs/heads/" + self.base_branch or ref in self.refs:
                raise ExecutionError("simulation_failed", "Simulation refused an existing or protected branch.")
            self.refs[ref] = sha
            return b""
        raise ExecutionError("simulation_failed", "Unsupported simulated Git transport operation.")


class SimulatedGitHubCLI:
    is_simulated = True

    def __init__(self, authenticated=True):
        self.authenticated = authenticated
        self.calls = []
        self.prs = []

    def preflight(self, cwd):
        self.calls.append({"operation": "authentication", "simulated": True})
        if not self.authenticated:
            raise ExecutionError("authentication_failed", "Simulated GitHub authentication is unavailable.")

    def check_repository(self, repository, branch, base_sha, cwd):
        self.calls.append({"operation": "repository_check", "repository": repository,
                           "base_branch": branch, "base_sha": base_sha, "simulated": True})

    def find_pr(self, repository, branch, cwd):
        self.calls.append({"operation": "pr_lookup", "simulated": True})
        return self.prs

    def create_pr(self, repository, base, head, title, body_file, draft, cwd):
        self.calls.append({"operation": "pr_create", "repository": repository, "base": base,
                           "head": head, "title": title, "draft": draft, "simulated": True})
        self.prs = [{"number": 1, "url": None, "baseRefName": base,
                     "headRefOid": Git(cwd).text("rev-parse", "refs/heads/" + head),
                     "state": "OPEN", "body": body_file.read_text(encoding="utf-8")}]

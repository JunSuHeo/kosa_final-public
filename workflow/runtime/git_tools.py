"""Restricted Git commands; no checkout, hooks, filters or inherited Git config."""

import os
from pathlib import Path
import shutil
import subprocess

from .codex_adapter import ExecutionError


def environment():
    result = {name: os.environ[name] for name in ("PATH", "HOME", "LANG") if name in os.environ}
    result.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                  GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    return result


class Git:
    def __init__(self, root: Path, extra_env=None):
        self.root = root
        self.extra_env = extra_env or {}

    def run(self, *args, data=None):
        executable = shutil.which("git")
        if not executable:
            raise ExecutionError("git_failed", "Git is not installed.")
        command = [executable, "-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false",
                   "-c", "core.attributesFile=" + os.devnull, "-c", "core.autocrlf=false",
                   "-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=always", *args]
        env = environment()
        env.update(self.extra_env)
        try:
            result = subprocess.run(command, cwd=self.root, input=data, capture_output=True,
                                    env=env, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExecutionError("git_failed", "Git could not complete the requested operation; raw output is withheld.") from exc
        if result.returncode:
            raise ExecutionError("git_failed", "Git operation failed; credentials and raw output are withheld.", result.returncode)
        return result.stdout

    def text(self, *args):
        return self.run(*args).decode("utf-8").strip()


def baseline(root, config):
    git = Git(root)
    try:
        return {"available": True, "base_branch": config["base_branch"],
                "base_sha": git.text("rev-parse", "--verify", "refs/heads/" + config["base_branch"]),
                "head_sha": git.text("rev-parse", "--verify", "HEAD"),
                "source_branch": git.text("branch", "--show-current")}
    except (ExecutionError, UnicodeError):
        # Offline/fake repositories can still generate and test candidates;
        # the publisher will reject a missing trustworthy Git baseline.
        return {"available": False, "base_branch": config["base_branch"]}

"""Prepare a verified PR locally; --execute explicitly authorizes push/PR creation.

python3 -B -m workflow.runtime.publish --config CONFIG --result RESULT
The producer, tester and publisher have separate roles. This module never runs
candidate code/tests or changes the source checkout/index/branches.
"""

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shlex
import string
import sys
import uuid

from . import branch_rules, evidence, git_tools, run, workspace, test_runner, validate_config as validator
from .codex_adapter import ExecutionError
from .github_adapter import GitHubCLI, environment as github_environment


def now():
    return datetime.now(timezone.utc).isoformat()


def branch_name(config, run_id, report=None):
    uuid.UUID(run_id)
    template = config["publishing"]["branch_template"]
    try:
        fields = branch_rules.template_fields(template)
        if fields == branch_rules.ISSUE_FIELDS and (report is None or "approved_issue" not in report):
            # Manual tasks have no Issue approver/title. Preserve their CLI path.
            template = config["publishing"].get("manual_branch_template", "ai/{project_id}/{run_id}")
            fields = branch_rules.template_fields(template, manual=True)
        values = {"project_id": config["project_id"], "run_id": run_id}
        if fields == branch_rules.ISSUE_FIELDS:
            issue = report["approved_issue"]
            approver = issue["approver"]
            if not isinstance(approver, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", approver):
                raise ValueError("Invalid Issue approver")
            started = datetime.fromisoformat(report["started_at"])
            if started.tzinfo is None:
                raise ValueError("Execution start time must include a timezone")
            values.update(date=started.astimezone(timezone(timedelta(hours=9), "Asia/Seoul")).strftime("%y.%m.%d"),
                          approver=approver, issue_title=branch_rules.issue_title_component(issue["title"]))
        name = template.format(**values)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise ExecutionError("config_error", "Branch template or approved Issue naming data is invalid.") from exc
    if (not branch_rules.valid_name(name)
            or name in (config["base_branch"], config["pr_policy"]["target_branch"])):
        raise ExecutionError("config_error", "Publishing branch is invalid or equals a protected base branch.")
    return name


def private_file(path, limit=16 * 1024 * 1024):
    if path.is_symlink() or not path.is_file() or path.resolve() != path.absolute():
        raise ExecutionError("untrusted_result", "Evidence must be regular files without symlink aliases.")
    info = path.stat()
    if info.st_nlink != 1 or info.st_size > limit or (os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
        raise ExecutionError("untrusted_result", "Evidence ownership, access permissions or size are unsafe.")
    return path.read_bytes()


def load_verified(result_path, config_path, root):
    if sys.platform != "linux":
        raise ExecutionError("environment_error", "Publication currently requires Linux/WSL.")
    result_path = result_path.absolute()
    directory = result_path.parent
    if result_path.name != "result.json" or directory.resolve().is_relative_to(root) or directory.is_symlink():
        raise ExecutionError("untrusted_result", "Result must be an external engine-owned result.json.")
    if directory.stat().st_mode & 0o077 or directory.stat().st_uid != os.getuid():
        raise ExecutionError("untrusted_result", "Run directory is not private to the current user.")
    raw = private_file(result_path)
    checksum = private_file(directory / "result.sha256", 128).decode().strip()
    if checksum != hashlib.sha256(raw).hexdigest():
        raise ExecutionError("untrusted_result", "Result checksum is missing or inconsistent; legacy results cannot be published.")
    report = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=validator._unique_object, parse_constant=validator._reject_constant)
    config, config_sha = run._load(config_path.absolute(), root)
    if "publishing" not in config:
        raise ExecutionError("config_error", "An explicit publishing configuration is required.")
    if report["config_sha256"] != config_sha or report["project_id"] != config["project_id"]:
        raise ExecutionError("untrusted_result", "Configuration differs from the tested run; execute and validate again.")
    if report["run_id"] != directory.name or report["result_path"] != str(result_path):
        raise ExecutionError("untrusted_result", "Run ID or evidence location is inconsistent.")
    if (report["final_status"] != "completed" or report["codex_status"] != "succeeded"
            or report["validation_status"] != "passed" or report["errors"]):
        raise ExecutionError("validation_blocked", "Only successfully generated and independently verified results may be published.")
    validation = report["validation"]
    if validation["status"] != "passed" or validation["scope_status"] != "passed" or validation["errors"]:
        raise ExecutionError("validation_blocked", "Independent validation is missing, failed or inconsistent.")
    all_tests = []
    for kind in ("unit", "e2e"):
        actual = validation["tests"][kind]
        expected = config["tests"][kind]
        if len(actual) != len(expected):
            raise ExecutionError("validation_blocked", "Test evidence is missing or duplicated.")
        for test, result in zip(expected, actual):
            if any(result[key] != value for key, value in {
                "id": test["id"], "kind": kind, "required": test["required"], "cwd": test["cwd"],
                "command": test["command"], "on_failure": test.get("on_failure", "block"),
                "timeout_seconds": test.get("timeout_seconds", 300),
            }.items()):
                raise ExecutionError("validation_blocked", "Test evidence does not match the trusted configuration.")
            if result["status"] not in ("passed", "failed", "not_run", "unavailable", "timeout"):
                raise ExecutionError("validation_blocked", "Unknown test status.")
            if result["status"] == "passed" and (type(result["return_code"]) is not int or result["return_code"] != 0):
                raise ExecutionError("validation_blocked", "A passed test lacks a successful process exit code.")
            if result["status"] == "not_run" and test_runner._skip(test, report["changes"]) is None:
                raise ExecutionError("validation_blocked", "A test was skipped without an applicable project policy.")
            if result["status"] == "passed" and test_runner._NO_TESTS.search(result["stdout"] + "\n" + result["stderr"]):
                raise ExecutionError("validation_blocked", "A passed test reports zero executed tests.")
            if (type(result["required"]) is not bool or type(result["duration_seconds"]) not in (int, float)
                    or not math.isfinite(result["duration_seconds"]) or result["duration_seconds"] < 0
                    or datetime.fromisoformat(result["ended_at"]) < datetime.fromisoformat(result["started_at"])):
                raise ExecutionError("validation_blocked", "Test timing evidence is incomplete.")
            all_tests.append(result)
    if test_runner.judge(all_tests)[0] != "passed":
        raise ExecutionError("validation_blocked", "Mandatory tests or optional blocking checks did not pass.")
    baseline_raw = private_file(directory / "baseline.json")
    if hashlib.sha256(baseline_raw).hexdigest() != report["baseline_sha256"]:
        raise ExecutionError("untrusted_result", "Starting snapshot checksum is inconsistent.")
    baseline = json.loads(baseline_raw.decode("utf-8-sig"), object_pairs_hook=validator._unique_object, parse_constant=validator._reject_constant)
    if (baseline["format_version"] != 1 or baseline["run_id"] != report["run_id"]
            or baseline["project_id"] != config["project_id"] or baseline["config_sha256"] != config_sha or baseline["git"] != report["git_baseline"]
            or baseline["config_relative"] != config_path.absolute().relative_to(root).as_posix()):
        raise ExecutionError("untrusted_result", "Starting snapshot is not from this execution.")
    git_base = baseline["git"]
    if (not git_base["available"] or git_base["base_branch"] != config["base_branch"]
            or git_base["source_branch"] != config["base_branch"] or git_base["head_sha"] != git_base["base_sha"]
            or config["pr_policy"]["target_branch"] != config["base_branch"]
            or not re.fullmatch(r"[0-9a-f]{40}", git_base["base_sha"])):
        raise ExecutionError("base_mismatch", "A matching SHA-1 Git base branch and source HEAD are required.")
    candidate = directory / "workspace"
    if report["workspace_path"] != str(candidate):
        raise ExecutionError("untrusted_result", "Candidate path does not belong to this execution.")
    changes = workspace.collect(candidate, config, baseline["files"], baseline["config_relative"])
    if not changes:
        raise ExecutionError("no_changes", "There are no automation changes to publish.")
    if changes != report["changes"] or [c["path"] for c in changes] != report["changed_files"]:
        raise ExecutionError("untrusted_result", "Changed-file evidence is inconsistent with the candidate.")
    if evidence.digest(workspace.inventory(candidate)) != validation["candidate_sha256"]:
        raise ExecutionError("untrusted_result", "Candidate content differs from the independently tested snapshot.")
    return config, report, baseline, candidate


def remote_url(config, root):
    value = git_tools.Git(root).text("remote", "get-url", config["publishing"]["remote"])
    repo = config["repository"]["owner"] + "/" + config["repository"]["name"]
    allowed = ["https://github.com/" + repo, "https://github.com/" + repo + ".git",
               "git@github.com:" + repo, "git@github.com:" + repo + ".git"]
    if value.casefold() not in [url.casefold() for url in allowed]:
        raise ExecutionError("remote_mismatch", "Remote is not the configured credential-free GitHub repository.")
    return "https://github.com/" + repo + ".git"


def check_baseline_tree(git, baseline, config):
    rows = git.run("ls-tree", "-r", "-z", baseline["git"]["base_sha"]).split(b"\0")
    tracked = {}
    for row in rows:
        if not row:
            continue
        header, path = row.split(b"\t", 1)
        mode, kind, object_id = header.decode().split()
        relative = path.decode("utf-8")
        if (workspace.protected(relative) or relative == baseline["config_relative"]
                or relative in config["execution"]["instructions"]):
            continue
        if any(Path(relative).is_relative_to(Path(scope)) for scope in config["allowed_paths"]):
            if kind != "blob" or mode not in ("100644", "100755"):
                raise ExecutionError("path_violation", "Git baseline contains links or submodules in the approved scope.")
            content = git.run("cat-file", "blob", object_id)
            tracked[relative] = {"sha256": hashlib.sha256(content).hexdigest(), "executable": mode == "100755"}
    if tracked != baseline["files"]:
        raise ExecutionError("user_changes", "The tested starting snapshot contains uncommitted, untracked or omitted project files. Commit the intended project baseline manually, then run generation and validation again.")


def pr_text(config, report, issue=None):
    def escape(value):
        # Treat task/output as data, suppress image attachment and mention syntax.
        return html.escape(str(value)).replace("!", "&#33;").replace("[", "&#91;").replace("@", "&#64;")
    title = f"[{config['project_id']}] " + " ".join(report["task"].split())[:100]
    body = ["## Summary", "Verified automation changes for " + escape(config["project_id"]),
            "", "## User request", escape(report["task"]), "", "## Changed files"]
    body += [f"- {escape(c['change'])}: {escape(c['path'])}" for c in report["changes"]]
    changed_docs = [c["path"] for c in report["changes"] if c["path"] in config["design_documents"]]
    body += ["", "## Design documents", escape(", ".join(changed_docs) if changed_docs else "No configured design document changed."), "", "## Independent tests"]
    for kind in ("unit", "e2e"):
        for result in report["validation"]["tests"][kind]:
            body.append(f"- {kind}/{escape(result['id'])}: {result['status']}; exit={result['return_code']}; duration={result['duration_seconds']}s")
            body.append("  Command: " + escape(json.dumps(result["command"], ensure_ascii=False)))
            if result.get("reason"):
                body.append("  Reason: " + escape(result["reason"]))
    body += ["", "## Verification", "Final validation: " + report["validation_status"],
             "Run ID: " + report["run_id"], "Candidate SHA-256: " + report["validation"]["candidate_sha256"]]
    if issue is not None:
        body += ["Related issue: #" + str(issue)]
    body += ["", "## Risks and remaining work", "Tests do not establish completeness or detect every weakened test. Human review of code, design and tests is required.",
             "No automatic approval, merge or deployment was performed."]
    return workspace.redact(title), workspace.redact("\n".join(body) + "\n")


def prepare_git(directory, root, config, report, baseline, candidate, branch):
    checkout = directory / "git"
    if checkout.exists():
        raise ExecutionError("publication_conflict", "An existing publishing Git workspace must not be overwritten.")
    checkout.mkdir(mode=0o700)
    git = git_tools.Git(checkout)
    git.run("init", "--quiet", "--template=")
    git.run("fetch", "--quiet", "--no-tags", "--no-recurse-submodules", str(root), baseline["git"]["base_sha"])
    check_baseline_tree(git, baseline, config)
    git.run("read-tree", baseline["git"]["base_sha"])
    for change in report["changes"]:
        if change["change"] == "deleted":
            git.run("update-index", "--force-remove", "--", change["path"])
        else:
            data = (candidate / change["path"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != change["after"]["sha256"]:
                raise ExecutionError("untrusted_result", "Candidate changed while preparing Git objects.")
            object_id = git.run("hash-object", "-w", "--stdin", data=data).decode().strip()
            git.run("update-index", "--add", "--cacheinfo", "100755" if change["after"]["executable"] else "100644", object_id, change["path"])
    names = git.run("diff", "--cached", "--name-only", "-z", "--no-renames", baseline["git"]["base_sha"]).decode().split("\0")
    if sorted(filter(None, names)) != sorted(report["changed_files"]):
        raise ExecutionError("untrusted_result", "Staged Git changes do not match this execution.")
    tree = git.text("write-tree")
    # Compare the staged full approved project to the tested snapshot, including
    # unchanged files. Plumbing never executes attributes, filters or hooks.
    staged = dict(baseline)
    staged["git"] = {"base_sha": tree}
    staged["files"] = workspace.inventory(candidate)
    check_baseline_tree(git, staged, config)
    author = config["publishing"].get("commit_author")
    if author is None:
        source = git_tools.Git(root)
        try:
            author = {"name": source.text("config", "--get", "user.name"), "email": source.text("config", "--get", "user.email")}
        except ExecutionError as exc:
            if exc.return_code != 1:
                raise
            raise ExecutionError("commit_identity_missing", "Set publishing.commit_author or configure user.name and user.email in the source Git checkout.") from exc
    if (any(not value.strip() or any(c in value for c in "\n\r\0<>") for value in author.values())
            or "@" not in author["email"] or workspace.redact(json.dumps(author)) != json.dumps(author)):
        raise ExecutionError("config_error", "A valid, secret-free Git commit identity is required.")
    git.extra_env.update(GIT_AUTHOR_NAME=author["name"], GIT_AUTHOR_EMAIL=author["email"],
                         GIT_COMMITTER_NAME=author["name"], GIT_COMMITTER_EMAIL=author["email"])
    sha = git.run("commit-tree", tree, "-p", baseline["git"]["base_sha"],
                  data=("Verified automation run " + report["run_id"] + "\n").encode()).decode().strip()
    git.run("update-ref", "refs/heads/" + branch, sha)
    patch = git.run("diff", "--binary", "--no-ext-diff", "--no-textconv", baseline["git"]["base_sha"], sha)
    evidence.atomic(directory, "changes.patch", patch)
    return checkout, sha


def authenticated_git(checkout, directory, gh):
    # Trusted askpass script only. Token goes directly to Git over a pipe; it is
    # never put in a file, command argument, remote URL, result or application log.
    helper = directory / "askpass.py"
    script = "#!/usr/bin/env python3\nimport os,subprocess,sys\n"
    script += "if 'username' in sys.argv[1].lower(): print('x-access-token')\n"
    script += "else:\n token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')\n"
    script += f" if not token:\n  p=subprocess.run([{gh.executable!r},'auth','token','--hostname','github.com'],capture_output=True,text=True)\n  token=p.stdout.strip() if p.returncode==0 else ''\n"
    script += " if not token: sys.exit(1)\n print(token)\n"
    evidence.atomic(directory, "askpass.py", script.encode())
    helper.chmod(0o700)
    env = github_environment()
    env.update(GIT_ASKPASS=shlex.quote(str(helper)), GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="credential.helper", GIT_CONFIG_VALUE_0="")
    return git_tools.Git(checkout, env)


def publish(result_path, config_path, root, *, execute=False, issue=None, github=None, simulate=False, network_git=None, publication_guard=None):
    root = root.resolve()
    outcome = {"attempted": False, "publishable": False, "local_eligible": False, "status": "checking",
               "blocked_reasons": [], "commit_sha": None, "branch": None, "pr_number": None,
               "pr_url": None, "started_at": now(), "ended_at": None, "run_id": None}
    outcome.update(mode="simulate" if simulate else "real" if execute else "prepare", simulated_attempted=False)
    journal_name = "publish.simulated.json" if simulate else "publish.json"
    workspace_name = "publication.simulated" if simulate else "publication"
    directory = None
    lock = None
    journal_safe = True
    operation = "verify_publish_evidence"
    try:
        if simulate and (execute or (github is not None and getattr(github, "is_simulated", False) is not True)
                         or (network_git is not None and getattr(network_git, "is_simulated", False) is not True)):
            raise ExecutionError("simulation_failed", "Simulation cannot use real GitHub/transport adapters or execute mode.")
        if network_git is not None and not simulate:
            raise ExecutionError("simulation_failed", "A simulated transport may only be supplied in simulation mode.")
        target = result_path.absolute().parent
        if (result_path.name != "result.json" or target.resolve().is_relative_to(root) or target.resolve() != target
                or target.stat().st_uid != os.getuid() or target.stat().st_mode & 0o077):
            raise ExecutionError("untrusted_result", "Publishing output requires a private, external engine run directory.")
        directory = target
        outcome["run_id"] = directory.name
        lock_path = directory / (".publish.simulated.lock" if simulate else ".publish.lock")
        lock_path.mkdir(mode=0o700)
        lock = lock_path
        previous_path = directory / journal_name
        previous = None
        if previous_path.exists():
            journal_safe = False
            previous_raw = private_file(previous_path)
            previous = json.loads(previous_raw.decode("utf-8-sig"), object_pairs_hook=validator._unique_object, parse_constant=validator._reject_constant)
            if (not isinstance(previous, dict) or previous.get("run_id") != directory.name
                    or type(previous.get("attempted")) is not bool or not isinstance(previous.get("blocked_reasons"), list)
                    or previous.get("status") not in ("prepared", "published", "simulated", "simulation_failed", "blocked", "outcome_unknown", "push_attempted", "pushed", "pr_attempted")
                    or (simulate and previous.get("mode") != "simulate")
                    or workspace.redact(json.dumps(previous)) != json.dumps(previous)):
                raise ExecutionError("publication_conflict", "Existing publication journal is corrupt or untrusted; its external-operation history must not be overwritten.")
            journal_safe = True
        if previous and (previous.get("attempted") or previous.get("simulated_attempted")):
            outcome = dict(previous)
            if previous["status"] == ("simulated" if simulate else "published"):
                return outcome
            raise ExecutionError("publication_conflict", "A previous external publication attempt is unresolved. Do not retry until its branch and PR state have been reconciled.")
        config, report, baseline, candidate = load_verified(result_path, config_path, root)
        outcome["run_id"] = report["run_id"]
        url = remote_url(config, root)
        branch = branch_name(config, report["run_id"], report)
        outcome["branch"] = branch
        prepared = directory / workspace_name
        if previous and previous.get("local_eligible") and previous.get("commit_sha"):
            checkout = prepared / "git"
            sha = previous["commit_sha"]
            if (prepared.resolve() != prepared or checkout.resolve() != checkout or (checkout / ".git").is_symlink()
                    or git_tools.Git(checkout).text("rev-parse", "--absolute-git-dir") != str(checkout / ".git")):
                raise ExecutionError("publication_conflict", "Prepared Git directory is not the isolated publishing repository.")
            if git_tools.Git(checkout).text("rev-parse", "refs/heads/" + branch) != sha:
                raise ExecutionError("publication_conflict", "Prepared branch changed since local review.")
            # Recheck the complete staged content on every explicit execution.
            staged = dict(baseline, git={"base_sha": sha}, files=workspace.inventory(candidate))
            check_baseline_tree(git_tools.Git(checkout), staged, config)
        else:
            operation = "prepare_git_commit"
            prepared.mkdir(mode=0o700)
            checkout, sha = prepare_git(prepared, root, config, report, baseline, candidate, branch)
        operation = "prepare_pr_metadata"
        title, body = pr_text(config, report, issue)
        if len(title) > 256 or len(body.encode()) > 65536:
            raise ExecutionError("publication_conflict", "Generated PR title or body exceeds the publishing size limit.")
        evidence.atomic(prepared, "pr-title.txt", title.encode())
        evidence.atomic(prepared, "pr-body.md", body.encode())
        outcome.update(local_eligible=True, commit_sha=sha, status="prepared")
        outcome["remote_check"] = "not_run"
        def save():
            evidence.save_json(directory, journal_name, outcome)
        save()
        operation = "verify_approval"
        if publication_guard is not None:
            publication_guard()
        if execute or simulate:
            if simulate:
                from .simulated_github import SimulatedGitHubCLI, SimulatedNetworkGit
                gh = github if github is not None else SimulatedGitHubCLI()
                git = network_git if network_git is not None else SimulatedNetworkGit(config["base_branch"], baseline["git"]["base_sha"])
                outcome["simulation"] = {"github_requests": gh.calls, "git_transport_requests": git.calls}
            else:
                gh = github if github is not None else GitHubCLI()
            operation = "github_cli_preflight"
            gh.preflight(checkout)
            repo = config["repository"]["owner"] + "/" + config["repository"]["name"]
            operation = "check_repository"
            gh.check_repository(repo, config["base_branch"], baseline["git"]["base_sha"], checkout)
            operation = "check_remote_refs"
            if not simulate:
                git = authenticated_git(checkout, prepared, gh)
            # Ref checks are authenticated reads; no automatic force push.
            if git.run("ls-remote", "--heads", url, "refs/heads/" + config["base_branch"]).decode().split()[0] != baseline["git"]["base_sha"]:
                raise ExecutionError("base_mismatch", "Remote base changed since validation.")
            branch_exists = git.run("ls-remote", "--heads", url, "refs/heads/" + branch).strip()
            if branch_exists:
                raise ExecutionError("publication_conflict", "Publishing branch or PR already exists; existing work is never overwritten.")
            operation = "find_existing_pr"
            if gh.find_pr(repo, branch, checkout):
                raise ExecutionError("publication_conflict", "Publishing branch or PR already exists; existing work is never overwritten.")
            operation = "verify_approval"
            if publication_guard is not None:
                publication_guard()
            outcome.update(publishable=not simulate, remote_check="simulated" if simulate else "passed",
                           attempted=not simulate, simulated_attempted=simulate, status="push_attempted")
            operation = "push_branch"
            save()
            git.run("push", "--porcelain", "--no-verify", url, sha + ":refs/heads/" + branch)
            outcome["status"] = "pushed"
            save()
            outcome["status"] = "pr_attempted"
            operation = "verify_approval"
            if publication_guard is not None:
                publication_guard()
            operation = "create_pr"
            save()
            creation_error = None
            try:
                gh.create_pr(repo, config["base_branch"], branch, title, prepared / "pr-body.md", config["publishing"]["draft"], checkout)
            except ExecutionError as exc:
                creation_error = exc
            operation = "confirm_pr"
            prs = gh.find_pr(repo, branch, checkout)
            matches = [pr for pr in prs if pr.get("headRefOid") == sha and pr.get("baseRefName") == config["base_branch"]
                       and pr.get("state") == "OPEN" and report["run_id"] in pr.get("body", "")]
            if len(matches) != 1:
                if creation_error:
                    operation = "create_pr"
                    raise creation_error
                raise ExecutionError("pr_unknown", "PR creation outcome could not be confirmed. Do not create a replacement PR automatically.")
            pr = matches[0]
            if (type(pr["number"]) is not int or pr["number"] <= 0
                    or (not simulate and pr["url"].casefold() != f"https://github.com/{repo}/pull/{pr['number']}".casefold())):
                raise ExecutionError("pr_unknown", "PR identity returned by GitHub is invalid.")
            if simulate:
                outcome.update(status="simulated", simulated_pr_number=pr["number"], simulated_at=now())
            else:
                outcome.update(status="published", pr_number=pr["number"], pr_url=pr["url"], published_at=now())
    except ExecutionError as exc:
        outcome["status"] = "simulation_failed" if simulate and outcome["simulated_attempted"] else "outcome_unknown" if outcome["attempted"] else "blocked"
        outcome["publishable"] = False
        reason = {"status": exc.status, "message": workspace.redact(str(exc)),
                  "operation": getattr(exc, "operation", operation)}
        http_status = getattr(exc, "http_status", None)
        if type(http_status) is int and 400 <= http_status <= 599:
            reason["http_status"] = http_status
        outcome["blocked_reasons"].append(reason)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        outcome["status"] = "simulation_failed" if simulate and outcome["simulated_attempted"] else "outcome_unknown" if outcome["attempted"] else "blocked"
        outcome["publishable"] = False
        outcome["blocked_reasons"].append({"status": "invalid_publication", "operation": operation,
                                           "message": "Missing/corrupt evidence, unsafe existing publication state or local operation failure; raw details are withheld."})
    finally:
        outcome["ended_at"] = now()
        # Invalid/untrusted directories are never used as output destinations.
        if directory is not None and lock is not None:
            try:
                name = journal_name if journal_safe else "publish-error-" + str(uuid.uuid4()) + ".json"
                evidence.save_json(directory, name, outcome)
            except OSError:
                outcome["status"] = "outcome_unknown" if outcome["attempted"] else "save_failed"
                message = ("Simulated publishing result could not be saved. Inspect local run state before retrying." if simulate
                           else "Publishing result could not be saved. Reconcile remote state before retrying.")
                outcome["blocked_reasons"].append({"status": "save_failed", "message": message})
            try:
                lock.rmdir()
            except OSError:
                outcome["blocked_reasons"].append({"status": "lock_cleanup_failed", "message": "Publishing lock cleanup failed; inspect the private run directory before retrying."})
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true", help="explicitly authorize real push and PR creation")
    modes.add_argument("--simulate", action="store_true", help="run in-memory GitHub/transport simulation with no network")
    parser.add_argument("--issue", type=int, help="optional existing Issue number; no Issue is created or closed")
    args = parser.parse_args(argv)
    if args.issue is not None and args.issue <= 0:
        parser.error("issue must be a positive number")
    result = publish(args.result, args.config, args.repo_root, execute=args.execute, issue=args.issue, simulate=args.simulate)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] in ("prepared", "published", "simulated") else 1


if __name__ == "__main__":
    raise SystemExit(main())

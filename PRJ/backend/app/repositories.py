"""Read-only Git access and bounded, commit-specific source analysis."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import subprocess
import time
from urllib.parse import quote
from uuid import uuid4

from fastapi import HTTPException
import httpx

from psycopg.types.json import Jsonb

from .config import settings
from .db import connect
from .github_connection import connected_token

LOCAL_ANALYSIS_VERSION = "git-text.v1"
GITHUB_ANALYSIS_VERSION = "git-text.v2"
MAX_FILES = 360
MAX_FILE_BYTES = 40_000
MAX_TOTAL_BYTES = 2_400_000
MAX_MODEL_BYTES = 32_000
MAX_TREE_BYTES = 1_000_000
LOCAL_ANALYSIS_SECONDS = 60
RULE_FILES = {"agents.md", "readme", "readme.md", "makefile", "contributing.md", "package.json", "pyproject.toml",
              "pom.xml", "build.gradle", "tsconfig.json", "go.mod", "cargo.toml"}
SOURCE_SUFFIXES = {
    ".md", ".py", ".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".java",
    ".kt", ".cs", ".go", ".rs", ".rb", ".php", ".sql", ".xml", ".html", ".css",
    ".scss", ".json", ".yaml", ".yml", ".toml", ".jsp", ".xaml", ".swift",
}
EXCLUDED_DIRS = {
    "node_modules", "vendor", "dist", "build", "target", "coverage", "bin", "obj",
    "data", "dumps", "secrets", "credentials", "logs", "uploads", "backup", "backups",
}
SECRET = re.compile(
    r"-----BEGIN [^-\n]+PRIVATE KEY-----|"
    r"(?i:\b(?:github_pat_|gh[pousr]_|sk-(?:proj-|or-v1-)?)[a-z0-9_\-]{16,})|"
    r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bAIza[\w-]{35}\b|"
    r"(?i:\b(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|client[_-]?secret|authorization)"
    r"""['"]?\s*[:=]\s*['"](?:[^'"\n]{4,})['"])|"""
    r"(?i:\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|https?)://[^\s/@:]+:[^\s/@]+@)|"
    r"\beyJ[\w-]+\.eyJ[\w-]+\.[\w-]+\b|"
    r"\b\d{6}-[1-4]\d{6}\b|\b01[016789][- ]\d{3,4}[- ]\d{4}\b|"
    r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"
)


class RepositoryError(RuntimeError):
    pass


def git(args, *, directory=None, deadline, limit=8192):
    env = {
        "PATH": os.defpath + ":/opt/homebrew/bin:/usr/local/bin",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1", "GIT_NO_LAZY_FETCH": "1",
        "GIT_ALLOW_PROTOCOL": "", "LC_ALL": "C",
    }
    command = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"]
    if directory:
        # A validated, read-only bind mount can have a different owner from the worker.
        # Trust only this checked path; never change Git's global safety configuration.
        command += ["-c", "safe.directory=" + str(directory), "-C", str(directory)]
    try:
        with subprocess.Popen(command + args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, env=env) as proc, selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            output = bytearray()
            try:
                while time.monotonic() < deadline and sel.select(deadline - time.monotonic()):
                    chunk = os.read(proc.stdout.fileno(), min(65536, limit + 1 - len(output)))
                    if not chunk:
                        if proc.wait(timeout=max(0.01, deadline - time.monotonic())):
                            raise RepositoryError("Git 저장소 또는 지정한 참조에 접근할 수 없습니다.")
                        return bytes(output)
                    output.extend(chunk)
                    if len(output) > limit:
                        raise RepositoryLimit("Git 응답이 분석 상한을 초과했습니다.")
                raise RepositoryLimit("저장소 분석 시간이 상한을 초과했습니다.")
            finally:
                if proc.poll() is None:
                    proc.kill()
    except (OSError, subprocess.TimeoutExpired):
        raise RepositoryError("Git 작업을 완료할 수 없습니다.") from None


def local_path(repository):
    configured = settings().local_repository_root
    parts = PurePosixPath(repository).parts
    if (settings().app_env != "local" or not configured or not parts
            or repository.startswith("/") or "\\" in repository
            or ".." in parts or ".git" in parts or any(ord(ch) < 32 for ch in repository)):
        raise RepositoryError("허용된 로컬 저장소의 상대 경로를 입력해 주세요.")
    root = settings().local_repository_root_resolved
    path = root.joinpath(*parts)
    try:
        valid = path.resolve() == path and path.is_dir() and (path / ".git").is_dir()
    except (OSError, RuntimeError):
        valid = False
    if not valid:
        raise RepositoryError("허용 경로에 일반 Git 저장소가 필요합니다.")
    return path


def local_gitdir(path, deadline):
    metadata = path / ".git"
    # Local mounts must be operator-controlled. Reject worktree indirection, links,
    # alternate object stores and config includes before starting Git.
    if metadata.is_symlink() or any((metadata / p).exists() for p in (
        "commondir", "objects/info/alternates", "objects/info/http-alternates",
    )):
        raise RepositoryError("연결된 Git 메타데이터는 로컬 분석에서 지원하지 않습니다.")
    for directory, dirs, files in os.walk(metadata):
        if time.monotonic() >= deadline:
            raise RepositoryLimit("저장소 분석 시간이 상한을 초과했습니다.")
        if any((Path(directory) / name).is_symlink() for name in dirs + files):
            raise RepositoryError("Git 메타데이터의 심볼릭 링크는 지원하지 않습니다.")
    config = metadata / "config"
    if config.exists():
        with config.open("rb") as stream:
            raw = stream.read(16385)
        if len(raw) > 16384 or re.search(
            rb"(?im)^\s*\[\s*(include|filter|extensions|fsmonitor|diff|core\.)|"
            rb"(?im:^\s*(?:fsmonitor|worktree|attributesfile|hookspath)\s*=)", raw
        ):
            raise RepositoryError("외부 설정 또는 실행을 참조하는 Git 저장소는 지원하지 않습니다.")


def github_url(repository):
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?", repository)
    if not match or match.group(1).split("/")[-1] in {".", ".."}:
        raise RepositoryError("https://github.com/소유자/저장소 형식의 URL을 입력해 주세요.")
    return "https://github.com/" + match.group(1).lower()


def github_token(owner):
    s = settings()
    token = s.github_user_tokens.get(owner)
    if not token and s.app_env == "local" and s.auth_mode == "mock" and owner == "demo-user":
        token = s.github_local_token
    return token or None


def resolve(source):
    deadline = time.monotonic() + 20
    ref = source["ref"]
    if source["kind"] == "local":
        path = local_path(source["repository"])
        local_gitdir(path, deadline)
        if ref != "HEAD":
            git(["check-ref-format", "refs/heads/" + ref], deadline=deadline)
        revision = ref if ref == "HEAD" else "refs/heads/" + ref
        sha = git(["rev-parse", "--verify", revision + "^{commit}"], directory=path, deadline=deadline).strip()
        dirty = bool(git(["status", "--porcelain", "-uno", "--ignore-submodules=all"], directory=path, deadline=deadline, limit=MAX_TREE_BYTES))
        if not dirty:
            dirty = bool(git(["ls-files", "--others", "--exclude-standard", "--directory"],
                             directory=path, deadline=deadline, limit=MAX_TREE_BYTES))
    else:
        git(["check-ref-format", "refs/heads/" + ref], deadline=deadline)
        path = "branches/" + quote(ref, safe="")
        with github_repository(source, path, deadline) as (_, branch):
            sha = str(branch.get("commit", {}).get("sha", "")).encode()
        dirty = False
    if not re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", sha):
        raise RepositoryError("커밋을 확인할 수 없습니다.")
    return sha.decode(), dirty


def analysis_version(source):
    return GITHUB_ANALYSIS_VERSION if source["kind"] == "github" else LOCAL_ANALYSIS_VERSION


def schedule(c, source, sha, dirty):
    version = analysis_version(source)
    c.execute(
        "INSERT INTO studio_code_snapshots(id,source_id,commit_sha,analysis_version,dirty,status) "
        "VALUES (%s,%s,%s,%s,%s,'queued') ON CONFLICT(source_id,commit_sha,analysis_version) DO NOTHING",
        (uuid4(), source["id"], sha, version, dirty),
    )
    return c.execute(
        "SELECT id,commit_sha,analysis_version,dirty,status,error,created_at FROM studio_code_snapshots "
        "WHERE source_id=%s AND commit_sha=%s AND analysis_version=%s",
        (source["id"], sha, version),
    ).fetchone()


def exclusion(path, mode, size):
    p = PurePosixPath(path.lower())
    if mode not in {"100644", "100755"}:
        return "non_regular"
    if any(part.startswith(".") or part in EXCLUDED_DIRS for part in p.parts[:-1]):
        return "excluded_directory"
    if (p.name.startswith(".") or re.search(r"(?:^|[._-])(?:env|secret|credentials?|passwords?|private|dump|seed|fixture|lock)(?:[._-]|$)", p.name)
            or p.name.endswith((".min.js", ".map")) or (p.name not in RULE_FILES and p.suffix not in SOURCE_SUFFIXES)):
        return "excluded_file_type"
    if size > MAX_FILE_BYTES:
        return "file_limit"
    return None


def git_entries(directory, sha, deadline):
    tree = git(["ls-tree", "-rlz", "--full-tree", sha], directory=directory, deadline=deadline, limit=MAX_TREE_BYTES)
    for row in tree.split(b"\0")[:-1]:
        header, name = row.split(b"\t", 1)
        mode, _, oid, size = header.decode().split()
        yield name.decode("utf-8", errors="replace"), mode, oid, int(size) if size != "-" else 0


class GitHubAccessError(RepositoryError):
    pass


@contextmanager
def github_repository(source, path, deadline=None):
    owner = source["owner_id"]
    legacy_token = github_token(owner)
    connection_error = None
    try:
        app_token = connected_token(owner)
    except HTTPException as error:
        app_token, connection_error = None, str(error.detail)
    token = app_token or legacy_token
    repository = github_url(source["repository"]).removeprefix("https://github.com/")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with httpx.Client(base_url=f"https://api.github.com/repos/{repository}/", headers=headers,
                      timeout=10, trust_env=False, follow_redirects=False) as client:
        try:
            first = github_get(client, path, deadline=deadline)
        except GitHubAccessError:
            if not app_token or app_token == legacy_token:
                if connection_error:
                    raise RepositoryError(connection_error) from None
                raise
            if legacy_token:
                client.headers["Authorization"] = "Bearer " + legacy_token
            else:
                del client.headers["Authorization"]
            first = github_get(client, path, deadline=deadline)
        yield client, first


def github_get(client, path, *, deadline=None, limit=50_000, raw=False):
    remaining = deadline - time.monotonic() if deadline is not None else None
    if remaining is not None and remaining <= 0:
        raise RepositoryLimit("저장소 분석 시간이 상한을 초과했습니다.")
    try:
        headers = {"Accept": "application/vnd.github.raw+json"} if raw else {}
        with client.stream("GET", path.lstrip("/"), headers=headers,
                           timeout=10 if remaining is None else min(10, remaining)) as response:
            if response.status_code in {403, 429} and response.headers.get("X-RateLimit-Remaining") == "0":
                raise RepositoryLimit("GitHub 읽기 한도에 도달했습니다.")
            if response.status_code == 401:
                raise GitHubAccessError("GitHub 권한을 확인할 수 없습니다. GitHub를 다시 연결해 주세요.")
            if response.status_code in {403, 404}:
                raise GitHubAccessError("GitHub 저장소 또는 지정한 참조에 접근할 수 없습니다.")
            if response.status_code != 200:
                raise RepositoryError("GitHub 저장소 또는 지정한 참조에 접근할 수 없습니다.")
            data = bytearray()
            for chunk in response.iter_bytes(chunk_size=8192):
                if deadline is not None and time.monotonic() >= deadline:
                    raise RepositoryLimit("저장소 분석 시간이 상한을 초과했습니다.")
                if len(data) + len(chunk) > limit:
                    raise RepositoryLimit("GitHub 응답이 분석 상한을 초과했습니다.")
                data.extend(chunk)
        return bytes(data) if raw else json.loads(data)
    except (httpx.HTTPError, ValueError) as error:
        if (remaining is not None and isinstance(error, httpx.TimeoutException)
                and (remaining <= 10 or time.monotonic() >= deadline)):
            raise RepositoryLimit("저장소 분석 시간이 상한을 초과했습니다.") from None
        raise RepositoryError("GitHub 저장소를 읽을 수 없습니다.") from None


class RepositoryLimit(RepositoryError):
    pass


def inspect_tree(entries, read_blob, *, priorities=(), tree_truncated=False):
    candidates, excluded = [], {}
    for path, mode, oid, size in entries:
        reason = exclusion(path, mode, size)
        if not reason and ("\ufffd" in path or any(ord(ch) < 32 for ch in path) or SECRET.search(path)):
            reason = "sensitive_or_invalid_name"
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
        else:
            candidates.append((path, oid, size))
    def priority(file):
        path = file[0]
        parts = PurePosixPath(path.lower())
        return (
            parts.name not in RULE_FILES,
            not any(path == prefix or path.startswith(prefix + "/") for prefix in priorities),
            path.count("/"),
            path,
        )

    candidates.sort(key=priority)
    manifest, files = [], {}
    total = 0
    for index, (path, oid, size) in enumerate(candidates):
        if index >= MAX_FILES or total + size > MAX_TOTAL_BYTES:
            reason = "analysis_limit"
        else:
            try:
                data = read_blob(oid)
            except RepositoryLimit:
                excluded["analysis_limit"] = excluded.get("analysis_limit", 0) + len(candidates) - index
                break
            if len(data) != size:
                raise RepositoryError("고정 커밋 파일의 크기를 검증할 수 없습니다.")
            total += len(data)
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                content = None
            if content is None or "\0" in content:
                reason = "binary"
            elif SECRET.search(content):
                reason = "sensitive_content"
            else:
                digest = hashlib.sha256(data).hexdigest()
                files[path] = content
                manifest.append({"path": path, "sha256": digest, "bytes": size})
                continue
        excluded[reason] = excluded.get(reason, 0) + 1
    if tree_truncated:
        excluded["tree_truncated"] = 1
    if not files:
        raise RepositoryError("읽기 상한 안에서 분석할 수 있는 텍스트 파일이 없습니다.")
    return {"manifest": manifest, "files": files, "excluded": excluded, "bytes_read": total}


def analyze(source, snapshot):
    sha = snapshot["commit_sha"]
    if source["kind"] == "local":
        deadline = time.monotonic() + LOCAL_ANALYSIS_SECONDS
        path = local_path(source["repository"])
        local_gitdir(path, deadline)
        return inspect_tree(
            git_entries(path, sha, deadline),
            lambda oid: git(["cat-file", "blob", oid], directory=path, deadline=deadline, limit=MAX_FILE_BYTES),
            priorities=source.get("analysis_paths", []),
        )
    with github_repository(source, f"git/commits/{sha}") as (client, commit):
        tree_sha = commit["tree"]["sha"]
        tree = github_get(client, f"git/trees/{tree_sha}?recursive=1", limit=8_000_000)
        entries = (
            (item["path"], item["mode"], item["sha"], item.get("size", 0))
            for item in tree["tree"] if item["type"] != "tree"
        )

        def read_blob(oid):
            content = github_get(client, f"git/blobs/{oid}", limit=MAX_FILE_BYTES, raw=True)
            if hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest() != oid:
                raise RepositoryError("GitHub 파일의 객체 해시를 검증할 수 없습니다.")
            return content

        return inspect_tree(entries, read_blob, priorities=source.get("analysis_paths", []),
                            tree_truncated=tree.get("truncated", False))


def process_analysis(snapshot_id):
    with connect() as lease:
        lease.autocommit = True
        if not lease.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,3)) AS locked",
                             (str(snapshot_id),)).fetchone()["locked"]:
            return
        snapshot = lease.execute(
            "UPDATE studio_code_snapshots SET status='running',error=NULL "
            "WHERE id=%s AND status IN ('queued','running') RETURNING *", (snapshot_id,)
        ).fetchone()
        if not snapshot:
            return
        source = lease.execute("SELECT * FROM studio_sources WHERE id=%s", (snapshot["source_id"],)).fetchone()
        try:
            if snapshot["analysis_version"] != analysis_version(source):
                raise RepositoryError("분석 버전이 변경되었습니다. 새 스냅샷을 요청해 주세요.")
            result = analyze(source, snapshot)
        except (RepositoryError, OSError, KeyError, TypeError, ValueError) as error:
            lease.execute("UPDATE studio_code_snapshots SET status='failed',error=%s WHERE id=%s",
                          (str(error) if isinstance(error, RepositoryError) else "저장소를 읽을 수 없습니다.", snapshot_id))
        else:
            lease.execute("UPDATE studio_code_snapshots SET status='ready',analysis=%s WHERE id=%s",
                          (Jsonb(result), snapshot_id))


def planning_context(source, snapshot, request):
    """Select bounded evidence deterministically; commit content never executes."""
    analysis = snapshot["analysis"]
    words = {word.casefold() for word in re.findall(r"[\w]+", request) if len(word) >= 2}
    ranked = []
    for entry in analysis["manifest"]:
        path = entry["path"]
        lines = analysis["files"][path].split("\n")
        rule = PurePosixPath(path.lower()).name in RULE_FILES
        path_score = sum(word in path.casefold() for word in words)
        for offset in range(0, len(lines), 16):
            quote = "\n".join(lines[offset:offset + 16])
            if not quote.strip() or len(quote.encode()) > 3000 or SECRET.search(quote):
                continue
            score = path_score * 4 + sum(word in quote.casefold() for word in words)
            if rule and offset == 0:
                score += 100
            ranked.append((-score, offset, path, quote, entry["sha256"]))
    evidence, total = [], 0
    selected_paths = {}
    for _, offset, path, quote, digest in sorted(ranked):
        if selected_paths.get(path, 0) >= 3:
            continue
        end = offset + len(quote.split("\n"))
        identity = f"{snapshot['id']}:{path}:{offset + 1}:{end}"
        item = {
            "id": "code-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
            "path": path, "sha256": digest, "start_line": offset + 1,
            "end_line": end, "quote": quote,
        }
        size = len(json.dumps(item, ensure_ascii=False).encode())
        if total + size + 2 <= MAX_MODEL_BYTES and len(evidence) < 40:
            evidence.append(item)
            selected_paths[path] = selected_paths.get(path, 0) + 1
            total += size + 2
    return {
        "source_id": str(source["id"]), "snapshot_id": str(snapshot["id"]),
        "name": source["name"], "repository": source["repository"], "ref": source["ref"],
        "commit_sha": snapshot["commit_sha"], "analysis_version": snapshot["analysis_version"],
        "files_analyzed": len(analysis["manifest"]), "excluded": analysis["excluded"],
        "analysis_paths": source.get("analysis_paths", []),
        "evidence": evidence,
    }

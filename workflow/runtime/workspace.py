"""Copy approved files and collect candidate changes without altering sources."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any

from .codex_adapter import ExecutionError
from . import validate_config as validator


_PROTECTED_PARTS = {".git", ".github", ".codex", ".ssh", "node_modules", ".venv", "__pycache__"}
_PROTECTED_NAMES = {"agents.md", ".gitattributes", ".gitmodules", "auth.json", "credentials.json", "config.toml"}
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)")
_SECRET = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{16,}|"
    r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----|"
    r"(?i:bearer)\s+[A-Za-z0-9._~+/-]{12,}|"
    r"(?i:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[\"']?[^\s\"',;]{4,})"
)


def redact(text: str) -> str:
    # Known inherited secret values are only used in memory as redaction targets.
    text = _PRIVATE_KEY.sub("[REDACTED]", text)
    for key, value in os.environ.items():
        if re.search(r"TOKEN|SECRET|PASSWORD|API_KEY", key, re.I) and len(value) >= 4:
            text = text.replace(value, "[REDACTED]")
    return _SECRET.sub("[REDACTED]", text)


def protected(relative: str) -> bool:
    path = Path(relative)
    parts = {part.casefold() for part in path.parts}
    name = path.name.casefold()
    # Product tasks cannot change common automation policy, credential files,
    # Git controls, or instructions. An explicit maintenance workflow is future work.
    return bool(
        parts & _PROTECTED_PARTS or name in _PROTECTED_NAMES
        or name == ".env" or name.startswith(".env.") or name.endswith((".pem", ".key", ".p12"))
        or relative == "workflow" or relative.startswith("workflow/")
    )


def resolve(value: str, root: Path) -> Path:
    try:
        return validator._resolve_path(value, root, "project path")
    except validator.ConfigError as exc:
        raise ExecutionError("path_violation", "A configured or generated path is outside the permitted boundary.") from exc


def read_context(path: Path) -> str:
    try:
        if path.is_symlink() or not path.is_file():
            raise ExecutionError("path_violation", "Context must be an existing regular file, not a symlink.")
        data = path.read_bytes()
        if len(data) > 512 * 1024:
            raise ExecutionError("environment_error", "A context document exceeds the 512 KiB limit.")
        text = data.decode("utf-8-sig")
        if redact(text) != text:
            raise ExecutionError("path_violation", "Sensitive content was detected in a context document; execution was blocked.")
        return text
    except (OSError, UnicodeError) as exc:
        raise ExecutionError("environment_error", "Cannot read a UTF-8 context document.") from exc


def _walk_error(exc: OSError) -> None:
    raise exc


def _files(root: Path, *, source_root: Path | None = None):
    for directory, directories, files in os.walk(root, followlinks=False, onerror=_walk_error):
        if source_root is not None:
            directories[:] = [name for name in directories if not protected((Path(directory) / name).relative_to(source_root).as_posix())]
        for name in directories:
            path = Path(directory) / name
            if path.is_symlink():
                raise ExecutionError("path_violation", "Symlink directories are not permitted in the execution workspace.")
        for name in files:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode) or path.is_symlink() or path.stat().st_nlink > 1:
                raise ExecutionError("path_violation", "Symlinks, hard links and special files are not permitted.")
            yield path


def inventory(root: Path) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    total = 0
    for path in _files(root):
        relative = path.relative_to(root).as_posix()
        if redact(relative) != relative:
            raise ExecutionError("path_violation", "Sensitive filenames are not permitted in results.")
        size = path.stat().st_size
        total += size
        if len(items) >= 10000 or size > 10 * 1024 * 1024 or total > 100 * 1024 * 1024:
            raise ExecutionError("result_collection_failed", "Workspace exceeds file/size collection limits.")
        data = path.read_bytes()
        if redact(data.decode("utf-8", errors="replace")) != data.decode("utf-8", errors="replace"):
            raise ExecutionError("path_violation", "Sensitive content was detected; candidate files will not be retained.")
        items[relative] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "executable": bool(path.stat().st_mode & stat.S_IXUSR),
        }
    return items


def prepare(root: Path, destination: Path, config: dict[str, Any], config_path: Path) -> dict[str, dict[str, Any]]:
    project = resolve(config["project_root"], root)
    excluded = set(config["execution"]["instructions"]) | {config_path.relative_to(root).as_posix()}
    copied: set[str] = set()
    total = 0
    destination.mkdir(mode=0o700)
    destination.joinpath(*Path(config["project_root"]).parts).mkdir(parents=True, exist_ok=True)
    for value in config["allowed_paths"]:
        scope = resolve(value, root)
        if protected(value) or scope.is_symlink():
            raise ExecutionError("path_violation", "A writable scope includes a protected automation/credential path.")
        if not scope.is_relative_to(project):
            raise ExecutionError("path_violation", "Writable scope escapes the project.")
        if not scope.exists():
            continue
        if root.joinpath(*Path(value).parts).resolve() != root.joinpath(*Path(value).parts):
            raise ExecutionError("path_violation", "Writable scopes must not contain symlink aliases.")
        paths = _files(scope, source_root=root) if scope.is_dir() else iter([scope])
        for path in paths:
            relative = path.relative_to(root).as_posix()
            if protected(relative) or relative in excluded:
                continue
            if relative in copied:
                continue
            if not resolve(relative, root).is_relative_to(project) or path.is_symlink():
                raise ExecutionError("path_violation", "Source file escapes the project.")
            if not path.is_file() or path.stat().st_nlink > 1:
                raise ExecutionError("path_violation", "Source must be a regular file without hard links.")
            size = path.stat().st_size
            total += size
            if len(copied) >= 10000 or size > 10 * 1024 * 1024 or total > 100 * 1024 * 1024:
                raise ExecutionError("environment_error", "Approved source snapshot exceeds file/size limits.")
            copied.add(relative)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # New inodes avoid links back to the source; no copy of .git or hooks.
            target.write_bytes(path.read_bytes())
            target.chmod(0o700 if path.stat().st_mode & stat.S_IXUSR else 0o600)
    for category in ("unit", "e2e"):
        for test in config["tests"][category]:
            (destination / test["cwd"]).mkdir(parents=True, exist_ok=True)
    return inventory(destination)


def collect(destination: Path, config: dict[str, Any], before: dict[str, Any], config_path: str) -> list[dict[str, Any]]:
    if destination.is_symlink() or not destination.is_dir():
        raise ExecutionError("path_violation", "Execution workspace was replaced or removed.")
    after = inventory(destination)
    scopes = [resolve(value, destination) for value in config["allowed_paths"]]
    project = resolve(config["project_root"], destination)
    for directory, _, _ in os.walk(destination, followlinks=False, onerror=_walk_error):
        path = Path(directory)
        relative = path.relative_to(destination).as_posix()
        if path == destination:
            continue
        if protected(relative) or not any(path.is_relative_to(scope) or scope.is_relative_to(path) for scope in scopes):
            raise ExecutionError("path_violation", "Codex created a directory outside the approved paths.")
    changes = []
    for relative in sorted(before.keys() | after.keys()):
        if before.get(relative) == after.get(relative):
            continue
        path = resolve(relative, destination)
        if (
            protected(relative) or relative == config_path or relative in config["execution"]["instructions"]
            or not path.is_relative_to(project) or not any(path.is_relative_to(scope) for scope in scopes)
        ):
            raise ExecutionError("path_violation", "Codex changed a file outside the approved writable paths.")
        changes.append({
            "path": relative,
            "change": "added" if relative not in before else "deleted" if relative not in after else "modified",
            "before": before.get(relative), "after": after.get(relative),
        })
    return changes

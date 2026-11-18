"""Offline project configuration validation for Python 3.12+ (stdlib only).

Usage:
    python -B workflow/runtime/validate_config.py CONFIG --repo-root REPOSITORY

Exit codes: 0 = valid, 1 = invalid/unreadable, 2 = CLI usage error.
Incomplete .example configurations intentionally fail. Null is not a fallback.

The bundled JSON Schema is the structural source of truth. The small evaluator
supports only its keywords and local $defs references; it is NOT a general JSON
Schema implementation. Unsupported schema keywords fail closed. Semantic checks
add real-filesystem boundaries, document/cwd existence, and unique test IDs.

All config paths are repository-relative POSIX paths, including test cwd. New
allowed scopes can be absent, but project_root/cwd/documents must exist. Paths
are resolved to detect symlink escapes; run in the target filesystem (e.g. WSL
for WSL checkouts). This is not a sandbox or a patch validator and does not
prevent changes after validation. Repository identity, branch existence, tool
availability, test outcomes and remote permissions are intentionally not checked.
Commands/arguments are never executed, approved, or interpolated by this module.
"""

from __future__ import annotations

import argparse
import json
import re
import string
import sys
from pathlib import Path
from typing import Any

if __package__:
    from . import branch_rules
else:
    try:
        import branch_rules
    except ModuleNotFoundError:
        # Also support importlib file loading from the repository root.
        from workflow.runtime import branch_rules


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "project.schema.json"
SUPPORTED_SCHEMA_VERSION = 1
_KEYWORDS = {
    "$schema", "$defs", "$ref", "title", "description", "type", "const",
    "required", "properties", "additionalProperties", "items", "minItems",
    "uniqueItems", "minLength", "pattern",
}
_TYPES = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}


class ConfigError(ValueError):
    """A readable validation failure without echoing configuration contents."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("duplicate JSON object keys are not allowed")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ConfigError("non-standard JSON constants (NaN/Infinity) are not allowed")


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8-sig") as handle:
            return json.load(handle, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    except UnicodeError as exc:
        raise ConfigError("file must contain UTF-8 JSON") from exc
    except OSError as exc:
        raise ConfigError("cannot read JSON file; check its path and access permissions") from exc
    except RecursionError as exc:
        raise ConfigError("JSON nesting is too deep") from exc
    except ConfigError:
        raise
    except ValueError as exc:
        raise ConfigError("invalid JSON value (check numeric limits)") from exc


def _reference(ref: str, schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        raise ConfigError("schema supports only local #/$defs/ references")
    name = ref.removeprefix("#/$defs/")
    if "/" in name or name not in schema.get("$defs", {}):
        raise ConfigError("schema contains an unresolved reference")
    return schema["$defs"][name]


def _check_schema(node: dict[str, Any], schema: dict[str, Any]) -> None:
    """Reject schema additions that this deliberately limited evaluator cannot enforce."""
    if not isinstance(node, dict) or set(node) - _KEYWORDS:
        raise ConfigError("bundled schema contains unsupported validation keywords")
    if "type" in node and node["type"] not in _TYPES:
        raise ConfigError("bundled schema contains an unsupported type")
    if "additionalProperties" in node and node["additionalProperties"] is not False:
        raise ConfigError("schema supports only additionalProperties=false")
    if "$ref" in node:
        _reference(node["$ref"], schema)
    if "pattern" in node:
        re.compile(node["pattern"])
    for keyword in ("properties", "$defs"):
        for child in node.get(keyword, {}).values():
            _check_schema(child, schema)
    if "items" in node:
        _check_schema(node["items"], schema)


def _matches_type(value: Any, expected: str) -> bool:
    # JSON Schema integers include integral JSON numbers, but never booleans.
    if expected == "integer":
        return type(value) is int or (type(value) is float and value.is_integer())
    return type(value) is _TYPES[expected]


def _validate_node(value: Any, node: dict[str, Any], schema: dict[str, Any], location: str) -> list[str]:
    errors: list[str] = []
    if "$ref" in node:
        errors.extend(_validate_node(value, _reference(node["$ref"], schema), schema, location))
    expected = node.get("type")
    if expected is not None and not _matches_type(value, expected):
        return errors + [f"{location}: expected {expected}"]
    if "const" in node and (
        value != node["const"] or isinstance(value, bool) != isinstance(node["const"], bool)
    ):
        errors.append(f"{location}: must be {json.dumps(node['const'])}")
    if isinstance(value, dict):
        properties = node.get("properties", {})
        for key in node.get("required", []):
            if key not in value:
                errors.append(f"{location}.{key}: required field is missing")
        if node.get("additionalProperties") is False and set(value) - set(properties):
            errors.append(f"{location}: unknown fields are not allowed")
        for key, child in properties.items():
            if key in value:
                errors.extend(_validate_node(value[key], child, schema, f"{location}.{key}"))
    elif isinstance(value, list):
        if len(value) < node.get("minItems", 0):
            errors.append(f"{location}: needs at least {node['minItems']} item(s)")
        if node.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            errors.append(f"{location}: duplicate entries are not allowed")
        if "items" in node:
            for index, item in enumerate(value):
                errors.extend(_validate_node(item, node["items"], schema, f"{location}[{index}]"))
    elif isinstance(value, str):
        if len(value) < node.get("minLength", 0):
            errors.append(f"{location}: must not be empty")
        if "pattern" in node and re.search(node["pattern"], value) is None:
            errors.append(f"{location}: does not match the required format")
    return errors


def _within(path: Path, scope: Path) -> bool:
    return path.is_relative_to(scope)


def _resolve_path(value: str, root: Path, location: str) -> Path:
    parts = value.split("/")
    invalid = (
        value != value.strip()
        or value.startswith("/")
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or any(char in value for char in "\\:*?[]")
        or (value != "." and any(part in ("", ".", "..") for part in parts))
        or any(part.casefold() == ".git" for part in parts)
    )
    if invalid:
        raise ConfigError(
            f"{location}: use a normalized repository-relative POSIX path; "
            "absolute paths, traversal, .git and glob patterns are forbidden"
        )
    try:
        resolved = root.joinpath(*parts).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ConfigError(f"{location}: cannot resolve path (check symlinks and permissions)") from exc
    if not _within(resolved, root):
        raise ConfigError(f"{location}: resolved path escapes the repository (possibly through a symlink)")
    if any(part.casefold() == ".git" for part in resolved.relative_to(root).parts):
        raise ConfigError(f"{location}: resolved path enters forbidden .git metadata")
    return resolved


def _check_paths(config: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    try:
        project = _resolve_path(config["project_root"], root, "$.project_root")
        if not project.is_dir():
            raise ConfigError("$.project_root: project directory does not exist")
    except (ConfigError, OSError) as exc:
        return [str(exc) if isinstance(exc, ConfigError) else "$.project_root: cannot inspect directory"]

    scopes: list[Path] = []
    for index, value in enumerate(config["allowed_paths"]):
        location = f"$.allowed_paths[{index}]"
        try:
            scope = _resolve_path(value, root, location)
            if not _within(scope, project):
                raise ConfigError(f"{location}: path is outside project_root")
            scopes.append(scope)
        except ConfigError as exc:
            errors.append(str(exc))

    def check(value: str, location: str, *, directory: bool) -> None:
        try:
            path = _resolve_path(value, root, location)
            if not _within(path, project):
                raise ConfigError(f"{location}: path is outside project_root")
            if not any(_within(path, scope) for scope in scopes):
                raise ConfigError(f"{location}: path is outside allowed_paths")
            exists = path.is_dir() if directory else path.is_file()
            if not exists:
                kind = "test working directory" if directory else "design document file"
                raise ConfigError(f"{location}: {kind} does not exist")
        except ConfigError as exc:
            errors.append(str(exc))
        except OSError:
            errors.append(f"{location}: cannot inspect path")

    for index, value in enumerate(config["design_documents"]):
        check(value, f"$.design_documents[{index}]", directory=False)
    for category in ("unit", "e2e"):
        for index, test in enumerate(config["tests"][category]):
            check(test["cwd"], f"$.tests.{category}[{index}].cwd", directory=True)
    return errors


def _check_semantics(config: dict[str, Any], root: Path) -> list[str]:
    errors = _check_paths(config, root)
    if "publishing" in config:
        for key in ("branch_template", "manual_branch_template"):
            if key not in config["publishing"]:
                continue
            try:
                template = config["publishing"][key]
                branch_rules.template_fields(template, manual=key == "manual_branch_template")
                name = template.format(project_id=config["project_id"], run_id="00000000-0000-4000-8000-000000000000",
                                       date="26.11.17", approver="approver", issue_title="Issue-title")
                if not branch_rules.valid_name(name):
                    errors.append(f"$.publishing.{key}: generated branch must be a valid Git branch")
            except (ValueError, KeyError, IndexError):
                errors.append(f"$.publishing.{key}: invalid template; use project_id/run_id or date/approver/issue_title without format modifiers")
    seen: set[str] = set()
    for category in ("unit", "e2e"):
        for index, test in enumerate(config["tests"][category]):
            if test["id"] in seen:
                errors.append(f"$.tests.{category}[{index}].id: test IDs must be unique across categories")
            seen.add(test["id"])
            location = f"$.tests.{category}[{index}]"
            seconds = test.get("timeout_seconds", 300)
            if not 1 <= seconds <= 3600:
                errors.append(f"{location}.timeout_seconds: must be between 1 and 3600")
            condition = test.get("run_if", "always")
            if test["required"] and (condition != "always" or test.get("on_failure", "block") != "block"):
                errors.append(f"{location}: required checks cannot be skipped or use record-only failure policy")
            if condition == "never" and not test.get("skip_reason", "").strip():
                errors.append(f"{location}.skip_reason: explicit reason is required for never")
            if (condition == "changed_paths") != ("changed_paths" in test):
                errors.append(f"{location}: changed_paths condition and path list must be supplied together")
            for value in test.get("changed_paths", []):
                try:
                    path = _resolve_path(value, root, location + ".changed_paths")
                    scopes = [_resolve_path(scope, root, "$.allowed_paths") for scope in config["allowed_paths"]]
                    if not any(_within(path, scope) for scope in scopes):
                        errors.append(f"{location}.changed_paths: path is outside allowed_paths")
                except ConfigError as exc:
                    errors.append(str(exc))
    for location, branch in (
        ("$.base_branch", config["base_branch"]),
        ("$.pr_policy.target_branch", config["pr_policy"]["target_branch"]),
    ):
        if (
            ".." in branch or "//" in branch or branch.endswith(("/", "."))
            or any(part.startswith(".") or part.endswith(".lock") for part in branch.split("/"))
        ):
            errors.append(f"{location}: invalid Git branch name")
    return errors


def validate_config(config_path: str | Path, repo_root: str | Path) -> list[str]:
    """Return all available errors; an empty list means offline validation passed."""
    try:
        config = _read_json(Path(config_path))
        schema = _read_json(SCHEMA_PATH)
        _check_schema(schema, schema)
        if schema["properties"]["schema_version"].get("const") != SUPPORTED_SCHEMA_VERSION:
            raise ConfigError("bundled schema/runtime version mismatch")
        root = Path(repo_root).resolve(strict=True)
        if not root.is_dir():
            raise ConfigError("repository root must be an existing directory")
    except ConfigError as exc:
        return [str(exc)]
    except OSError:
        return ["repository root does not exist or cannot be accessed"]
    except (KeyError, TypeError, ValueError, RuntimeError, RecursionError):
        return ["invalid bundled schema or repository root"]
    if isinstance(config, dict) and "schema_version" in config:
        version = config["schema_version"]
        if _matches_type(version, "integer") and version != SUPPORTED_SCHEMA_VERSION:
            return [f"$.schema_version: unsupported schema version; expected {SUPPORTED_SCHEMA_VERSION}"]
    try:
        errors = _validate_node(config, schema, schema, "$")
        if errors:
            return errors
        return _check_semantics(config, root)
    except (RecursionError, OSError, RuntimeError, ValueError):
        return ["configuration cannot be fully validated; check nesting and filesystem access"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path, help="UTF-8 JSON project configuration")
    parser.add_argument("--repo-root", type=Path, required=True, help="explicit local repository root")
    arguments = parser.parse_args(argv)
    errors = validate_config(arguments.config, arguments.repo_root)
    if errors:
        print("FAIL: project configuration is invalid", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("PASS: offline project configuration validation (commands and remote access were not checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

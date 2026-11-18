"""Meaningful offline contract and boundary tests; no product tests or network.

Run from the repository root:
    python -B -m unittest discover -s workflow/runtime/tests -v
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "validate_config.py"
SPEC = importlib.util.spec_from_file_location("validate_config", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)
EXAMPLE = SCRIPT.parents[1] / "config" / "projects" / "prj.json.example"


class ValidateConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name) / "repo"
        self.root.mkdir()
        for directory in ("sample/src", "sample/docs", "sample/tests", "other", "sample-extra"):
            (self.root / directory).mkdir(parents=True)
        (self.root / "sample/docs/design.md").write_text("# Approved design\n", encoding="utf-8")
        (self.root / "other/design.md").write_text("# Other project\n", encoding="utf-8")
        self.path = self.root / "config.json"
        self.config = {
            "schema_version": 1,
            "configuration_status": "ready",
            "project_id": "sample",
            "repository": {"provider": "github", "owner": "example-team", "name": "sample-repo"},
            "base_branch": "main",
            "project_root": "sample",
            "allowed_paths": ["sample/src", "sample/docs", "sample/tests"],
            "design_documents": ["sample/docs/design.md"],
            "tests": {
                "unit": [{"id": "logic", "required": True, "cwd": "sample/tests",
                          "command": {"program": "python", "args": ["-m", "unittest"]}}],
                "e2e": [{"id": "journey", "required": True, "cwd": "sample/tests",
                         "command": {"program": "npm", "args": ["run", "test:e2e"]}}],
            },
            "pr_policy": {"target_branch": "main", "allow_draft_on_failure": False,
                          "require_human_approval": True, "allow_auto_merge": False},
        }

    def write(self, config=None) -> Path:
        self.path.write_text(json.dumps(self.config if config is None else config), encoding="utf-8")
        return self.path

    def errors(self) -> list[str]:
        return validator.validate_config(self.write(), self.root)

    def assert_error(self, fragment: str) -> None:
        errors = self.errors()
        self.assertTrue(errors, "invalid config unexpectedly passed")
        self.assertIn(fragment, "\n".join(errors))

    def test_valid_configuration(self):
        self.assertEqual(self.errors(), [])

    def test_second_project_needs_no_runtime_change(self):
        self.config["project_id"] = "second"
        self.config["project_root"] = "other"
        self.config["repository"]["name"] = "different-repo"
        self.config["base_branch"] = "develop"
        self.config["pr_policy"]["target_branch"] = "develop"
        self.config["allowed_paths"] = ["other"]
        self.config["design_documents"] = ["other/design.md"]
        for category in ("unit", "e2e"):
            self.config["tests"][category][0]["cwd"] = "other"
            self.config["tests"][category][0]["command"] = {"program": "custom-runner", "args": [category]}
        self.assertEqual(self.errors(), [])

    def test_repository_root_project(self):
        self.config["project_root"] = "."
        self.assertEqual(self.errors(), [])

    def test_missing_required_fields(self):
        for keys in (("project_id",), ("repository", "owner"), ("tests", "e2e"),
                     ("pr_policy", "allow_draft_on_failure")):
            with self.subTest(keys=keys):
                config = copy.deepcopy(self.config)
                target = config
                for key in keys[:-1]:
                    target = target[key]
                del target[keys[-1]]
                errors = validator.validate_config(self.write(config), self.root)
                self.assertIn("required field is missing", "\n".join(errors))

    def test_wrong_data_types(self):
        for key, value in (("allowed_paths", "sample"), ("repository", []),
                           ("schema_version", True), ("schema_version", "1"), ("schema_version", 1.5)):
            with self.subTest(key=key, value=value):
                config = copy.deepcopy(self.config)
                config[key] = value
                self.assertIn("expected", "\n".join(validator.validate_config(self.write(config), self.root)))

    def test_integral_json_number_matches_schema_integer(self):
        self.config["schema_version"] = 1.0
        self.assertEqual(self.errors(), [])

    def test_unsupported_schema_version(self):
        self.config["schema_version"] = 2
        self.assert_error("unsupported schema version")

    def test_incomplete_status_and_null(self):
        self.config["configuration_status"] = "incomplete"
        self.config["design_documents"] = None
        self.assert_error('must be "ready"')

    def test_unknown_field_rejected(self):
        self.config["unexpected"] = "not part of the contract"
        self.assert_error("unknown fields")

    def test_path_traversal_absolute_and_nonportable_paths(self):
        for value in ("../outside", "/tmp/outside", "C:/outside", "C:\\outside", "//server/share",
                      "sample/../other", "sample/./src", "sample//src", "sample/src/",
                      "sample/*", "sample/.git", "sample/src:stream", "sample/\nsecret"):
            with self.subTest(path=value):
                config = copy.deepcopy(self.config)
                config["allowed_paths"] = [value]
                errors = validator.validate_config(self.write(config), self.root)
                self.assertIn("repository-relative POSIX path", "\n".join(errors))

    def test_sibling_project_scope_rejected(self):
        self.config["allowed_paths"] = ["other"]
        self.assert_error("outside project_root")

    def test_same_prefix_is_not_a_child(self):
        self.config["allowed_paths"] = ["sample-extra"]
        self.assert_error("outside project_root")

    def test_documents_outside_allowed_scope(self):
        self.config["allowed_paths"] = ["sample/src", "sample/tests"]
        self.assert_error("$.design_documents[0]: path is outside allowed_paths")

    def test_test_cwd_outside_project(self):
        self.config["tests"]["unit"][0]["cwd"] = "other"
        self.assert_error("$.tests.unit[0].cwd: path is outside project_root")

    def test_project_directory_must_exist(self):
        self.config["project_root"] = "missing"
        self.assert_error("project directory does not exist")

    def test_document_file_must_exist(self):
        self.config["design_documents"] = ["sample/docs/missing.md"]
        self.assert_error("design document file does not exist")

    def test_document_must_be_file(self):
        self.config["design_documents"] = ["sample/docs"]
        self.assert_error("design document file does not exist")

    def test_test_cwd_must_exist(self):
        self.config["tests"]["e2e"][0]["cwd"] = "sample/tests/missing"
        self.assert_error("test working directory does not exist")

    def test_new_allowed_paths_can_be_absent(self):
        self.config["allowed_paths"].append("sample/new-module")
        self.assertEqual(self.errors(), [])

    def test_invalid_test_structures(self):
        for value in (None, [], "pytest", {"unit": [], "e2e": []},
                      {"unit": ["pytest"], "e2e": []}):
            with self.subTest(value=value):
                config = copy.deepcopy(self.config)
                config["tests"] = value
                self.assertTrue(validator.validate_config(self.write(config), self.root))

    def test_shell_string_is_not_a_command(self):
        self.config["tests"]["unit"][0]["command"] = "python -m pytest"
        self.assert_error("command: expected object")

    def test_argument_vector_must_be_strings(self):
        self.config["tests"]["unit"][0]["command"]["args"] = [42]
        self.assert_error("args[0]: expected string")

    def test_test_required_flag_must_be_boolean(self):
        self.config["tests"]["unit"][0]["required"] = "true"
        self.assert_error("required: expected boolean")

    def test_duplicate_test_id(self):
        self.config["tests"]["e2e"][0]["id"] = "logic"
        self.assert_error("test IDs must be unique")

    def test_duplicate_scopes(self):
        self.config["allowed_paths"].append("sample/src")
        self.assert_error("duplicate entries")

    def test_auto_merge_and_no_human_approval_rejected(self):
        self.config["pr_policy"]["allow_auto_merge"] = True
        self.config["pr_policy"]["require_human_approval"] = False
        self.assert_error("allow_auto_merge: must be false")
        self.assert_error("require_human_approval: must be true")

    def test_invalid_branch_names(self):
        for branch in ("bad..name", "feature//task", "feature/task.lock", "main.", "main/", "bad name"):
            with self.subTest(branch=branch):
                config = copy.deepcopy(self.config)
                config["base_branch"] = branch
                self.assertTrue(validator.validate_config(self.write(config), self.root))

    def symlink(self, source: Path, target: Path):
        try:
            source.symlink_to(target, target_is_directory=target.is_dir())
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlinks unavailable on this environment: {type(exc).__name__}")

    def test_symlink_escape_from_repository(self):
        outside = Path(self.workspace.name) / "outside"
        outside.mkdir()
        self.symlink(self.root / "sample/escape", outside)
        self.config["allowed_paths"].append("sample/escape/new-file")
        self.assert_error("escapes the repository")

    def test_symlink_escape_to_other_project(self):
        self.symlink(self.root / "sample/escape", self.root / "other")
        self.config["allowed_paths"].append("sample/escape")
        self.assert_error("outside project_root")

    def test_document_symlink_escape(self):
        self.symlink(self.root / "sample/docs/link.md", self.root / "other/design.md")
        self.config["design_documents"] = ["sample/docs/link.md"]
        self.assert_error("outside project_root")

    def test_symlink_into_git_metadata(self):
        (self.root / ".git").mkdir()
        self.symlink(self.root / "sample/metadata", self.root / ".git")
        self.config["allowed_paths"].append("sample/metadata")
        self.assert_error("forbidden .git metadata")

    def test_invalid_json_does_not_echo_contents(self):
        self.path.write_text('{"do-not-echo-this-value": }', encoding="utf-8")
        errors = validator.validate_config(self.path, self.root)
        self.assertIn("invalid JSON at line 1", "\n".join(errors))
        self.assertNotIn("do-not-echo-this-value", "\n".join(errors))

    def test_duplicate_json_keys_rejected(self):
        self.path.write_text('{"schema_version": 1, "schema_version": 2}', encoding="utf-8")
        self.assertIn("duplicate JSON object keys", "\n".join(validator.validate_config(self.path, self.root)))

    def test_nonstandard_json_rejected(self):
        self.path.write_text('{"schema_version": NaN}', encoding="utf-8")
        self.assertIn("non-standard JSON", "\n".join(validator.validate_config(self.path, self.root)))

    def test_unreadable_file(self):
        self.assertIn("cannot read JSON file", "\n".join(validator.validate_config(self.path, self.root)))

    def test_bad_encoding(self):
        self.path.write_bytes(b"\xff")
        self.assertIn("UTF-8", "\n".join(validator.validate_config(self.path, self.root)))

    def test_json_root_must_be_object(self):
        self.write([])
        self.assertIn("$: expected object", "\n".join(validator.validate_config(self.path, self.root)))

    def test_missing_repository_root(self):
        self.assertIn("repository root", "\n".join(validator.validate_config(self.write(), self.root / "missing")))

    def test_unknown_schema_keyword_fails_closed(self):
        with self.assertRaisesRegex(validator.ConfigError, "unsupported validation keywords"):
            validator._check_schema({"type": "string", "format": "uri"}, {})

    def test_external_schema_reference_is_not_fetched(self):
        with self.assertRaisesRegex(validator.ConfigError, "only local"):
            validator._check_schema({"$ref": "https://example.invalid/schema"}, {})

    def cli(self, path: Path, *extra: str):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(path), *extra],
            text=True, capture_output=True, check=False, env=os.environ.copy(),
        )

    def test_cli_valid_and_invalid_exit_codes(self):
        passed = self.cli(self.write(), "--repo-root", str(self.root))
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertIn("PASS: offline", passed.stdout)
        self.config["schema_version"] = 99
        failed = self.cli(self.write(), "--repo-root", str(self.root))
        self.assertEqual(failed.returncode, 1)
        self.assertIn("unsupported schema version", failed.stderr)

    def test_cli_requires_explicit_repository_root(self):
        result = self.cli(self.write())
        self.assertEqual(result.returncode, 2)
        self.assertIn("--repo-root", result.stderr)

    def test_prj_example_is_intentionally_blocked(self):
        result = self.cli(EXAMPLE, "--repo-root", str(self.root))
        self.assertEqual(result.returncode, 1)
        self.assertIn('configuration_status: must be "ready"', result.stderr)
        self.assertIn("design_documents: expected array", result.stderr)
        self.assertIn("command: expected object", result.stderr)


if __name__ == "__main__":
    unittest.main()

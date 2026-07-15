from __future__ import annotations

from contracts.engine.tests.fixtures import (
    Path,
    VALID_MIXED_SCHEMA,
    json,
    lint,
    requires_symlink_capability,
    run_cli,
    tempfile,
    unittest,
    write_yaml,
)


class SchemaContractSourceLinterFilesystemTests(unittest.TestCase):
    @requires_symlink_capability
    def test_schema_root_and_discovered_symlinks_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            outside = base / "outside"
            approved = base / "approved"
            outside.mkdir()
            approved.mkdir()
            outside_yaml = write_yaml(outside, "outside.yml", VALID_MIXED_SCHEMA)

            root_link = base / "root-link"
            root_link.symlink_to(outside, target_is_directory=True)
            file_link = approved / "escape.yml"
            file_link.symlink_to(outside_yaml)
            directory_link = approved / "linked-directory"
            directory_link.symlink_to(outside, target_is_directory=True)

            for path in (root_link, file_link, directory_link):
                with self.subTest(path=path.name):
                    schema_root = path if path != directory_link else approved
                    report = lint.lint_schema_contracts(
                        [schema_root], required_language="ko-KR"
                    )

                    self.assertEqual("ERROR", report["status"])
                    self.assertTrue(
                        any(
                            error["code"] == "PATH_UNSAFE" for error in report["errors"]
                        ),
                        report,
                    )
                    self.assertNotIn("루트 외부", lint.render_report(report))

    def test_parser_input_bounds_return_deterministic_json_instead_of_tracebacks(
        self,
    ) -> None:
        def nested_mapping(depth: int) -> str:
            lines = ["root:"]
            for index in range(max(depth - 1, 0)):
                lines.append(f"{'  ' * (index + 1)}level_{index}:")
            lines.append(f"{'  ' * depth}leaf: value")
            return "\n".join(lines) + "\n"

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            within_depth = write_yaml(
                root,
                "within-depth.yml",
                nested_mapping(lint.MAX_NESTING_DEPTH),
            )
            within_report = lint.lint_schema_contracts(
                [within_depth], required_language="ko-KR"
            )
            self.assertEqual("PASS", within_report["status"], within_report)

            over_limit_fixtures = {
                "file_size": "x" * (lint.MAX_FILE_BYTES + 1),
                "line_count": "# line\n" * (lint.MAX_LINE_COUNT + 1),
                "line_length": "description: " + "가" * lint.MAX_LINE_LENGTH + "\n",
                "scalar_length": (
                    "description: |\n"
                    + "  "
                    + ("가" * 1000 + "\n  ") * (lint.MAX_SCALAR_LENGTH // 1000 + 1)
                ),
                "nesting_depth": nested_mapping(lint.MAX_NESTING_DEPTH + 1),
            }
            rendered_reports: dict[str, bytes] = {}
            for name, body in over_limit_fixtures.items():
                with self.subTest(name=name):
                    path = write_yaml(root, f"{name}.yml", body)
                    report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )
                    rendered = lint.render_report(report).encode("utf-8")

                    self.assertEqual("FAIL", report["status"], report)
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertEqual(
                        ["INPUT_LIMIT_EXCEEDED"],
                        [error["code"] for error in report["errors"]],
                    )
                    self.assertNotIn(b"Traceback", rendered)
                    rendered_reports[name] = rendered

                    repeated = lint.render_report(
                        lint.lint_schema_contracts([path], required_language="ko-KR")
                    ).encode("utf-8")
                    self.assertEqual(rendered, repeated)

            self.assertEqual(set(over_limit_fixtures), set(rendered_reports))

    @requires_symlink_capability
    def test_output_rejects_input_collision_and_symlink_without_modifying_targets(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            schema_path = write_yaml(root, "schema.yml", VALID_MIXED_SCHEMA)
            original_schema = schema_path.read_bytes()

            collision = run_cli(
                "--schema-root",
                schema_path,
                "--require-language",
                "ko-KR",
                "--output",
                schema_path,
            )
            self.assertEqual(2, collision.returncode)
            self.assertEqual("", collision.stdout)
            self.assertIn("cannot write output", collision.stderr)
            self.assertEqual(original_schema, schema_path.read_bytes())

            target = root / "existing-target.json"
            target.write_text("do-not-overwrite", encoding="utf-8")
            output_link = root / "report-link.json"
            output_link.symlink_to(target)
            linked = run_cli(
                "--schema-root",
                schema_path,
                "--require-language",
                "ko-KR",
                "--output",
                output_link,
            )
            self.assertEqual(2, linked.returncode)
            self.assertEqual("", linked.stdout)
            self.assertIn("cannot write output", linked.stderr)
            self.assertEqual("do-not-overwrite", target.read_text(encoding="utf-8"))

            safe_output = root / "safe-report.json"
            successful = run_cli(
                "--schema-root",
                schema_path,
                "--require-language",
                "ko-KR",
                "--output",
                safe_output,
            )
            self.assertEqual(0, successful.returncode, successful.stderr)
            self.assertEqual(
                "PASS", json.loads(safe_output.read_text(encoding="utf-8"))["status"]
            )
            self.assertEqual([], list(root.glob(f".{safe_output.name}.*.tmp")))

    @requires_symlink_capability
    def test_output_collision_preflight_uses_raw_roots_before_early_error_reports(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            unsupported = write_yaml(
                root, "unsupported-language.yml", VALID_MIXED_SCHEMA
            )
            unsupported_bytes = unsupported.read_bytes()
            unsupported_result = run_cli(
                "--schema-root",
                unsupported,
                "--require-language",
                "en-US",
                "--output",
                unsupported,
            )
            self.assertEqual(2, unsupported_result.returncode)
            self.assertEqual("", unsupported_result.stdout)
            self.assertIn("collides", unsupported_result.stderr)
            self.assertEqual(unsupported_bytes, unsupported.read_bytes())

            partial = write_yaml(root, "partial-root.yml", VALID_MIXED_SCHEMA)
            partial_bytes = partial.read_bytes()
            partial_result = run_cli(
                "--schema-root",
                partial,
                "--schema-root",
                root / "missing-root",
                "--require-language",
                "ko-KR",
                "--output",
                partial,
            )
            self.assertEqual(2, partial_result.returncode)
            self.assertIn("collides", partial_result.stderr)
            self.assertEqual(partial_bytes, partial.read_bytes())

            target = write_yaml(root, "symlink-target.yml", VALID_MIXED_SCHEMA)
            target_bytes = target.read_bytes()
            schema_link = root / "schema-link.yml"
            schema_link.symlink_to(target)
            symlink_result = run_cli(
                "--schema-root",
                schema_link,
                "--require-language",
                "ko-KR",
                "--output",
                target,
            )
            self.assertEqual(2, symlink_result.returncode)
            self.assertIn("collides", symlink_result.stderr)
            self.assertEqual(target_bytes, target.read_bytes())

    @requires_symlink_capability
    def test_every_raw_root_path_is_collision_protected_before_suffix_or_existence_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            for name in ("valuable.txt", "valuable"):
                with self.subTest(existing=name):
                    path = root / name
                    original = b"ORIGINAL-DO-NOT-OVERWRITE\n"
                    path.write_bytes(original)
                    result = run_cli(
                        "--schema-root",
                        path,
                        "--require-language",
                        "ko-KR",
                        "--output",
                        path,
                    )
                    self.assertEqual(2, result.returncode)
                    self.assertIn("collides", result.stderr)
                    self.assertEqual(original, path.read_bytes())

            missing = root / "missing-root"
            missing_result = run_cli(
                "--schema-root",
                missing,
                "--require-language",
                "ko-KR",
                "--output",
                missing,
            )
            self.assertEqual(2, missing_result.returncode)
            self.assertIn("collides", missing_result.stderr)
            self.assertFalse(missing.exists())

            partial = root / "partial-input.txt"
            partial_bytes = b"PARTIAL-ROOT-BYTES\n"
            partial.write_bytes(partial_bytes)
            valid = write_yaml(root, "valid-partial.yml", VALID_MIXED_SCHEMA)
            partial_result = run_cli(
                "--schema-root",
                valid,
                "--schema-root",
                partial,
                "--require-language",
                "ko-KR",
                "--output",
                partial,
            )
            self.assertEqual(2, partial_result.returncode)
            self.assertIn("collides", partial_result.stderr)
            self.assertEqual(partial_bytes, partial.read_bytes())

            target = root / "alias-target.txt"
            target_bytes = b"ALIAS-TARGET-BYTES\n"
            target.write_bytes(target_bytes)
            alias = root / "alias-root"
            alias.symlink_to(target)
            alias_result = run_cli(
                "--schema-root",
                alias,
                "--require-language",
                "ko-KR",
                "--output",
                target,
            )
            self.assertEqual(2, alias_result.returncode)
            self.assertIn("collides", alias_result.stderr)
            self.assertEqual(target_bytes, target.read_bytes())

    @requires_symlink_capability
    def test_canonicalized_output_parent_symlink_is_allowed_but_leaf_symlink_remains_blocked(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            schema_path = write_yaml(root, "schema.yml", VALID_MIXED_SCHEMA)
            real_parent = root / "real-output"
            real_parent.mkdir()
            linked_parent = root / "linked-output"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            output = linked_parent / "report.json"

            result = run_cli(
                "--schema-root",
                schema_path,
                "--require-language",
                "ko-KR",
                "--output",
                output,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                "PASS", json.loads(output.read_text(encoding="utf-8"))["status"]
            )

            leaf_target = real_parent / "leaf-target.json"
            leaf_target.write_text("keep", encoding="utf-8")
            leaf_link = linked_parent / "leaf-link.json"
            leaf_link.symlink_to(leaf_target)
            blocked = run_cli(
                "--schema-root",
                schema_path,
                "--require-language",
                "ko-KR",
                "--output",
                leaf_link,
            )
            self.assertEqual(2, blocked.returncode)
            self.assertIn("output symlinks are unsupported", blocked.stderr)
            self.assertEqual("keep", leaf_target.read_text(encoding="utf-8"))

    @requires_symlink_capability
    def test_output_inside_raw_directory_is_blocked_lexically_and_canonically(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "input-root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            write_yaml(root, "schema.yml", VALID_MIXED_SCHEMA)
            valuable = write_yaml(outside, "valuable.yml", "ORIGINAL: BYTES\n")
            original = valuable.read_bytes()
            linked_directory = root / "linked-dir"
            linked_directory.symlink_to(outside, target_is_directory=True)
            destructive_output = linked_directory / "valuable.yml"

            blocked = run_cli(
                "--schema-root",
                root,
                "--require-language",
                "ko-KR",
                "--output",
                destructive_output,
            )
            self.assertEqual(2, blocked.returncode)
            self.assertIn("inside a schema root", blocked.stderr)
            self.assertEqual(original, valuable.read_bytes())

            clean_root = base / "clean-root"
            write_yaml(clean_root, "schema.yml", VALID_MIXED_SCHEMA)
            allowed_output = outside / "report.json"
            allowed = run_cli(
                "--schema-root",
                clean_root,
                "--require-language",
                "ko-KR",
                "--output",
                allowed_output,
            )
            self.assertEqual(0, allowed.returncode, allowed.stderr)
            self.assertEqual(
                "PASS", json.loads(allowed_output.read_text(encoding="utf-8"))["status"]
            )

    @requires_symlink_capability
    def test_descendant_symlink_targets_are_protected_regardless_of_suffix_or_existence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "input-root"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            write_yaml(root, "schema.yml", VALID_MIXED_SCHEMA)

            cases = (
                ("linked-file.txt", "valuable.txt"),
                ("non-yaml-link.txt", "valuable.yml"),
            )
            for link_name, target_name in cases:
                with self.subTest(link=link_name, target=target_name):
                    target = outside / target_name
                    original = f"ORIGINAL-{target_name}\n".encode("utf-8")
                    target.write_bytes(original)
                    link = root / link_name
                    link.symlink_to(target)
                    result = run_cli(
                        "--schema-root",
                        root,
                        "--require-language",
                        "ko-KR",
                        "--output",
                        target,
                    )
                    self.assertEqual(2, result.returncode)
                    self.assertIn("collides", result.stderr)
                    self.assertEqual(original, target.read_bytes())

            broken_target = outside / "future-target.txt"
            broken_link = root / "broken-link.txt"
            broken_link.symlink_to(broken_target)
            broken_result = run_cli(
                "--schema-root",
                root,
                "--require-language",
                "ko-KR",
                "--output",
                broken_target,
            )
            self.assertEqual(2, broken_result.returncode)
            self.assertIn("collides", broken_result.stderr)
            self.assertFalse(broken_target.exists())


if __name__ == "__main__":
    unittest.main()

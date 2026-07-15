from __future__ import annotations

from contracts.engine.tests.fixtures import (
    Path,
    VALID_MIXED_SCHEMA,
    errors_with_code,
    json,
    lint,
    run_cli,
    tempfile,
    unittest,
    write_yaml,
)


class SchemaContractSourceLinterResourceTests(unittest.TestCase):
    def test_duplicate_column_and_resource_report_both_source_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "duplicates.yml",
                """
                version: 2
                models:
                  - name: repeated_model
                    description: 반복 모델 설명
                    columns:
                      - name: dup_col
                        description: 첫 번째 열 설명
                      - name: dup_col
                        description: 두 번째 열 설명
                  - name: repeated_model
                    description: 두 번째 모델 설명
                """,
            )

            report = lint.lint_schema_contracts([path], required_language="ko-KR")

            self.assertEqual("FAIL", report["status"])
            duplicate_column = errors_with_code(report, "DUPLICATE_COLUMN")
            duplicate_resource = errors_with_code(report, "DUPLICATE_RESOURCE")
            self.assertEqual(1, len(duplicate_column))
            self.assertEqual(
                {
                    "code": "DUPLICATE_COLUMN",
                    "column": "dup_col",
                    "file": path.resolve().as_posix(),
                    "lines": [6, 8],
                    "message": "duplicate column 'dup_col' in model 'repeated_model'",
                    "resource_kind": "model",
                    "resource_name": "repeated_model",
                },
                duplicate_column[0],
            )
            self.assertEqual(1, len(duplicate_resource))
            self.assertEqual([3, 10], duplicate_resource[0]["lines"])
            self.assertEqual("model", duplicate_resource[0]["resource_kind"])
            self.assertEqual("repeated_model", duplicate_resource[0]["resource_name"])

    def test_description_failures_identify_exact_entity_and_field(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_yaml(
                root,
                "semantic.yml",
                """
                version: 2
                models:
                  - name: missing_model
                    columns:
                      - name: missing_column
                  - name: english_model
                    description: Human readable English description
                    columns:
                      - name: placeholder_col
                        description: TODO
                      - name: identifier_only
                        description: "`identifier_only`"
                      - name: korean_placeholder
                        description: 추후 작성
                """,
            )

            report = lint.lint_schema_contracts([root], required_language="ko-KR")

            self.assertEqual("FAIL", report["status"])
            self.assertEqual(100.0, report["summary"]["coverage_percentage"])
            keyed = {
                (
                    error["code"],
                    error["entity_kind"],
                    error["resource_name"],
                    error.get("column"),
                )
                for error in report["errors"]
                if "entity_kind" in error
            }
            self.assertEqual(
                {
                    ("MISSING_DESCRIPTION", "resource", "missing_model", None),
                    (
                        "MISSING_DESCRIPTION",
                        "column",
                        "missing_model",
                        "missing_column",
                    ),
                    ("DESCRIPTION_LANGUAGE", "resource", "english_model", None),
                    (
                        "PLACEHOLDER_DESCRIPTION",
                        "column",
                        "english_model",
                        "placeholder_col",
                    ),
                    (
                        "IDENTIFIER_ONLY_DESCRIPTION",
                        "column",
                        "english_model",
                        "identifier_only",
                    ),
                    (
                        "PLACEHOLDER_DESCRIPTION",
                        "column",
                        "english_model",
                        "korean_placeholder",
                    ),
                },
                keyed,
            )
            for error in report["errors"]:
                if "entity_kind" in error:
                    self.assertEqual("description", error["field"])

    def test_unsupported_constructs_fail_the_whole_file_without_pass_coverage(
        self,
    ) -> None:
        cases = {
            "anchor": "description: &shared 서울 설명",
            "alias": "description: *shared",
            "merge_key": "<<: *defaults",
            "tab": "\tdescription: 서울 설명",
            "nested_flow": "values: [['x']]",
            "multiline_flow": "values: [\n          'x'\n        ]",
            "unbalanced_flow": "values: ['x'",
            "malformed_indentation": "   columns:\n      - name: bad\n        description: 잘못된 들여쓰기",
            "unclassified_line": "this line has no mapping separator",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for name, construct in cases.items():
                with self.subTest(name=name):
                    path = write_yaml(
                        root,
                        f"{name}.yml",
                        f"""
                        version: 2
                        models:
                          - name: model_{name}
                            description: 정상 모델 설명
                            columns:
                              - name: value
                                description: 정상 열 설명
                                {construct}
                        """,
                    )
                    report = lint.lint_schema_contracts(
                        [path], required_language="ko-KR"
                    )
                    self.assertEqual("FAIL", report["status"])
                    self.assertEqual("FAIL", report["files"][0]["scan_status"])
                    self.assertEqual(0, report["summary"]["files_scanned"])
                    self.assertLess(report["summary"]["coverage_percentage"], 100.0)
                    self.assertTrue(
                        any(
                            error["code"] == "UNSUPPORTED_YAML"
                            for error in report["errors"]
                        ),
                        report,
                    )

    def test_resource_selection_limits_semantics_but_not_lexical_safety(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            safe_path = write_yaml(
                root,
                "safe.yml",
                """
                version: 2
                models:
                  - name: selected_model
                    description: 선택 모델 설명
                    columns:
                      - name: selected_id
                        description: 선택 식별자 설명
                  - name: ignored_model
                    description: English only and ignored semantically
                    columns:
                      - name: ignored_id
                """,
            )

            report = lint.lint_schema_contracts(
                [safe_path], resources=["selected_model"], required_language="ko-KR"
            )

            self.assertEqual("PASS", report["status"])
            self.assertEqual(
                ["selected_model"], [item["name"] for item in report["resources"]]
            )
            self.assertEqual(2, report["summary"]["description_fields_expected"])
            self.assertEqual(100.0, report["summary"]["coverage_percentage"])

            unsafe_path = write_yaml(
                root,
                "unsafe.yml",
                """
                version: 2
                models:
                  - name: selected_model
                    description: 선택 모델 설명
                  - name: ignored_model
                    description: &unsafe English ignored semantically
                """,
            )
            unsafe_report = lint.lint_schema_contracts(
                [unsafe_path], resources=["selected_model"], required_language="ko-KR"
            )
            self.assertEqual("FAIL", unsafe_report["status"])
            unsafe_file = next(
                item
                for item in unsafe_report["files"]
                if item["path"] == unsafe_path.resolve().as_posix()
            )
            self.assertEqual("FAIL", unsafe_file["scan_status"])
            self.assertLess(unsafe_report["summary"]["coverage_percentage"], 100.0)

    def test_plain_description_braces_are_not_misclassified_as_flow_collections(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = write_yaml(
                root,
                "plain-braces.yml",
                """
                version: 2
                models:
                  - name: endpoint_model
                    description: KOPIS 상세 경로 /{mt10id} 원천 모델
                    meta:
                      database: "{{ target.database }}"
                      values: ['x', 'y']
                      freshness: {count: 30, period: hour}
                    columns:
                      - name: endpoint_id
                        description: 상세 경로 식별자
                """,
            )

            report = lint.lint_schema_contracts([path], required_language="ko-KR")

            self.assertEqual("PASS", report["status"])
            self.assertEqual(100.0, report["summary"]["coverage_percentage"])

    def test_root_and_creation_order_do_not_change_json_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first"
            second = root / "second"
            write_yaml(
                second,
                "z.yaml",
                VALID_MIXED_SCHEMA.replace(
                    "gold_weather_orders", "gold_weather_orders_z"
                ),
            )
            write_yaml(
                first,
                "a.yml",
                VALID_MIXED_SCHEMA.replace(
                    "gold_weather_orders", "gold_weather_orders_a"
                ),
            )

            forward = lint.render_report(
                lint.lint_schema_contracts([first, second], required_language="ko-KR")
            )
            reverse = lint.render_report(
                lint.lint_schema_contracts([second, first], required_language="ko-KR")
            )

            self.assertEqual(forward.encode("utf-8"), reverse.encode("utf-8"))
            paths = [item["path"] for item in json.loads(forward)["files"]]
            self.assertEqual(sorted(paths), paths)

    def test_cli_exit_codes_stdout_output_file_and_invalid_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid = write_yaml(root, "valid.yml", VALID_MIXED_SCHEMA)
            invalid = write_yaml(
                root,
                "invalid.yml",
                """
                version: 2
                models:
                  - name: english_model
                    description: English only
                """,
            )

            passed = run_cli("--schema-root", valid, "--require-language", "ko-KR")
            self.assertEqual(0, passed.returncode, passed.stderr)
            self.assertEqual("", passed.stderr)
            self.assertEqual("PASS", json.loads(passed.stdout)["status"])
            self.assertIn("서울", passed.stdout)
            self.assertNotIn("\\u", passed.stdout)

            output_path = root / "report.json"
            to_file = run_cli(
                "--schema-root",
                valid,
                "--require-language",
                "ko-KR",
                "--output",
                output_path,
            )
            self.assertEqual(0, to_file.returncode, to_file.stderr)
            self.assertEqual("", to_file.stdout)
            self.assertEqual(
                "PASS", json.loads(output_path.read_text(encoding="utf-8"))["status"]
            )

            failed = run_cli("--schema-root", invalid, "--require-language", "ko-KR")
            self.assertEqual(1, failed.returncode)
            self.assertEqual("FAIL", json.loads(failed.stdout)["status"])

            missing = run_cli(
                "--schema-root", root / "does-not-exist", "--require-language", "ko-KR"
            )
            self.assertEqual(2, missing.returncode)
            self.assertEqual("ERROR", json.loads(missing.stdout)["status"])
            self.assertEqual(
                "INVALID_ROOT", json.loads(missing.stdout)["errors"][0]["code"]
            )

            bad_output = run_cli(
                "--schema-root",
                valid,
                "--require-language",
                "ko-KR",
                "--output",
                root / "missing-parent" / "report.json",
            )
            self.assertEqual(2, bad_output.returncode)
            self.assertEqual("", bad_output.stdout)
            self.assertIn("cannot write output", bad_output.stderr)


if __name__ == "__main__":
    unittest.main()

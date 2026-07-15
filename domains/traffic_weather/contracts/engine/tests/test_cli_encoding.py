from __future__ import annotations

from contracts.engine.tests.fixtures import (
    CATALOG_COMPARE_SCRIPT,
    MANIFEST_SCRIPT,
    Path,
    SCRIPT,
    VALID_MIXED_SCHEMA,
    copy,
    importlib,
    io,
    json,
    run_cli_bytes,
    tempfile,
    unittest,
    valid_catalog_pair,
    write_json_artifact,
    write_yaml,
)


class ContractCliUtf8StdoutTests(unittest.TestCase):
    def test_all_contract_clis_emit_utf8_json_under_forced_stdio_encodings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid_schema = write_yaml(root, "valid.yml", VALID_MIXED_SCHEMA)
            failing_schema = write_yaml(
                root,
                "failing.yml",
                """
                version: 2
                models:
                  - name: undocumented_model
                    description: English only
                """,
            )
            missing_schema = root / "없는-스키마-root"

            manifest, catalog = valid_catalog_pair()
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            catalog_path = write_json_artifact(root, "catalog.json", catalog)
            invalid_manifest_path = root / "invalid-manifest.json"
            invalid_manifest_path.write_text("{not json", encoding="utf-8")
            invalid_catalog_path = root / "invalid-catalog.json"
            invalid_catalog_path.write_text("{not json", encoding="utf-8")

            failing_catalog = copy.deepcopy(catalog)
            failing_catalog["nodes"]["model.weather.gold_weather_public_metric"][
                "columns"
            ].pop("request_id")
            failing_catalog_path = write_json_artifact(
                root, "failing-catalog.json", failing_catalog
            )

            cases = (
                (
                    "source_linter_pass",
                    SCRIPT,
                    ("--schema-root", valid_schema, "--require-language", "ko-KR"),
                    0,
                    "PASS",
                ),
                (
                    "source_linter_fail",
                    SCRIPT,
                    ("--schema-root", failing_schema, "--require-language", "ko-KR"),
                    1,
                    "FAIL",
                ),
                (
                    "source_linter_error",
                    SCRIPT,
                    ("--schema-root", missing_schema, "--require-language", "ko-KR"),
                    2,
                    "ERROR",
                ),
                (
                    "manifest_validator_pass",
                    MANIFEST_SCRIPT,
                    ("--manifest", manifest_path, "--require-language", "ko-KR"),
                    0,
                    "PASS",
                ),
                (
                    "manifest_validator_fail",
                    MANIFEST_SCRIPT,
                    (
                        "--manifest",
                        manifest_path,
                        "--resource",
                        "missing",
                        "--require-language",
                        "ko-KR",
                    ),
                    1,
                    "FAIL",
                ),
                (
                    "manifest_validator_error",
                    MANIFEST_SCRIPT,
                    (
                        "--manifest",
                        invalid_manifest_path,
                        "--require-language",
                        "ko-KR",
                    ),
                    2,
                    "ERROR",
                ),
                (
                    "catalog_comparator_pass",
                    CATALOG_COMPARE_SCRIPT,
                    (
                        "--manifest",
                        manifest_path,
                        "--catalog",
                        catalog_path,
                        "--require-language",
                        "ko-KR",
                    ),
                    0,
                    "PASS",
                ),
                (
                    "catalog_comparator_fail",
                    CATALOG_COMPARE_SCRIPT,
                    (
                        "--manifest",
                        manifest_path,
                        "--catalog",
                        failing_catalog_path,
                        "--require-language",
                        "ko-KR",
                    ),
                    1,
                    "FAIL",
                ),
                (
                    "catalog_comparator_error",
                    CATALOG_COMPARE_SCRIPT,
                    (
                        "--manifest",
                        manifest_path,
                        "--catalog",
                        invalid_catalog_path,
                        "--require-language",
                        "ko-KR",
                    ),
                    2,
                    "ERROR",
                ),
            )

            for python_io_encoding in ("ascii", "utf-16"):
                for name, script, arguments, expected_exit, expected_status in cases:
                    with self.subTest(
                        python_io_encoding=python_io_encoding,
                        name=name,
                    ):
                        result = run_cli_bytes(
                            script,
                            *arguments,
                            python_io_encoding=python_io_encoding,
                            cwd=root,
                        )
                        self.assertEqual(
                            expected_exit, result.returncode, result.stderr
                        )
                        self.assertEqual(b"", result.stderr)
                        rendered = result.stdout.decode("utf-8")
                        report = json.loads(rendered)
                        self.assertEqual(expected_status, report["status"])
                        self.assertTrue(rendered.endswith("\n"))
                        self.assertIn("이", rendered)
                        self.assertNotIn("\\u", rendered)
                        self.assertNotIn("Traceback", rendered)

    def test_utf8_stdout_helper_supports_string_io_fallback(self) -> None:
        artifact_io = importlib.import_module("contracts.engine.artifact_io")
        stream = io.StringIO()

        artifact_io.write_utf8_stdout("한글 계약\n", stream=stream)

        self.assertEqual("한글 계약\n", stream.getvalue())


if __name__ == "__main__":
    unittest.main()

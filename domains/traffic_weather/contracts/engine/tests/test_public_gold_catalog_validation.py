from __future__ import annotations

from contracts.engine.tests.fixtures import (
    Path,
    catalog_comparator_module,
    json,
    run_catalog_compare_cli,
    tempfile,
    unittest,
    valid_catalog_pair,
    write_json_artifact,
)


class PublicGoldCatalogValidationTests(unittest.TestCase):
    def test_complete_fixture_passes_comparison_without_promoting_physical_proof(
        self,
    ) -> None:
        manifest, catalog = valid_catalog_pair()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            catalog_path = write_json_artifact(root, "catalog.json", catalog)

            result = run_catalog_compare_cli(
                "--manifest",
                manifest_path,
                "--catalog",
                catalog_path,
                "--require-language",
                "ko-KR",
            )

        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual("PASS", report["status"])
        self.assertEqual(
            {
                "catalog_comparison": "PASS",
                "data_contract": "NOT_RUN",
                "declared_contract": "PASS",
                "manual_semantic_review": "REQUIRED",
                "physical_contract": "NOT_RUN",
                "source_yaml_uniqueness": "NOT_RUN",
            },
            report["proof"],
        )
        self.assertEqual(
            {
                "attestation": "operator_supplied_unverified",
                "evidence_id": None,
                "evidence_kind": "fixture",
                "evidence_scope": "non_dev_fixture",
            },
            report["evidence"],
        )
        self.assertEqual("", result.stderr)
        self.assertIn("물리", result.stdout)
        self.assertNotIn("\\u", result.stdout)
        self.assertNotIn("task-3a-fixture-invocation", result.stdout)
        self.assertNotIn("generated_at", result.stdout)

    def test_catalog_differences_fail_with_stable_codes_and_exact_paths(self) -> None:
        comparator = catalog_comparator_module()
        uid = "model.weather.gold_weather_public_metric"

        def missing_relation(catalog: dict[str, object]) -> None:
            catalog["sources"][uid] = catalog["nodes"].pop(uid)

        def missing_column(catalog: dict[str, object]) -> None:
            catalog["nodes"][uid]["columns"].pop("request_id")

        def extra_column(catalog: dict[str, object]) -> None:
            catalog["nodes"][uid]["columns"]["unexpected"] = {
                "index": 8,
                "name": "unexpected",
                "type": "varchar",
            }

        def incompatible_type(catalog: dict[str, object]) -> None:
            catalog["nodes"][uid]["columns"]["metric_value"]["type"] = "varchar"

        def mismatched_order(catalog: dict[str, object]) -> None:
            columns = catalog["nodes"][uid]["columns"]
            columns["district_id"]["index"] = 2
            columns["metric_value"]["index"] = 1

        cases = (
            (
                "missing_relation",
                missing_relation,
                "MISSING_PHYSICAL_RELATION",
                f"catalog.nodes.{uid}",
            ),
            (
                "missing_column",
                missing_column,
                "MISSING_PHYSICAL_COLUMN",
                f"catalog.nodes.{uid}.columns.request_id",
            ),
            (
                "extra_column",
                extra_column,
                "EXTRA_PHYSICAL_COLUMN",
                f"catalog.nodes.{uid}.columns.unexpected",
            ),
            (
                "incompatible_type",
                incompatible_type,
                "INCOMPATIBLE_COLUMN_TYPE",
                f"catalog.nodes.{uid}.columns.metric_value.type",
            ),
            (
                "mismatched_order",
                mismatched_order,
                "PHYSICAL_COLUMN_ORDER_MISMATCH",
                f"catalog.nodes.{uid}.columns.district_id.index",
            ),
        )
        for name, mutate, expected_code, expected_path in cases:
            with self.subTest(name=name):
                manifest, catalog = valid_catalog_pair()
                mutate(catalog)
                report = comparator.compare_public_gold_catalog(manifest, catalog)
                matches = [
                    error
                    for error in report["errors"]
                    if error["code"] == expected_code
                ]
                self.assertEqual("FAIL", report["status"], report)
                self.assertEqual("PASS", report["proof"]["declared_contract"])
                self.assertEqual("FAIL", report["proof"]["catalog_comparison"])
                self.assertEqual("NOT_RUN", report["proof"]["physical_contract"])
                self.assertTrue(matches, report)
                self.assertIn(expected_path, [error["path"] for error in matches])
                self.assertTrue(all(error["uid"] == uid for error in matches))

    def test_type_normalization_is_case_whitespace_and_exact_aliases_only(self) -> None:
        comparator = catalog_comparator_module()
        uid = "model.weather.gold_weather_public_metric"
        passing_pairs = (
            ("int", " INTEGER "),
            ("double precision", " DOUBLE "),
            (" decimal ( 10 , 2 ) ", "DECIMAL(10,2)"),
        )
        for declared_type, physical_type in passing_pairs:
            with self.subTest(pass_pair=(declared_type, physical_type)):
                manifest, catalog = valid_catalog_pair()
                manifest["nodes"][uid]["columns"]["metric_value"]["data_type"] = (
                    declared_type
                )
                catalog["nodes"][uid]["columns"]["metric_value"]["type"] = physical_type
                report = comparator.compare_public_gold_catalog(manifest, catalog)
                self.assertEqual("PASS", report["status"], report)

        failing_pairs = (
            ("decimal(10,2)", "decimal(12,2)", "metric_value"),
            ("varchar(32)", "varchar(64)", "metric_value"),
            ("int(10)", "integer(10)", "metric_value"),
            ("string", "varchar", "district_id"),
            (
                "timestamp(6)with time zone",
                "timestamp(6) with time zone",
                "metric_value",
            ),
            ("timestamp(6)", "timestamp(6) with time zone", "product_as_of_at"),
        )
        for declared_type, physical_type, column_name in failing_pairs:
            with self.subTest(fail_pair=(declared_type, physical_type)):
                manifest, catalog = valid_catalog_pair()
                manifest["nodes"][uid]["columns"][column_name]["data_type"] = (
                    declared_type
                )
                catalog["nodes"][uid]["columns"][column_name]["type"] = physical_type
                report = comparator.compare_public_gold_catalog(manifest, catalog)
                matches = [
                    error
                    for error in report["errors"]
                    if error["code"] == "INCOMPATIBLE_COLUMN_TYPE"
                    and error["column"] == column_name
                ]
                self.assertEqual("FAIL", report["status"], report)
                self.assertTrue(matches, report)
                self.assertEqual(declared_type, matches[0]["declared_type"])
                self.assertEqual(physical_type, matches[0]["physical_type"])

    def test_invalid_catalog_and_invocation_shapes_exit_two_without_output(
        self,
    ) -> None:
        uid = "model.weather.gold_weather_public_metric"

        def wrong_version(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"]["dbt_schema_version"] = "catalog/v2"
            return catalog

        def top_level_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            return []

        def metadata_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"] = []
            return catalog

        def nodes_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"] = []
            return catalog

        def node_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid] = []
            return catalog

        def columns_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"] = []
            return catalog

        def column_list(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"] = []
            return catalog

        def missing_type(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"].pop("type")
            return catalog

        def missing_index(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"].pop("index")
            return catalog

        def string_index(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"]["index"] = "2"
            return catalog

        def boolean_index(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"]["index"] = True
            return catalog

        def name_mismatch(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["nodes"][uid]["columns"]["metric_value"]["name"] = "other"
            return catalog

        def nonempty_errors(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["errors"] = ["adapter failure"]
            return catalog

        def missing_manifest_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            manifest["metadata"].pop("invocation_id")
            return catalog

        def missing_catalog_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"].pop("invocation_id")
            return catalog

        def blank_manifest_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            manifest["metadata"]["invocation_id"] = "   "
            return catalog

        def blank_catalog_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"]["invocation_id"] = "   "
            return catalog

        def mismatched_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            catalog["metadata"]["invocation_id"] = "unrelated-invocation"
            return catalog

        def whitespace_mismatched_invocation(
            manifest: dict[str, object], catalog: dict[str, object]
        ) -> object:
            manifest["metadata"]["invocation_id"] = (
                " " + manifest["metadata"]["invocation_id"]
            )
            return catalog

        cases = (
            (
                "version",
                wrong_version,
                "UNSUPPORTED_CATALOG_VERSION",
                "catalog.metadata.dbt_schema_version",
            ),
            ("top", top_level_list, "INVALID_ARTIFACT_SHAPE", "catalog"),
            ("metadata", metadata_list, "INVALID_ARTIFACT_SHAPE", "catalog.metadata"),
            ("nodes", nodes_list, "INVALID_ARTIFACT_SHAPE", "catalog.nodes"),
            ("node", node_list, "INVALID_ARTIFACT_SHAPE", "catalog.nodes"),
            (
                "columns",
                columns_list,
                "INVALID_ARTIFACT_SHAPE",
                f"catalog.nodes.{uid}.columns",
            ),
            (
                "column",
                column_list,
                "INVALID_ARTIFACT_SHAPE",
                f"catalog.nodes.{uid}.columns",
            ),
            (
                "type",
                missing_type,
                "INVALID_CATALOG_COLUMN_TYPE",
                f"catalog.nodes.{uid}.columns.metric_value.type",
            ),
            (
                "missing_index",
                missing_index,
                "INVALID_CATALOG_COLUMN_INDEX",
                f"catalog.nodes.{uid}.columns.metric_value.index",
            ),
            (
                "string_index",
                string_index,
                "INVALID_CATALOG_COLUMN_INDEX",
                f"catalog.nodes.{uid}.columns.metric_value.index",
            ),
            (
                "boolean_index",
                boolean_index,
                "INVALID_CATALOG_COLUMN_INDEX",
                f"catalog.nodes.{uid}.columns.metric_value.index",
            ),
            (
                "name",
                name_mismatch,
                "CATALOG_COLUMN_NAME_MISMATCH",
                f"catalog.nodes.{uid}.columns.metric_value.name",
            ),
            ("errors", nonempty_errors, "CATALOG_ERRORS_PRESENT", "catalog.errors"),
            (
                "manifest_invocation",
                missing_manifest_invocation,
                "MISSING_INVOCATION_ID",
                "manifest.metadata.invocation_id",
            ),
            (
                "catalog_invocation",
                missing_catalog_invocation,
                "MISSING_INVOCATION_ID",
                "catalog.metadata.invocation_id",
            ),
            (
                "blank_manifest_invocation",
                blank_manifest_invocation,
                "MISSING_INVOCATION_ID",
                "manifest.metadata.invocation_id",
            ),
            (
                "blank_catalog_invocation",
                blank_catalog_invocation,
                "MISSING_INVOCATION_ID",
                "catalog.metadata.invocation_id",
            ),
            (
                "invocation_mismatch",
                mismatched_invocation,
                "INVOCATION_ID_MISMATCH",
                "catalog.metadata.invocation_id",
            ),
            (
                "invocation_whitespace_mismatch",
                whitespace_mismatched_invocation,
                "INVOCATION_ID_MISMATCH",
                "catalog.metadata.invocation_id",
            ),
        )
        for name, mutate, expected_code, expected_path in cases:
            with (
                self.subTest(name=name),
                tempfile.TemporaryDirectory() as temporary_directory,
            ):
                root = Path(temporary_directory)
                manifest, catalog = valid_catalog_pair()
                catalog_value = mutate(manifest, catalog)
                manifest_path = write_json_artifact(root, "manifest.json", manifest)
                catalog_path = write_json_artifact(root, "catalog.json", catalog_value)
                output_path = root / "report.json"
                output_path.write_text("sentinel", encoding="utf-8")
                result = run_catalog_compare_cli(
                    "--manifest",
                    manifest_path,
                    "--catalog",
                    catalog_path,
                    "--require-language",
                    "ko-KR",
                    "--output",
                    output_path,
                )
                self.assertEqual(2, result.returncode, result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual("ERROR", report["status"], report)
                self.assertEqual(
                    [expected_code], [error["code"] for error in report["errors"]]
                )
                self.assertEqual(
                    [expected_path], [error["path"] for error in report["errors"]]
                )
                self.assertEqual("NOT_RUN", report["proof"]["catalog_comparison"])
                self.assertEqual("NOT_RUN", report["proof"]["physical_contract"])
                self.assertEqual("sentinel", output_path.read_text(encoding="utf-8"))
                self.assertEqual("", result.stderr)
                self.assertNotIn("Traceback", result.stdout)

    def test_index_shape_errors_are_distinct_from_comparison_failures(self) -> None:
        comparator = catalog_comparator_module()
        uid = "model.weather.gold_weather_public_metric"
        manifest, duplicate_catalog = valid_catalog_pair()
        duplicate_columns = duplicate_catalog["nodes"][uid]["columns"]
        duplicate_columns["metric_value"]["index"] = 1
        duplicate_report = comparator.compare_public_gold_catalog(
            manifest, duplicate_catalog
        )
        self.assertEqual("FAIL", duplicate_report["status"], duplicate_report)
        self.assertIn(
            "DUPLICATE_PHYSICAL_INDEX",
            [error["code"] for error in duplicate_report["errors"]],
        )
        self.assertIn(
            "NONCONTIGUOUS_PHYSICAL_INDEX",
            [error["code"] for error in duplicate_report["errors"]],
        )

        manifest, gap_catalog = valid_catalog_pair()
        gap_catalog["nodes"][uid]["columns"]["request_id"]["index"] = 8
        gap_report = comparator.compare_public_gold_catalog(manifest, gap_catalog)
        self.assertEqual("FAIL", gap_report["status"], gap_report)
        gap_errors = [
            error
            for error in gap_report["errors"]
            if error["code"] == "NONCONTIGUOUS_PHYSICAL_INDEX"
        ]
        self.assertEqual(
            [f"catalog.nodes.{uid}.columns.request_id.index"],
            [error["path"] for error in gap_errors],
        )
        self.assertEqual(7, gap_errors[0]["expected_index"])
        self.assertEqual(8, gap_errors[0]["physical_index"])

    def test_declared_failure_stops_catalog_and_physical_proof(self) -> None:
        comparator = catalog_comparator_module()
        manifest, catalog = valid_catalog_pair()
        uid = "model.weather.gold_weather_public_metric"
        manifest["nodes"][uid]["description"] = "English only"

        report = comparator.compare_public_gold_catalog(
            manifest,
            catalog,
            evidence_kind="approved_dev_catalog",
            evidence_id="review-144-run-7",
        )

        self.assertEqual("FAIL", report["status"], report)
        self.assertEqual("FAIL", report["proof"]["declared_contract"])
        self.assertEqual("NOT_RUN", report["proof"]["catalog_comparison"])
        self.assertEqual("NOT_RUN", report["proof"]["physical_contract"])
        self.assertEqual("NOT_RUN", report["proof"]["data_contract"])
        self.assertEqual(0, report["summary"]["difference_count"])
        self.assertEqual(0, report["summary"]["resources_checked"])


if __name__ == "__main__":
    unittest.main()

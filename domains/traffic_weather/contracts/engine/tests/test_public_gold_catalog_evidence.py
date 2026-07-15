from __future__ import annotations

from contracts.engine.tests.fixtures import (
    BASE_COLUMN_ORDER,
    Path,
    catalog_comparator_module,
    copy,
    json,
    run_catalog_compare_cli,
    tempfile,
    unittest,
    valid_catalog_pair,
    valid_manifest_exposure,
    valid_manifest_node,
    write_json_artifact,
)


class PublicGoldCatalogEvidenceTests(unittest.TestCase):
    def test_evidence_kind_controls_only_physical_artifact_proof(self) -> None:
        comparator = catalog_comparator_module()
        manifest, catalog = valid_catalog_pair()
        fixture = comparator.compare_public_gold_catalog(
            manifest, catalog, evidence_kind="fixture", evidence_id="fixture-7"
        )
        self.assertEqual("NOT_RUN", fixture["proof"]["physical_contract"])
        self.assertEqual("non_dev_fixture", fixture["evidence"]["evidence_scope"])

        missing_id = comparator.compare_public_gold_catalog(
            manifest, catalog, evidence_kind="approved_dev_catalog"
        )
        self.assertEqual("ERROR", missing_id["status"])
        self.assertEqual("MISSING_EVIDENCE_ID", missing_id["errors"][0]["code"])
        self.assertEqual("NOT_RUN", missing_id["proof"]["declared_contract"])

        approved = comparator.compare_public_gold_catalog(
            manifest,
            catalog,
            evidence_kind="approved_dev_catalog",
            evidence_id="review-144-run-7",
        )
        self.assertEqual("PASS", approved["proof"]["physical_contract"])
        self.assertEqual("NOT_RUN", approved["proof"]["data_contract"])
        self.assertEqual("REQUIRED", approved["proof"]["manual_semantic_review"])
        self.assertEqual("review-144-run-7", approved["evidence"]["evidence_id"])
        self.assertEqual(
            "operator_asserted_approved_dev_catalog",
            approved["evidence"]["evidence_scope"],
        )
        self.assertEqual(
            "operator_supplied_unverified", approved["evidence"]["attestation"]
        )
        self.assertIn("암호학적으로", approved["claim_limitations_ko"])

        failing_catalog = copy.deepcopy(catalog)
        failing_catalog["nodes"].pop("model.weather.gold_weather_public_metric")
        approved_failure = comparator.compare_public_gold_catalog(
            manifest,
            failing_catalog,
            evidence_kind="approved_dev_catalog",
            evidence_id="review-144-run-7",
        )
        self.assertEqual("FAIL", approved_failure["proof"]["physical_contract"])
        self.assertEqual("NOT_RUN", approved_failure["proof"]["data_contract"])

        valid_maximum_id = "A" + ("z" * 127)
        maximum_id_report = comparator.compare_public_gold_catalog(
            manifest,
            catalog,
            evidence_kind="approved_dev_catalog",
            evidence_id=valid_maximum_id,
        )
        self.assertEqual("PASS", maximum_id_report["status"], maximum_id_report)
        self.assertEqual(valid_maximum_id, maximum_id_report["evidence"]["evidence_id"])

        invalid_evidence_ids = (
            " review-144",
            "review-144 ",
            "review 144",
            "review\n144",
            "review/144",
            "review\\144",
            ".review-144",
            "-review-144",
            "review:144",
            "검토-144",
            "A" + ("z" * 128),
        )
        for invalid_evidence_id in invalid_evidence_ids:
            with self.subTest(invalid_evidence_id=repr(invalid_evidence_id)):
                rejected_id = comparator.compare_public_gold_catalog(
                    manifest,
                    catalog,
                    evidence_kind="approved_dev_catalog",
                    evidence_id=invalid_evidence_id,
                )
                self.assertEqual("ERROR", rejected_id["status"], rejected_id)
                self.assertEqual(
                    ["INVALID_EVIDENCE_ID"],
                    [error["code"] for error in rejected_id["errors"]],
                )
                self.assertIsNone(rejected_id["evidence"]["evidence_id"])
                self.assertEqual("NOT_RUN", rejected_id["proof"]["declared_contract"])
                self.assertEqual("NOT_RUN", rejected_id["proof"]["catalog_comparison"])
                self.assertEqual("NOT_RUN", rejected_id["proof"]["physical_contract"])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_json_artifact(root, "manifest.json", manifest)
            catalog_path = write_json_artifact(root, "catalog.json", catalog)
            output_path = root / "report.json"
            missing_id_result = run_catalog_compare_cli(
                "--manifest",
                manifest_path,
                "--catalog",
                catalog_path,
                "--require-language",
                "ko-KR",
                "--evidence-kind",
                "approved_dev_catalog",
                "--output",
                output_path,
            )
            self.assertEqual(2, missing_id_result.returncode, missing_id_result.stdout)
            self.assertEqual(
                "MISSING_EVIDENCE_ID",
                json.loads(missing_id_result.stdout)["errors"][0]["code"],
            )
            self.assertFalse(output_path.exists())
            self.assertEqual("", missing_id_result.stderr)

            invalid_output_path = root / "invalid-id-report.json"
            invalid_id_result = run_catalog_compare_cli(
                "--manifest",
                manifest_path,
                "--catalog",
                catalog_path,
                "--require-language",
                "ko-KR",
                "--evidence-kind",
                "approved_dev_catalog",
                "--evidence-id",
                "review/144",
                "--output",
                invalid_output_path,
            )
            self.assertEqual(2, invalid_id_result.returncode, invalid_id_result.stdout)
            invalid_id_report = json.loads(invalid_id_result.stdout)
            self.assertEqual(
                "INVALID_EVIDENCE_ID", invalid_id_report["errors"][0]["code"]
            )
            self.assertIsNone(invalid_id_report["evidence"]["evidence_id"])
            self.assertNotIn("review/144", invalid_id_result.stdout)
            self.assertFalse(invalid_output_path.exists())
            self.assertEqual("", invalid_id_result.stderr)

            preflight_result = run_catalog_compare_cli(
                "--manifest",
                root / "missing-manifest.json",
                "--catalog",
                catalog_path,
                "--require-language",
                "ko-KR",
                "--evidence-kind",
                "approved_dev_catalog",
                "--evidence-id",
                "unsafe/path",
            )
            self.assertEqual(2, preflight_result.returncode, preflight_result.stdout)
            preflight_report = json.loads(preflight_result.stdout)
            self.assertEqual(
                "INVALID_EVIDENCE_ID", preflight_report["errors"][0]["code"]
            )
            self.assertIsNone(preflight_report["evidence"]["evidence_id"])
            self.assertNotIn("unsafe/path", preflight_result.stdout)
            self.assertNotIn("MANIFEST_READ_ERROR", preflight_result.stdout)
            self.assertEqual("", preflight_result.stderr)

    def test_invalid_evidence_kind_uses_neutral_evidence_scope(self) -> None:
        comparator = catalog_comparator_module()
        manifest, catalog = valid_catalog_pair()

        report = comparator.compare_public_gold_catalog(
            manifest, catalog, evidence_kind="unsupported"
        )

        self.assertEqual("ERROR", report["status"], report)
        self.assertEqual("invalid_evidence_kind", report["evidence"]["evidence_scope"])
        self.assertEqual("unsupported", report["evidence"]["evidence_kind"])
        self.assertIsNone(report["evidence"]["evidence_id"])
        self.assertEqual(
            {
                "catalog_comparison": "NOT_RUN",
                "data_contract": "NOT_RUN",
                "declared_contract": "NOT_RUN",
                "manual_semantic_review": "REQUIRED",
                "physical_contract": "NOT_RUN",
                "source_yaml_uniqueness": "NOT_RUN",
            },
            report["proof"],
        )

    def test_catalog_errors_may_be_absent_or_empty_and_column_name_is_optional(
        self,
    ) -> None:
        comparator = catalog_comparator_module()
        uid = "model.weather.gold_weather_public_metric"
        absent = object()
        for errors_value in (absent, None, []):
            with self.subTest(errors_value=repr(errors_value)):
                manifest, catalog = valid_catalog_pair()
                if errors_value is absent:
                    catalog.pop("errors")
                else:
                    catalog["errors"] = errors_value
                catalog["nodes"][uid]["columns"]["metric_value"].pop("name")
                report = comparator.compare_public_gold_catalog(manifest, catalog)
                self.assertEqual("PASS", report["status"], report)

    def test_mapping_order_comments_and_generation_time_do_not_change_report_bytes(
        self,
    ) -> None:
        comparator = catalog_comparator_module()
        manifest, catalog = valid_catalog_pair()
        uid = "model.weather.gold_weather_public_metric"
        second_uid = "model.weather.gold_second_public_metric"
        second_node = valid_manifest_node(second_uid)
        manifest["nodes"][second_uid] = second_node
        second_catalog_node = copy.deepcopy(catalog["nodes"][uid])
        second_catalog_node["unique_id"] = second_uid
        second_catalog_node["metadata"]["name"] = second_node["name"]
        catalog["nodes"][second_uid] = second_catalog_node
        baseline = comparator.render_json(
            comparator.compare_public_gold_catalog(manifest, catalog)
        ).encode("utf-8")

        reordered_manifest = copy.deepcopy(manifest)
        reordered_manifest = dict(reversed(list(reordered_manifest.items())))
        reordered_manifest["metadata"] = dict(
            reversed(list(reordered_manifest["metadata"].items()))
        )
        reordered_manifest["nodes"] = dict(
            reversed(list(reordered_manifest["nodes"].items()))
        )
        node = reordered_manifest["nodes"][uid]
        node["columns"] = dict(reversed(list(node["columns"].items())))

        reordered_catalog = copy.deepcopy(catalog)
        reordered_catalog = dict(reversed(list(reordered_catalog.items())))
        reordered_catalog["metadata"] = dict(
            reversed(list(reordered_catalog["metadata"].items()))
        )
        reordered_catalog["metadata"]["generated_at"] = "2099-01-01T00:00:00Z"
        reordered_catalog["nodes"] = dict(
            reversed(list(reordered_catalog["nodes"].items()))
        )
        physical_node = reordered_catalog["nodes"][uid]
        physical_node["metadata"]["comment"] = "English comment is not proof"
        physical_node["columns"] = dict(
            reversed(list(physical_node["columns"].items()))
        )
        for column in physical_node["columns"].values():
            column["comment"] = "Changed catalog comment"

        reordered = comparator.render_json(
            comparator.compare_public_gold_catalog(
                reordered_manifest, reordered_catalog
            )
        ).encode("utf-8")
        self.assertEqual(baseline, reordered)
        self.assertIn("물리".encode(), reordered)
        self.assertNotIn(b"\\u", reordered)
        self.assertNotIn(b"generated_at", reordered)
        self.assertNotIn(b"Changed catalog comment", reordered)

        explicit_order_manifest = copy.deepcopy(reordered_manifest)
        explicit_order_catalog = copy.deepcopy(reordered_catalog)
        explicit_order = list(reversed(BASE_COLUMN_ORDER))
        explicit_order_manifest["nodes"][uid]["config"]["meta"]["public_gold"][
            "column_order"
        ] = explicit_order
        physical_columns = explicit_order_catalog["nodes"][uid]["columns"]
        for index, column_name in enumerate(explicit_order, start=1):
            physical_columns[column_name]["index"] = index
        explicit_report = comparator.compare_public_gold_catalog(
            explicit_order_manifest, explicit_order_catalog
        )
        self.assertEqual("PASS", explicit_report["status"], explicit_report)
        self.assertEqual(
            baseline, comparator.render_json(explicit_report).encode("utf-8")
        )

    def test_default_selection_compares_only_public_resources_and_rejects_explicit_internal(
        self,
    ) -> None:
        comparator = catalog_comparator_module()
        public_uid = "model.weather.gold_weather_public_metric"
        served_uid = "model.weather.gold_served_metric"
        internal_uid = "model.weather.gold_internal_metric"
        candidate_uid = "model.weather.gold_candidate_metric"
        manifest, catalog = valid_catalog_pair()
        served_node = valid_manifest_node(served_uid, visibility="served")
        manifest["nodes"][served_uid] = served_node
        manifest["exposures"]["exposure.weather.gold_served_metric"] = (
            valid_manifest_exposure(served_uid)
        )
        served_catalog_node = copy.deepcopy(catalog["nodes"][public_uid])
        served_catalog_node["unique_id"] = served_uid
        served_catalog_node["metadata"]["name"] = served_node["name"]
        catalog["nodes"][served_uid] = served_catalog_node
        manifest["nodes"][internal_uid] = valid_manifest_node(
            internal_uid, visibility="internal"
        )
        manifest["nodes"][candidate_uid] = valid_manifest_node(
            candidate_uid, visibility="candidate"
        )

        default_report = comparator.compare_public_gold_catalog(manifest, catalog)
        self.assertEqual("PASS", default_report["status"], default_report)
        self.assertEqual(sorted([public_uid, served_uid]), default_report["resources"])

        selected_public = comparator.compare_public_gold_catalog(
            manifest, catalog, resources=[public_uid]
        )
        self.assertEqual("PASS", selected_public["status"], selected_public)
        self.assertEqual([public_uid], selected_public["resources"])

        selected_served = comparator.compare_public_gold_catalog(
            manifest, catalog, resources=["gold_served_metric"]
        )
        self.assertEqual("PASS", selected_served["status"], selected_served)
        self.assertEqual([served_uid], selected_served["resources"])

        for selector, expected_uid in (
            (internal_uid, internal_uid),
            ("gold_candidate_metric", candidate_uid),
        ):
            with self.subTest(selector=selector):
                rejected = comparator.compare_public_gold_catalog(
                    manifest, catalog, resources=[selector]
                )
                self.assertEqual("FAIL", rejected["status"], rejected)
                self.assertEqual("PASS", rejected["proof"]["declared_contract"])
                self.assertEqual("NOT_RUN", rejected["proof"]["catalog_comparison"])
                self.assertEqual("NOT_RUN", rejected["proof"]["physical_contract"])
                self.assertEqual(
                    ["RESOURCE_NOT_PUBLISHABLE"],
                    [error["code"] for error in rejected["errors"]],
                )
                self.assertEqual(expected_uid, rejected["errors"][0]["uid"])


if __name__ == "__main__":
    unittest.main()

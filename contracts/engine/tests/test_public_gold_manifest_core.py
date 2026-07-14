from __future__ import annotations

from contracts.engine.tests.fixtures import (
    BASE_COLUMN_ORDER,
    MANIFEST_SCRIPT,
    Path,
    copy,
    json,
    manifest_validator_module,
    run_manifest_cli,
    tempfile,
    unittest,
    valid_manifest,
    valid_manifest_node,
    write_manifest,
)


class PublicGoldManifestCoreTests(unittest.TestCase):
    def test_complete_korean_manifest_passes_and_exports_readable_proof_bounded_catalog(
        self,
    ) -> None:
        self.assertTrue(
            MANIFEST_SCRIPT.is_file(), "manifest validator script is missing"
        )
        validator = manifest_validator_module()
        manifest = valid_manifest()
        manifest["future_additive_field"] = {"accepted": True}
        node = manifest["nodes"]["model.weather.gold_weather_public_metric"]
        node["config"]["meta"]["public_gold"]["future_additive_contract_field"] = "허용"

        report, catalog = validator.validate_manifest(
            manifest, required_language="ko-KR"
        )

        self.assertEqual("PASS", report["status"])
        self.assertEqual([], report["errors"])
        self.assertIsNotNone(catalog)
        self.assertEqual(
            {
                "data_contract": "NOT_RUN",
                "declared_contract": "PASS",
                "manual_semantic_review": "REQUIRED",
                "physical_contract": "NOT_RUN",
                "source_yaml_uniqueness": "NOT_RUN",
            },
            report["proof"],
        )
        self.assertEqual(report["proof"], catalog["proof"])
        self.assertIn("실제 컬럼", report["claim_limitations_ko"])
        self.assertEqual(
            "public-gold-ai-contract/v1", catalog["catalog_schema_version"]
        )
        self.assertEqual(
            ["model.weather.gold_weather_public_metric"],
            [resource["unique_id"] for resource in catalog["resources"]],
        )
        rendered = validator.render_json(catalog)
        self.assertTrue(rendered.endswith("\n"))
        self.assertIn("서울", rendered)
        self.assertNotIn("\\u", rendered)
        self.assertNotIn("generated_at", rendered)
        self.assertNotIn("credentials", rendered)
        self.assertNotIn("future_additive_contract_field", rendered)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_manifest(root, manifest)
            catalog_path = root / "catalog.json"
            result = run_manifest_cli(
                "--manifest",
                manifest_path,
                "--require-language",
                "ko-KR",
                "--output",
                catalog_path,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("PASS", json.loads(result.stdout)["status"])
            self.assertEqual("", result.stderr)
            self.assertEqual(rendered, catalog_path.read_text(encoding="utf-8"))

    def test_required_model_language_and_prose_fail_at_exact_paths(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        cases = (
            (
                "missing_product_question",
                lambda node: node["config"]["meta"]["public_gold"].pop(
                    "product_question"
                ),
                f"nodes.{uid}.config.meta.public_gold.product_question",
            ),
            (
                "wrong_language",
                lambda node: node["config"]["meta"]["public_gold"].__setitem__(
                    "documentation_language", "en-US"
                ),
                f"nodes.{uid}.config.meta.public_gold.documentation_language",
            ),
            (
                "english_model",
                lambda node: node.__setitem__(
                    "description", "English only description"
                ),
                f"nodes.{uid}.description",
            ),
            (
                "placeholder_column",
                lambda node: node["columns"]["metric_value"].__setitem__(
                    "description", "TODO"
                ),
                f"nodes.{uid}.columns.metric_value.description",
            ),
            (
                "identifier_only_column",
                lambda node: node["columns"]["metric_value"].__setitem__(
                    "description", "metric_value"
                ),
                f"nodes.{uid}.columns.metric_value.description",
            ),
        )
        for name, mutate, expected_path in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                mutate(node)
                report, catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    expected_path, [error["path"] for error in report["errors"]]
                )
                self.assertEqual("FAIL", report["proof"]["declared_contract"])

    def test_column_contract_and_metric_fields_fail_at_exact_paths(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        base = f"nodes.{uid}.columns.metric_value"
        cases = (
            (
                "description",
                lambda column: column.pop("description"),
                f"{base}.description",
            ),
            ("data_type", lambda column: column.pop("data_type"), f"{base}.data_type"),
            (
                "meta",
                lambda column: column["config"].pop("meta"),
                f"{base}.config.meta",
            ),
            (
                "unit",
                lambda column: column["config"]["meta"].pop("unit"),
                f"{base}.config.meta.unit",
            ),
            (
                "zero_meaning",
                lambda column: column["config"]["meta"].pop("zero_meaning"),
                f"{base}.config.meta.zero_meaning",
            ),
            (
                "null_meaning",
                lambda column: column["config"]["meta"].pop("null_meaning"),
                f"{base}.config.meta.null_meaning",
            ),
            (
                "aggregation_behavior",
                lambda column: column["config"]["meta"].pop("aggregation_behavior"),
                f"{base}.config.meta.aggregation_behavior",
            ),
        )
        for name, mutate, expected_path in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                mutate(node["columns"]["metric_value"])
                report, _ = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertEqual("FAIL", report["status"], report)
                self.assertIn(
                    expected_path, [error["path"] for error in report["errors"]]
                )

        for name, value, expected_path in (
            (
                "unsafe_role",
                "label",
                f"nodes.{uid}.columns.district_id.config.meta.semantic_role",
            ),
            (
                "nullable_key",
                True,
                f"nodes.{uid}.columns.district_id.config.meta.nullable",
            ),
        ):
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                key_meta = node["columns"]["district_id"]["config"]["meta"]
                key_meta["semantic_role" if name == "unsafe_role" else "nullable"] = (
                    value
                )
                report, _ = validator.validate_manifest(valid_manifest((uid, node)))
                self.assertIn(
                    expected_path, [error["path"] for error in report["errors"]]
                )

    def test_dev_pending_allows_missing_enforcement_but_enforced_status_requires_it(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        pending = valid_manifest_node(uid, contract_status="dev_pending")
        pending_report, _ = validator.validate_manifest(valid_manifest((uid, pending)))
        self.assertEqual("PASS", pending_report["status"], pending_report)

        enforced = valid_manifest_node(uid, contract_status="enforced")
        enforced_report, catalog = validator.validate_manifest(
            valid_manifest((uid, enforced))
        )
        self.assertEqual("FAIL", enforced_report["status"])
        self.assertIsNone(catalog)
        self.assertIn(
            f"nodes.{uid}.config.contract.enforced",
            [error["path"] for error in enforced_report["errors"]],
        )

        enforced["config"]["contract"] = {"enforced": True}
        passed_report, passed_catalog = validator.validate_manifest(
            valid_manifest((uid, enforced))
        )
        self.assertEqual("PASS", passed_report["status"], passed_report)
        self.assertEqual("enforced", passed_catalog["resources"][0]["contract_status"])

        legacy_fallback = valid_manifest_node(uid, contract_status="enforced")
        legacy_fallback["config"]["contract"] = {}
        legacy_fallback["contract"] = {"enforced": True}
        fallback_report, _ = validator.validate_manifest(
            valid_manifest((uid, legacy_fallback))
        )
        self.assertEqual("PASS", fallback_report["status"], fallback_report)

    def test_canonical_and_legacy_metadata_fallbacks_pass_but_conflicts_fail(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        fallback = valid_manifest_node(uid)
        fallback["meta"] = fallback["config"].pop("meta")
        column = fallback["columns"]["district_id"]
        column["meta"] = column["config"].pop("meta")
        fallback_report, _ = validator.validate_manifest(
            valid_manifest((uid, fallback))
        )
        self.assertEqual("PASS", fallback_report["status"], fallback_report)

        compatible = valid_manifest_node(uid)
        compatible["meta"] = copy.deepcopy(compatible["config"]["meta"])
        compatible_column = compatible["columns"]["district_id"]
        compatible_column["meta"] = copy.deepcopy(compatible_column["config"]["meta"])
        compatible_report, _ = validator.validate_manifest(
            valid_manifest((uid, compatible))
        )
        self.assertEqual("PASS", compatible_report["status"], compatible_report)

        node_conflict = copy.deepcopy(compatible)
        node_conflict["meta"]["public_gold"]["product_question"] = (
            "서로 다른 질문입니다."
        )
        conflict_report, _ = validator.validate_manifest(
            valid_manifest((uid, node_conflict))
        )
        self.assertIn(
            f"nodes.{uid}.config.meta.public_gold",
            [error["path"] for error in conflict_report["errors"]],
        )

        column_conflict = copy.deepcopy(compatible)
        column_conflict["columns"]["district_id"]["meta"]["semantic_role"] = "label"
        conflict_report, _ = validator.validate_manifest(
            valid_manifest((uid, column_conflict))
        )
        self.assertIn(
            f"nodes.{uid}.columns.district_id.config.meta.semantic_role",
            [error["path"] for error in conflict_report["errors"]],
        )

    def test_all_visibilities_are_validated_but_only_public_producers_are_exported(
        self,
    ) -> None:
        validator = manifest_validator_module()
        nodes = []
        for visibility in ("internal", "candidate", "published_producer", "served"):
            uid = f"model.weather.gold_{visibility}"
            nodes.append((uid, valid_manifest_node(uid, visibility=visibility)))
        report, catalog = validator.validate_manifest(valid_manifest(*nodes))
        self.assertEqual("PASS", report["status"], report)
        self.assertEqual(
            ["model.weather.gold_published_producer", "model.weather.gold_served"],
            [resource["unique_id"] for resource in catalog["resources"]],
        )

        nodes[0][1]["description"] = "English invalid internal model"
        invalid_report, invalid_catalog = validator.validate_manifest(
            valid_manifest(*nodes)
        )
        self.assertEqual("FAIL", invalid_report["status"])
        self.assertIsNone(invalid_catalog)

    def test_manifest_order_does_not_change_catalog_bytes(self) -> None:
        validator = manifest_validator_module()
        first_uid = "model.weather.gold_a"
        second_uid = "model.weather.gold_b"
        first_node = valid_manifest_node(first_uid, visibility="served")
        second_node = valid_manifest_node(second_uid)
        forward = valid_manifest((first_uid, first_node), (second_uid, second_node))
        reverse = copy.deepcopy(forward)
        reverse["nodes"] = dict(reversed(list(reverse["nodes"].items())))
        for node in reverse["nodes"].values():
            node["columns"] = dict(reversed(list(node["columns"].items())))
            node["depends_on"]["nodes"] = list(reversed(node["depends_on"]["nodes"]))

        forward_report, forward_catalog = validator.validate_manifest(forward)
        reverse_report, reverse_catalog = validator.validate_manifest(reverse)
        self.assertEqual("PASS", forward_report["status"])
        self.assertEqual("PASS", reverse_report["status"])
        forward_bytes = validator.render_json(forward_catalog).encode("utf-8")
        reverse_bytes = validator.render_json(reverse_catalog).encode("utf-8")
        self.assertEqual(forward_bytes, reverse_bytes)
        self.assertEqual(
            BASE_COLUMN_ORDER,
            forward_catalog["resources"][0]["public_gold"].get("column_order"),
        )
        self.assertEqual(
            BASE_COLUMN_ORDER,
            reverse_catalog["resources"][0]["public_gold"].get("column_order"),
        )
        self.assertIn("서울".encode(), forward_bytes)
        self.assertNotIn(b"\\u", forward_bytes)

    def test_column_order_is_required_distinct_and_matches_declared_columns_exactly(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        base_path = f"nodes.{uid}.config.meta.public_gold.column_order"

        def missing(value: dict[str, object]) -> None:
            value.pop("column_order")

        def invalid_type(value: dict[str, object]) -> None:
            value["column_order"] = {"district_id": 1}

        def blank_item(value: dict[str, object]) -> None:
            value["column_order"].append(" ")

        def duplicate_item(value: dict[str, object]) -> None:
            value["column_order"].append("district_id")

        def missing_column(value: dict[str, object]) -> None:
            value["column_order"].remove("request_id")

        def extra_column(value: dict[str, object]) -> None:
            value["column_order"].append("not_declared")

        cases = (
            ("missing", missing, base_path),
            ("invalid_type", invalid_type, base_path),
            ("blank_item", blank_item, f"{base_path}[7]"),
            ("duplicate", duplicate_item, f"{base_path}[7]"),
            ("missing_column", missing_column, base_path),
            ("extra_column", extra_column, f"{base_path}[7]"),
        )
        for name, mutate, expected_path in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                mutate(node["config"]["meta"]["public_gold"])
                report, catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    expected_path, [error["path"] for error in report["errors"]]
                )

    def test_column_order_controls_exported_columns_without_mapping_order_inference(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        declared_order = list(reversed(BASE_COLUMN_ORDER))
        node["config"]["meta"]["public_gold"]["column_order"] = declared_order
        node["columns"] = dict(reversed(list(node["columns"].items())))

        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))

        self.assertEqual("PASS", report["status"], report)
        self.assertEqual(
            declared_order,
            [column["name"] for column in catalog["resources"][0]["columns"]],
        )
        self.assertEqual(
            declared_order,
            catalog["resources"][0]["public_gold"]["column_order"],
        )

    def test_selectors_resolve_uniquely_and_missing_or_ambiguous_are_contract_failures(
        self,
    ) -> None:
        validator = manifest_validator_module()
        first_uid = "model.weather.package_a"
        second_uid = "model.other.package_b"
        first = valid_manifest_node(first_uid, name="shared")
        second = valid_manifest_node(second_uid, name="shared")
        manifest = valid_manifest((first_uid, first), (second_uid, second))

        selected_report, selected_catalog = validator.validate_manifest(
            manifest, resources=[first_uid]
        )
        self.assertEqual("PASS", selected_report["status"])
        self.assertEqual(
            [first_uid], [item["unique_id"] for item in selected_catalog["resources"]]
        )

        for selector, code in (
            ("missing", "RESOURCE_NOT_FOUND"),
            ("shared", "RESOURCE_AMBIGUOUS"),
        ):
            with self.subTest(selector=selector):
                report, catalog = validator.validate_manifest(
                    manifest, resources=[selector]
                )
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(code, [error["code"] for error in report["errors"]])

    def test_artifact_shape_and_cli_io_errors_use_exit_two_without_partial_catalog(
        self,
    ) -> None:
        validator = manifest_validator_module()
        for name, manifest in (
            (
                "wrong_v12",
                {**valid_manifest(), "metadata": {"dbt_schema_version": "v11"}},
            ),
            ("nodes_list", {**valid_manifest(), "nodes": []}),
            ("exposures_list", {**valid_manifest(), "exposures": []}),
        ):
            with self.subTest(name=name):
                report, catalog = validator.validate_manifest(manifest)
                self.assertEqual("ERROR", report["status"], report)
                self.assertIsNone(catalog)
                self.assertEqual("FAIL", report["proof"]["declared_contract"])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            invalid_json = root / "invalid.json"
            invalid_json.write_text("{not json", encoding="utf-8")
            invalid_result = run_manifest_cli(
                "--manifest", invalid_json, "--require-language", "ko-KR"
            )
            self.assertEqual(2, invalid_result.returncode, invalid_result.stderr)
            self.assertEqual("ERROR", json.loads(invalid_result.stdout)["status"])

            manifest_path = write_manifest(root, valid_manifest())
            missing_result = run_manifest_cli(
                "--manifest",
                manifest_path,
                "--resource",
                "missing",
                "--require-language",
                "ko-KR",
            )
            self.assertEqual(1, missing_result.returncode, missing_result.stderr)
            self.assertEqual("FAIL", json.loads(missing_result.stdout)["status"])

            bad_output = root / "missing-parent" / "catalog.json"
            output_result = run_manifest_cli(
                "--manifest",
                manifest_path,
                "--require-language",
                "ko-KR",
                "--output",
                bad_output,
            )
            self.assertEqual(2, output_result.returncode)
            self.assertEqual("ERROR", json.loads(output_result.stdout)["status"])
            self.assertFalse(bad_output.exists())


if __name__ == "__main__":
    unittest.main()

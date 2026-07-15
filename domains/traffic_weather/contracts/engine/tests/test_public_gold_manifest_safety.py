from __future__ import annotations

from contracts.engine.tests.fixtures import (
    Path,
    copy,
    json,
    manifest_validator_module,
    os,
    run_manifest_cli,
    tempfile,
    unittest,
    valid_manifest,
    valid_manifest_node,
    write_escaped_json_artifact,
    write_manifest,
)


class PublicGoldManifestSafetyTests(unittest.TestCase):
    def test_recursive_export_boundary_rejects_forbidden_keys_and_absolute_paths(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        base = f"nodes.{uid}.config.meta.public_gold.quality"
        cases = (
            (
                "generated_at",
                {"checks": [{"generated_at": "2026-07-12T00:00:00Z"}]},
                f"{base}.checks[0].generated_at",
            ),
            (
                "credentials",
                {"checks": [{"credentials": "value"}]},
                f"{base}.checks[0].credentials",
            ),
            ("token", {"auth": [{"token": "value"}]}, f"{base}.auth[0].token"),
            ("secret", {"auth": [{"secret": "value"}]}, f"{base}.auth[0].secret"),
            (
                "access_key",
                {"auth": [{"access_key": "value"}]},
                f"{base}.auth[0].access_key",
            ),
            (
                "environment_schema",
                {"targets": [{"environment_schema": "dev_user"}]},
                f"{base}.targets[0].environment_schema",
            ),
            (
                "absolute_path_key",
                {"files": [{"absolute_path": "relative.json"}]},
                f"{base}.files[0].absolute_path",
            ),
            (
                "absolute_path_value",
                {"files": [{"reference": "/private/tmp/contract.json"}]},
                f"{base}.files[0].reference",
            ),
        )
        for name, unsafe_quality, expected_path in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                node["config"]["meta"]["public_gold"]["quality"] = unsafe_quality
                report, catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    expected_path, [error["path"] for error in report["errors"]]
                )

        safe = valid_manifest((uid, valid_manifest_node(uid)))
        safe["future_additive_manifest_field"] = {
            "generated_at": "manifest additive fields are not exported"
        }
        safe_report, safe_catalog = validator.validate_manifest(safe)
        self.assertEqual("PASS", safe_report["status"], safe_report)
        self.assertNotIn(
            "future_additive_manifest_field", validator.render_json(safe_catalog)
        )

    def test_conflict_equality_distinguishes_json_booleans_from_numbers_deeply(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        node = valid_manifest_node(uid)
        node["config"]["meta"]["public_gold"]["quality"]["future_rules"] = [
            {"enabled": True}
        ]
        node["meta"] = copy.deepcopy(node["config"]["meta"])
        node["meta"]["public_gold"]["quality"]["future_rules"][0]["enabled"] = 1
        report, _ = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertIn(
            "CONFLICTING_METADATA", [error["code"] for error in report["errors"]]
        )

        column_node = valid_manifest_node(uid)
        column = column_node["columns"]["district_id"]
        column["config"]["meta"]["details"] = [{"enabled": True}]
        column["meta"] = copy.deepcopy(column["config"]["meta"])
        column["meta"]["details"][0]["enabled"] = 1
        report, _ = validator.validate_manifest(valid_manifest((uid, column_node)))
        self.assertIn(
            f"nodes.{uid}.columns.district_id.config.meta.details",
            [error["path"] for error in report["errors"]],
        )

        numeric_node = valid_manifest_node(uid)
        numeric_node["config"]["meta"]["public_gold"]["quality"]["future_threshold"] = 1
        numeric_node["meta"] = copy.deepcopy(numeric_node["config"]["meta"])
        numeric_node["meta"]["public_gold"]["quality"]["future_threshold"] = 1.0
        numeric_report, _ = validator.validate_manifest(
            valid_manifest((uid, numeric_node))
        )
        self.assertEqual("PASS", numeric_report["status"], numeric_report)

    def test_fallback_validation_errors_retain_actual_metadata_and_contract_paths(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        legacy_column_node = valid_manifest_node(uid)
        legacy_metric = legacy_column_node["columns"]["metric_value"]
        legacy_metric["meta"] = legacy_metric["config"].pop("meta")
        legacy_metric["meta"].pop("unit")
        legacy_report, _ = validator.validate_manifest(
            valid_manifest((uid, legacy_column_node))
        )
        self.assertIn(
            f"nodes.{uid}.columns.metric_value.meta.unit",
            [error["path"] for error in legacy_report["errors"]],
        )

        canonical_column_node = valid_manifest_node(uid)
        canonical_column_node["columns"]["metric_value"]["config"]["meta"].pop("unit")
        canonical_report, _ = validator.validate_manifest(
            valid_manifest((uid, canonical_column_node))
        )
        self.assertIn(
            f"nodes.{uid}.columns.metric_value.config.meta.unit",
            [error["path"] for error in canonical_report["errors"]],
        )

        legacy_contract_node = valid_manifest_node(uid, contract_status="enforced")
        legacy_contract_node["contract"] = {"enforced": False}
        contract_report, _ = validator.validate_manifest(
            valid_manifest((uid, legacy_contract_node))
        )
        self.assertIn(
            f"nodes.{uid}.contract.enforced",
            [error["path"] for error in contract_report["errors"]],
        )

    def test_output_error_preserves_successful_declared_contract_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_manifest(root, valid_manifest())
            result = run_manifest_cli(
                "--manifest",
                manifest_path,
                "--require-language",
                "ko-KR",
                "--output",
                root / "missing-parent" / "catalog.json",
            )
            self.assertEqual(2, result.returncode)
            report = json.loads(result.stdout)
            self.assertEqual("ERROR", report["status"])
            self.assertEqual("PASS", report["proof"]["declared_contract"])

            invalid = root / "invalid.json"
            invalid.write_text("{invalid", encoding="utf-8")
            invalid_result = run_manifest_cli(
                "--manifest", invalid, "--require-language", "ko-KR"
            )
            self.assertEqual(2, invalid_result.returncode)
            self.assertEqual(
                "FAIL", json.loads(invalid_result.stdout)["proof"]["declared_contract"]
            )

    def test_output_rejects_existing_hard_link_identity_without_mutating_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest_path = write_manifest(root, valid_manifest())
            original = manifest_path.read_bytes()
            hard_link = root / "catalog-hard-link.json"
            os.link(manifest_path, hard_link)

            result = run_manifest_cli(
                "--manifest",
                manifest_path,
                "--require-language",
                "ko-KR",
                "--output",
                hard_link,
            )

            self.assertEqual(2, result.returncode, result.stdout)
            self.assertEqual(original, manifest_path.read_bytes())
            self.assertEqual(original, hard_link.read_bytes())
            self.assertEqual(
                "PASS", json.loads(result.stdout)["proof"]["declared_contract"]
            )

    def test_json_preflight_rejects_nonfinite_depth_and_container_limits_without_output_mutation(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        nonfinite = valid_manifest((uid, valid_manifest_node(uid)))
        nonfinite["nodes"][uid]["config"]["meta"]["public_gold"]["quality"] = {
            "threshold": float("nan")
        }
        report, catalog = validator.validate_manifest(nonfinite)
        self.assertEqual("ERROR", report["status"], report)
        self.assertIsNone(catalog)
        self.assertIn(
            f"nodes.{uid}.config.meta.public_gold.quality.threshold",
            [error["path"] for error in report["errors"]],
        )
        with self.assertRaises(ValueError):
            validator.render_json({"not_finite": float("inf")})

        too_deep = valid_manifest()
        cursor: dict[str, object] = {}
        too_deep["future_deep"] = cursor
        for index in range(70):
            child: dict[str, object] = {}
            cursor[f"level_{index}"] = child
            cursor = child
        depth_report, _ = validator.validate_manifest(too_deep)
        self.assertEqual("ERROR", depth_report["status"], depth_report)
        self.assertIn(
            "JSON_LIMIT_EXCEEDED", [error["code"] for error in depth_report["errors"]]
        )

        production_sized = valid_manifest()
        production_sized["future_many"] = [{} for _ in range(11_500)]
        production_sized_report, _ = validator.validate_manifest(production_sized)
        self.assertEqual(
            "PASS", production_sized_report["status"], production_sized_report
        )

        too_many = valid_manifest()
        too_many["future_many"] = [
            {} for _ in range(validator.MAX_JSON_CONTAINERS + 100)
        ]
        count_report, _ = validator.validate_manifest(too_many)
        self.assertEqual("ERROR", count_report["status"], count_report)
        self.assertIn(
            "JSON_LIMIT_EXCEEDED", [error["code"] for error in count_report["errors"]]
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "catalog.json"
            output.write_text("KEEP", encoding="utf-8")
            for constant in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(constant=constant):
                    manifest_path = (
                        root / f"manifest-{constant.replace('-', 'minus')}.json"
                    )
                    body = json.dumps(valid_manifest(), ensure_ascii=False)
                    body = body[:-1] + f', "future_nonfinite": {constant}' + "}"
                    manifest_path.write_text(body, encoding="utf-8")
                    result = run_manifest_cli(
                        "--manifest",
                        manifest_path,
                        "--require-language",
                        "ko-KR",
                        "--output",
                        output,
                    )
                    self.assertEqual(2, result.returncode, result.stdout)
                    self.assertEqual("ERROR", json.loads(result.stdout)["status"])
                    self.assertEqual("KEEP", output.read_text(encoding="utf-8"))

    def test_manifest_json_preflight_rejects_lone_surrogate_values_and_keys(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            cases = []
            value_manifest = valid_manifest()
            value_manifest["future_surrogate"] = "\ud800"
            cases.append(("value", value_manifest))
            key_manifest = valid_manifest()
            key_manifest["future_mapping"] = {"\ud800": True}
            cases.append(("key", key_manifest))
            for name, manifest in cases:
                with self.subTest(name=name):
                    manifest_path = write_escaped_json_artifact(
                        root, f"manifest-surrogate-{name}.json", manifest
                    )
                    self.assertIn("\\ud800", manifest_path.read_text(encoding="utf-8"))
                    output = root / f"catalog-surrogate-{name}.json"
                    output.write_text("KEEP", encoding="utf-8")

                    result = run_manifest_cli(
                        "--manifest",
                        manifest_path,
                        "--require-language",
                        "ko-KR",
                        "--output",
                        output,
                    )

                    self.assertEqual(2, result.returncode, result.stdout)
                    report = json.loads(result.stdout)
                    self.assertEqual("ERROR", report["status"])
                    self.assertEqual(
                        ["INVALID_JSON_VALUE"],
                        [error["code"] for error in report["errors"]],
                    )
                    self.assertEqual(
                        result.stdout,
                        result.stdout.encode("utf-8").decode("utf-8"),
                    )
                    self.assertNotIn("\\ud800", result.stdout.casefold())
                    self.assertEqual("KEEP", output.read_text(encoding="utf-8"))
                    self.assertEqual("", result.stderr)
                    self.assertNotIn("Traceback", result.stdout)

    def test_catalog_omits_structured_metadata_not_yet_validated_by_task_2b1(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        public_gold = node["config"]["meta"]["public_gold"]
        public_gold["quality"]["future_unvalidated"] = {
            "updated_at": "2026-07-12T12:34:56Z",
            "target_schema": "dev_user",
            "auth_value": "opaque-but-not-validated",
        }
        public_gold["lineage"]["future_unvalidated"] = {
            "timestamp": "2026-07-12T12:34:56+09:00"
        }

        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))

        self.assertEqual("PASS", report["status"], report)
        rendered = validator.render_json(catalog)
        for forbidden_literal in (
            "future_unvalidated",
            "updated_at",
            "target_schema",
            "auth_value",
            "2026-07-12T12:34:56Z",
            "2026-07-12T12:34:56+09:00",
        ):
            self.assertNotIn(forbidden_literal, rendered)
        exported_public_gold = catalog["resources"][0]["public_gold"]
        self.assertFalse(
            {
                "future_unvalidated",
                "updated_at",
                "target_schema",
                "auth_value",
                "timestamp",
            }
            & exported_public_gold.keys()
        )

    def test_node_legacy_public_gold_fallback_requires_config_meta_key_to_be_absent(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        legacy_meta = node["config"]["meta"]
        node["config"]["meta"] = {"unrelated": "canonical metadata exists"}
        node["meta"] = legacy_meta
        manifest = valid_manifest((uid, node))

        report, catalog = validator.validate_manifest(manifest, resources=[uid])

        self.assertEqual("FAIL", report["status"], report)
        self.assertIsNone(catalog)
        self.assertIn(
            "RESOURCE_NOT_FOUND", [error["code"] for error in report["errors"]]
        )

        unselected_report, unselected_catalog = validator.validate_manifest(manifest)
        self.assertEqual("PASS", unselected_report["status"], unselected_report)
        self.assertEqual([], unselected_catalog["resources"])

        conflict = valid_manifest_node(uid)
        conflict["meta"] = copy.deepcopy(conflict["config"]["meta"])
        conflict["meta"]["public_gold"]["owner"] = "다른 운영팀"
        conflict_report, _ = validator.validate_manifest(
            valid_manifest((uid, conflict))
        )
        self.assertIn(
            "CONFLICTING_METADATA",
            [error["code"] for error in conflict_report["errors"]],
        )

    def test_non_primary_column_nullable_must_be_boolean_when_present(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        meta = node["columns"]["metric_value"]["config"]["meta"]
        meta["semantic_role"] = "label"
        meta["nullable"] = {"declared": False}
        for field in ("unit", "zero_meaning", "aggregation_behavior"):
            meta.pop(field)

        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))

        self.assertEqual("FAIL", report["status"], report)
        self.assertIsNone(catalog)
        self.assertIn(
            f"nodes.{uid}.columns.metric_value.config.meta.nullable",
            [error["path"] for error in report["errors"]],
        )

    def test_nonmetric_optional_semantic_fields_reject_structured_values(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        cases = (
            ("unit", {"name": "건"}),
            ("zero_meaning", ["값이 없음"]),
            ("aggregation_behavior", {"mode": "none"}),
        )
        for field, invalid_value in cases:
            with self.subTest(field=field):
                node = valid_manifest_node(uid)
                meta = node["columns"]["metric_value"]["config"]["meta"]
                meta["semantic_role"] = "label"
                for optional in ("unit", "zero_meaning", "aggregation_behavior"):
                    meta.pop(optional)
                meta[field] = invalid_value

                report, catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )

                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    f"nodes.{uid}.columns.metric_value.config.meta.{field}",
                    [error["path"] for error in report["errors"]],
                )

    def test_nonmetric_valid_optional_scalars_export_only_validated_scalars(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        meta = node["columns"]["metric_value"]["config"]["meta"]
        meta.update(
            {
                "aggregation_behavior": "none",
                "nullable": True,
                "semantic_role": "label",
                "unit": "코드",
                "zero_meaning": "값이 0이면 해당 코드가 없음을 뜻합니다.",
            }
        )
        node["config"]["meta"]["public_gold"]["metrics"] = {}

        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))

        self.assertEqual("PASS", report["status"], report)
        exported = next(
            column
            for column in catalog["resources"][0]["columns"]
            if column["name"] == "metric_value"
        )["meta"]
        self.assertEqual(
            {
                "aggregation_behavior": "none",
                "null_meaning": "원천에서 지표를 제공하지 않은 상태입니다.",
                "nullable": True,
                "semantic_role": "label",
                "unit": "코드",
                "zero_meaning": "값이 0이면 해당 코드가 없음을 뜻합니다.",
            },
            exported,
        )
        self.assertTrue(
            all(isinstance(value, (str, bool)) for value in exported.values())
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from contracts.engine.tests.fixtures import (
    copy,
    manifest_validator_module,
    unittest,
    valid_join_metadata,
    valid_manifest,
    valid_manifest_exposure,
    valid_manifest_node,
    valid_reconciliation_test,
)


class PublicGoldManifestPublicationTests(unittest.TestCase):
    def test_published_producer_requires_truthful_publication_metadata_and_no_exposure(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid, visibility="published_producer")
        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertEqual("PASS", report["status"], report)
        exported = catalog["resources"][0]["public_gold"]
        self.assertIn("exposure_status", exported)
        self.assertEqual("none_no_live_consumer", exported["exposure_status"])
        self.assertEqual(["ai_catalog", "analyst"], exported["intended_consumer_types"])
        self.assertEqual(2, len(exported["cross_domain_usage_examples"]))

        cases = (
            (
                "consumers",
                lambda pg: pg.pop("intended_consumer_types"),
                "intended_consumer_types",
            ),
            (
                "status",
                lambda pg: pg.__setitem__("exposure_status", "active_exposure"),
                "exposure_status",
            ),
            (
                "examples_count",
                lambda pg: pg.__setitem__(
                    "cross_domain_usage_examples", ["한 개 예시입니다."]
                ),
                "cross_domain_usage_examples",
            ),
            (
                "examples_language",
                lambda pg: pg.__setitem__(
                    "cross_domain_usage_examples",
                    ["English example", "두 번째 예시입니다."],
                ),
                "cross_domain_usage_examples[0]",
            ),
        )
        for name, mutate, field in cases:
            with self.subTest(name=name):
                invalid = valid_manifest_node(uid, visibility="published_producer")
                mutate(invalid["config"]["meta"]["public_gold"])
                invalid_report, invalid_catalog = validator.validate_manifest(
                    valid_manifest((uid, invalid))
                )
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(
                    any(
                        error["path"].endswith(field)
                        for error in invalid_report["errors"]
                    ),
                    invalid_report,
                )

        invented = valid_manifest((uid, valid_manifest_node(uid)))
        invented["exposures"]["exposure.weather.invented_app"] = (
            valid_manifest_exposure(uid)
        )
        invented_report, invented_catalog = validator.validate_manifest(invented)
        self.assertEqual("FAIL", invented_report["status"], invented_report)
        self.assertIsNone(invented_catalog)

    def test_internal_and_candidate_require_no_manifest_exposure(self) -> None:
        validator = manifest_validator_module()
        for visibility in ("internal", "candidate"):
            with self.subTest(visibility=visibility):
                uid = f"model.weather.gold_{visibility}"
                node = valid_manifest_node(uid, visibility=visibility)
                manifest = valid_manifest((uid, node))
                manifest["exposures"][f"exposure.weather.{visibility}"] = (
                    valid_manifest_exposure(uid)
                )
                report, catalog = validator.validate_manifest(manifest)
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    "UNEXPECTED_EXPOSURE", [error["code"] for error in report["errors"]]
                )

    def test_served_requires_real_valid_exposure_and_exports_stable_declaration(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_served"
        node = valid_manifest_node(uid, visibility="served")
        manifest = valid_manifest((uid, node))
        exposure_uid = next(iter(manifest["exposures"]))
        manifest["exposures"][exposure_uid]["owner"] = {
            "email": ["ops@example.com", "data@example.com"],
            "name": "",
        }
        report, catalog = validator.validate_manifest(manifest)
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("exposures", catalog["resources"][0])
        self.assertEqual(
            [
                {
                    "maturity": "medium",
                    "name": "public_metric_application",
                    "owner": {
                        "email": ["data@example.com", "ops@example.com"],
                        "name": "",
                    },
                    "type": "application",
                    "unique_id": exposure_uid,
                }
            ],
            catalog["resources"][0]["exposures"],
        )

        for name, mutate, expected_code in (
            (
                "missing",
                lambda value: value["exposures"].clear(),
                "MISSING_ACTIVE_EXPOSURE",
            ),
            (
                "maturity",
                lambda value: next(iter(value["exposures"].values())).__setitem__(
                    "maturity", "unknown"
                ),
                "INVALID_EXPOSURE_MATURITY",
            ),
            (
                "owner",
                lambda value: next(iter(value["exposures"].values())).__setitem__(
                    "owner", {"email": None, "name": ""}
                ),
                "INVALID_EXPOSURE_OWNER",
            ),
        ):
            with self.subTest(name=name):
                invalid = valid_manifest(
                    (uid, valid_manifest_node(uid, visibility="served"))
                )
                mutate(invalid)
                invalid_report, invalid_catalog = validator.validate_manifest(invalid)
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertIn(
                    expected_code, [error["code"] for error in invalid_report["errors"]]
                )

    def test_join_policy_resolves_reconciliation_test_by_name_and_exports_allowlist(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        join = valid_join_metadata()
        join["source_keys"] = ["metric_value", "district_id"]
        node["config"]["meta"]["public_gold"]["joins"] = {"district_lookup": join}
        test_uid, test_node = valid_reconciliation_test(uid)
        manifest = valid_manifest((uid, node), (test_uid, test_node))

        report, catalog = validator.validate_manifest(manifest)

        self.assertEqual("PASS", report["status"], report)
        self.assertIn("joins", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            {
                "district_lookup": {
                    "cardinality": "many_to_one",
                    "fan_out_policy": "대상 키가 중복되면 게시를 중단합니다.",
                    "purpose": "서울 자치구 기준 정보를 연결합니다.",
                    "reconciliation_test": "reconcile_district_join",
                    "source_keys": ["metric_value", "district_id"],
                    "target": "model.weather.dim_district",
                }
            },
            catalog["resources"][0]["public_gold"]["joins"],
        )
        self.assertNotIn(test_uid, validator.render_json(catalog))

    def test_join_policy_rejects_missing_unsafe_or_unresolved_declarations(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        cases = []
        for field in (
            "target",
            "source_keys",
            "purpose",
            "cardinality",
            "fan_out_policy",
            "reconciliation_test",
        ):
            cases.append(
                (
                    f"missing_{field}",
                    lambda join, field=field: join.pop(field),
                    field,
                    None,
                )
            )
        cases.extend(
            [
                (
                    "one_to_many",
                    lambda join: join.__setitem__("cardinality", "one_to_many"),
                    "cardinality",
                    None,
                ),
                (
                    "many_to_many",
                    lambda join: join.__setitem__("cardinality", "many_to_many"),
                    "cardinality",
                    None,
                ),
                (
                    "unknown_source",
                    lambda join: join.__setitem__("source_keys", ["missing_column"]),
                    "source_keys",
                    None,
                ),
                (
                    "unknown_test",
                    lambda join: join.__setitem__(
                        "reconciliation_test", "missing_test"
                    ),
                    "reconciliation_test",
                    None,
                ),
                (
                    "wrong_dependency",
                    lambda join: None,
                    "reconciliation_test",
                    "model.other.unrelated",
                ),
            ]
        )
        for name, mutate, field, dependency in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                join = valid_join_metadata()
                mutate(join)
                node["config"]["meta"]["public_gold"]["joins"] = {
                    "district_lookup": join
                }
                test_uid, test_node = valid_reconciliation_test(dependency or uid)
                manifest = valid_manifest((uid, node), (test_uid, test_node))
                report, catalog = validator.validate_manifest(manifest)
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertTrue(
                    any(error["path"].endswith(field) for error in report["errors"]),
                    report,
                )

    def test_lifecycle_active_and_deprecated_rules_export_only_validated_fields(
        self,
    ) -> None:
        validator = manifest_validator_module()
        active_uid = "model.weather.gold_active"
        active = valid_manifest_node(active_uid)
        active["config"]["meta"]["public_gold"]["lifecycle"] = {
            "replacement_is_future": True,
            "replacement_relation": "model.weather.gold_future",
            "status": "active",
        }
        deprecated_uid = "model.weather.gold_deprecated"
        deprecated = valid_manifest_node(deprecated_uid)
        deprecated["config"]["meta"]["public_gold"]["lifecycle"] = {
            "compatibility_window_guidance": "두 번의 월간 배포 동안 기존 계약을 함께 제공합니다.",
            "replacement_relation": "model.weather.gold_replacement",
            "status": "deprecated",
        }
        report, catalog = validator.validate_manifest(
            valid_manifest((deprecated_uid, deprecated), (active_uid, active))
        )
        self.assertEqual("PASS", report["status"], report)
        resources = {item["unique_id"]: item for item in catalog["resources"]}
        self.assertIn("lifecycle", resources[active_uid]["public_gold"])
        self.assertEqual(
            active["config"]["meta"]["public_gold"]["lifecycle"],
            resources[active_uid]["public_gold"]["lifecycle"],
        )
        self.assertEqual(
            deprecated["config"]["meta"]["public_gold"]["lifecycle"],
            resources[deprecated_uid]["public_gold"]["lifecycle"],
        )

    def test_lifecycle_rejects_invalid_deprecation_and_unmarked_active_replacement(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        cases = (
            ("status", {"status": "retired"}, "status"),
            (
                "deprecated_relation",
                {
                    "status": "deprecated",
                    "compatibility_window_guidance": "두 번의 배포 동안 호환합니다.",
                },
                "replacement_relation",
            ),
            (
                "deprecated_guidance",
                {"status": "deprecated", "replacement_relation": "model.weather.new"},
                "compatibility_window_guidance",
            ),
            (
                "deprecated_english",
                {
                    "status": "deprecated",
                    "replacement_relation": "model.weather.new",
                    "compatibility_window_guidance": "Two releases",
                },
                "compatibility_window_guidance",
            ),
            (
                "active_replacement",
                {"status": "active", "replacement_relation": "model.weather.future"},
                "replacement_is_future",
            ),
        )
        for name, lifecycle, field in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                node["config"]["meta"]["public_gold"]["lifecycle"] = lifecycle
                report, catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertTrue(
                    any(error["path"].endswith(field) for error in report["errors"]),
                    report,
                )

    def test_reconciliation_uniqueness_is_scoped_to_same_name_dependent_tests(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        node["config"]["meta"]["public_gold"]["joins"] = {
            "district_lookup": valid_join_metadata()
        }
        dependent_uid, dependent = valid_reconciliation_test(
            uid, unique_id="test.weather.random_hash_dependent"
        )
        unrelated_uid, unrelated = valid_reconciliation_test(
            "model.other.unrelated", unique_id="test.weather.random_hash_unrelated"
        )

        report, catalog = validator.validate_manifest(
            valid_manifest(
                (uid, node), (unrelated_uid, unrelated), (dependent_uid, dependent)
            )
        )

        self.assertEqual("PASS", report["status"], report)
        self.assertIsNotNone(catalog)

        scenarios = (
            ("not_found", [], "RECONCILIATION_TEST_NOT_FOUND"),
            (
                "dependency",
                [(unrelated_uid, unrelated)],
                "RECONCILIATION_TEST_DEPENDENCY",
            ),
            (
                "ambiguous",
                [
                    (dependent_uid, dependent),
                    valid_reconciliation_test(
                        uid, unique_id="test.weather.second_dependent"
                    ),
                ],
                "RECONCILIATION_TEST_AMBIGUOUS",
            ),
        )
        for name, tests, expected_code in scenarios:
            with self.subTest(name=name):
                scenario_report, scenario_catalog = validator.validate_manifest(
                    valid_manifest((uid, copy.deepcopy(node)), *tests)
                )
                self.assertEqual("FAIL", scenario_report["status"], scenario_report)
                self.assertIsNone(scenario_catalog)
                self.assertIn(
                    expected_code,
                    [error["code"] for error in scenario_report["errors"]],
                )

    def test_served_exposure_projection_rejects_paths_and_runtime_timestamps_at_exact_paths(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_served"
        cases = (
            ("uid_path", "uid", "/private/tmp/exposure", None),
            ("name_path", "name", "/private/tmp/application", ".name"),
            ("type_timestamp", "type", "2026-07-12T12:34:56Z", ".type"),
            ("owner_name_path", "owner_name", "/private/tmp/owner", ".owner.name"),
            ("owner_email_path", "owner_email", "/private/tmp/email", ".owner.email"),
            (
                "owner_email_timestamp",
                "owner_email_list",
                "2026-07-12T12:34:56+09:00",
                ".owner.email[1]",
            ),
        )
        for name, field, value, suffix in cases:
            with self.subTest(name=name):
                manifest = valid_manifest(
                    (uid, valid_manifest_node(uid, visibility="served"))
                )
                exposure_uid = next(iter(manifest["exposures"]))
                exposure = manifest["exposures"][exposure_uid]
                if field == "uid":
                    manifest["exposures"] = {value: exposure}
                    expected_path = f"exposures.{value}"
                elif field == "owner_name":
                    exposure["owner"] = {"email": None, "name": value}
                    expected_path = f"exposures.{exposure_uid}{suffix}"
                elif field == "owner_email":
                    exposure["owner"] = {"email": value, "name": ""}
                    expected_path = f"exposures.{exposure_uid}{suffix}"
                elif field == "owner_email_list":
                    exposure["owner"] = {
                        "email": ["ops@example.com", value],
                        "name": "",
                    }
                    expected_path = f"exposures.{exposure_uid}{suffix}"
                else:
                    exposure[field] = value
                    expected_path = f"exposures.{exposure_uid}{suffix}"
                report, catalog = validator.validate_manifest(manifest)
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    expected_path, [error["path"] for error in report["errors"]]
                )

    def test_served_exposure_valid_projection_is_byte_stable_across_mapping_order(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_served"
        forward = valid_manifest((uid, valid_manifest_node(uid, visibility="served")))
        first_uid = next(iter(forward["exposures"]))
        forward["exposures"][first_uid]["owner"] = {
            "email": ["ops@example.com", "data@example.com"],
            "name": "서비스 운영팀",
        }
        second_uid = "exposure.weather.second_app"
        forward["exposures"][second_uid] = valid_manifest_exposure(
            uid,
            name="second_application",
            owner={"email": "second@example.com", "name": ""},
        )
        reverse = copy.deepcopy(forward)
        reverse["exposures"] = dict(reversed(list(reverse["exposures"].items())))
        reverse["exposures"][first_uid]["owner"]["email"].reverse()

        forward_report, forward_catalog = validator.validate_manifest(forward)
        reverse_report, reverse_catalog = validator.validate_manifest(reverse)

        self.assertEqual("PASS", forward_report["status"], forward_report)
        self.assertEqual("PASS", reverse_report["status"], reverse_report)
        self.assertEqual(
            validator.render_json(forward_catalog).encode("utf-8"),
            validator.render_json(reverse_catalog).encode("utf-8"),
        )


if __name__ == "__main__":
    unittest.main()

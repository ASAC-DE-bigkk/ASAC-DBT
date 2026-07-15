from __future__ import annotations

from contracts.engine.tests.fixtures import (
    CANONICAL_SPACE_SOURCE_CHAIN,
    CANONICAL_SPACE_STAMP,
    CANONICAL_TIMEZONE,
    enable_valid_space_contract,
    manifest_validator_module,
    unittest,
    valid_manifest,
    valid_manifest_node,
)


class PublicGoldManifestSemanticRuleTests(unittest.TestCase):
    def test_time_contract_projects_valid_roles_and_rejects_timezone_or_role_conflicts(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        valid = valid_manifest((uid, valid_manifest_node(uid)))
        report, catalog = validator.validate_manifest(valid)
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("time", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            valid["nodes"][uid]["config"]["meta"]["public_gold"]["time"],
            catalog["resources"][0]["public_gold"]["time"],
        )

        def mutate_description(node: dict[str, object]) -> None:
            node["columns"]["product_as_of_at"]["description"] = (
                "UTC 기준으로 계산한 제품 시각입니다."
            )

        def add_unmapped_time_role(node: dict[str, object]) -> None:
            node["columns"]["observed_time"] = {
                "config": {
                    "meta": {
                        "null_meaning": "관측 시각이 없는 상태입니다.",
                        "semantic_role": "timestamp",
                        "time_role": "observation",
                        "timezone": CANONICAL_TIMEZONE,
                    }
                },
                "data_type": "timestamp(6)",
                "description": "원천 자료를 관측한 서울 기준 시각입니다.",
                "name": "observed_time",
            }
            node["config"]["meta"]["public_gold"]["column_order"].append(
                "observed_time"
            )

        cases = (
            (
                "canonical_utc",
                lambda node: node["config"]["meta"]["public_gold"]["time"].__setitem__(
                    "canonical_timezone", "UTC"
                ),
                "canonical_timezone",
            ),
            (
                "role_utc",
                lambda node: node["config"]["meta"]["public_gold"]["time"]["roles"][
                    "product_as_of_at"
                ].__setitem__("timezone", "UTC"),
                "roles.product_as_of_at.timezone",
            ),
            (
                "column_utc",
                lambda node: node["columns"]["product_as_of_at"]["config"][
                    "meta"
                ].__setitem__("timezone", "UTC"),
                "columns.product_as_of_at.config.meta.timezone",
            ),
            (
                "role_mismatch",
                lambda node: node["columns"]["product_as_of_at"]["config"][
                    "meta"
                ].__setitem__("time_role", "event"),
                "columns.product_as_of_at.config.meta.time_role",
            ),
            (
                "missing_role",
                lambda node: node["config"]["meta"]["public_gold"]["time"]["roles"].pop(
                    "published_at"
                ),
                "time.roles.published_at",
            ),
            (
                "utc_description",
                mutate_description,
                "columns.product_as_of_at.description",
            ),
            (
                "english_slo",
                lambda node: node["config"]["meta"]["public_gold"]["time"].__setitem__(
                    "freshness_slo", "Within fifteen minutes"
                ),
                "time.freshness_slo",
            ),
            ("unmapped_time_role", add_unmapped_time_role, "time.roles.observed_time"),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                mutate(node)
                invalid_report, invalid_catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(
                    any(
                        error["path"].endswith(suffix)
                        for error in invalid_report["errors"]
                    ),
                    invalid_report,
                )

    def test_explicit_utc_detection_uses_ascii_identifier_boundaries(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        expected_path = f"nodes.{uid}.columns.product_as_of_at.description"
        descriptions = (
            "UTC기준으로 계산한 제품 시각입니다.",
            "UTC로 변환한 제품 시각입니다.",
            "utc에서 읽은 제품 시각입니다.",
            "제품 시각은 (UTC) 기준입니다.",
            "제품 시각은 UTC, 기준입니다.",
        )
        for description in descriptions:
            with self.subTest(description=description):
                node = valid_manifest_node(uid)
                node["columns"]["product_as_of_at"]["description"] = description
                report, catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    expected_path, [error["path"] for error in report["errors"]]
                )

    def test_timestamp_data_type_and_time_role_contract_is_bidirectional(self) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        data_type_path = f"nodes.{uid}.columns.product_as_of_at.data_type"

        for data_type in (
            "timestamp",
            "TIMESTAMP(3)",
            "timestamp with time zone",
            "TIMESTAMP(6) WITHOUT TIME ZONE",
        ):
            with self.subTest(valid_data_type=data_type):
                node = valid_manifest_node(uid)
                node["columns"]["product_as_of_at"]["data_type"] = data_type
                report, catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )
                self.assertEqual("PASS", report["status"], report)
                self.assertIsNotNone(catalog)

        for data_type in ("varchar", "date"):
            with self.subTest(role_on_non_timestamp=data_type):
                node = valid_manifest_node(uid)
                node["columns"]["product_as_of_at"]["data_type"] = data_type
                report, catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertIn(
                    data_type_path, [error["path"] for error in report["errors"]]
                )

        semantic_mismatch = valid_manifest_node(uid)
        semantic_mismatch["columns"]["product_as_of_at"]["config"]["meta"][
            "semantic_role"
        ] = "dimension"
        mismatch_report, mismatch_catalog = validator.validate_manifest(
            valid_manifest((uid, semantic_mismatch))
        )
        self.assertEqual("FAIL", mismatch_report["status"], mismatch_report)
        self.assertIsNone(mismatch_catalog)
        self.assertIn(
            f"nodes.{uid}.columns.product_as_of_at.config.meta.semantic_role",
            [error["path"] for error in mismatch_report["errors"]],
        )

        timestamp_without_role = valid_manifest_node(uid)
        timestamp_without_role["columns"]["event_time"] = {
            "config": {
                "meta": {
                    "null_meaning": "이벤트 시각을 기록하지 못한 상태입니다.",
                    "semantic_role": "dimension",
                }
            },
            "data_type": "TIMESTAMP(3) WITH TIME ZONE",
            "description": "원천 이벤트의 서울 기준 시각입니다.",
            "name": "event_time",
        }
        timestamp_without_role["config"]["meta"]["public_gold"]["column_order"].append(
            "event_time"
        )
        missing_report, missing_catalog = validator.validate_manifest(
            valid_manifest((uid, timestamp_without_role))
        )
        self.assertEqual("FAIL", missing_report["status"], missing_report)
        self.assertIsNone(missing_catalog)
        missing_paths = [error["path"] for error in missing_report["errors"]]
        self.assertIn(
            f"nodes.{uid}.columns.event_time.config.meta.semantic_role",
            missing_paths,
        )
        self.assertIn(
            f"nodes.{uid}.config.meta.public_gold.time.roles.event_time",
            missing_paths,
        )

    def test_space_contract_requires_exact_axis_stamp_dependency_and_named_tests(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_spatial"
        node = valid_manifest_node(uid)
        test_nodes = enable_valid_space_contract(node)
        manifest = valid_manifest((uid, node), *test_nodes)
        report, catalog = validator.validate_manifest(manifest)
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("space", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            node["config"]["meta"]["public_gold"]["space"],
            catalog["resources"][0]["public_gold"]["space"],
        )

        portable_node = valid_manifest_node(uid)
        portable_tests = enable_valid_space_contract(portable_node)
        portable_node["depends_on"]["nodes"].remove("model.asac_axes.dim_admin_dong")
        portable_node["depends_on"]["nodes"].append(
            "model.alternate_axes.dim_admin_dong"
        )
        portable_report, portable_catalog = validator.validate_manifest(
            valid_manifest((uid, portable_node), *portable_tests)
        )
        self.assertEqual("PASS", portable_report["status"], portable_report)
        self.assertIsNotNone(portable_catalog)

        cases = (
            (
                "chain",
                lambda value, tests: value["config"]["meta"]["public_gold"][
                    "space"
                ].__setitem__(
                    "source_chain", list(reversed(CANONICAL_SPACE_SOURCE_CHAIN))
                ),
                "source_chain",
            ),
            (
                "key",
                lambda value, tests: value["config"]["meta"]["public_gold"][
                    "space"
                ].__setitem__("canonical_key", "source_admin_code"),
                "canonical_key",
            ),
            (
                "missing_approved_revision",
                lambda value, tests: value["config"]["meta"]["public_gold"][
                    "space"
                ].pop("approved_revision_date"),
                "approved_revision_date",
            ),
            (
                "wrong_approved_revision",
                lambda value, tests: value["config"]["meta"]["public_gold"][
                    "space"
                ].__setitem__("approved_revision_date", "1900-01-01"),
                "approved_revision_date",
            ),
            (
                "stamp",
                lambda value, tests: value["config"]["meta"]["public_gold"][
                    "space"
                ].__setitem__("stamp_fields", CANONICAL_SPACE_STAMP[:-1]),
                "stamp_fields",
            ),
            (
                "dependency",
                lambda value, tests: value["depends_on"]["nodes"].remove(
                    "model.asac_axes.dim_admin_dong"
                ),
                "dependency",
            ),
            ("test", lambda value, tests: tests.pop(), "reconciliation_tests"),
            (
                "explanation",
                lambda value, tests: value["config"]["meta"]["public_gold"][
                    "space"
                ].__setitem__("fan_out_explanation", "Stop on duplicates"),
                "fan_out_explanation",
            ),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                invalid = valid_manifest_node(uid)
                invalid_tests = enable_valid_space_contract(invalid)
                mutate(invalid, invalid_tests)
                invalid_report, invalid_catalog = validator.validate_manifest(
                    valid_manifest((uid, invalid), *invalid_tests)
                )
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(
                    any(suffix in error["path"] for error in invalid_report["errors"]),
                    invalid_report,
                )

    def test_metric_contract_matches_declared_metric_column_and_projects_allowlist(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("metrics", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            node["config"]["meta"]["public_gold"]["metrics"],
            catalog["resources"][0]["public_gold"]["metrics"],
        )

        cases = (
            (
                "unknown_column",
                lambda value: value["config"]["meta"]["public_gold"][
                    "metrics"
                ].__setitem__(
                    "missing_metric",
                    value["config"]["meta"]["public_gold"]["metrics"].pop(
                        "metric_value"
                    ),
                ),
                "metrics.missing_metric",
            ),
            (
                "formula",
                lambda value: value["config"]["meta"]["public_gold"]["metrics"][
                    "metric_value"
                ].pop("expression"),
                "metrics.metric_value.expression",
            ),
            (
                "unit",
                lambda value: value["config"]["meta"]["public_gold"]["metrics"][
                    "metric_value"
                ].__setitem__("unit", "명"),
                "metrics.metric_value.unit",
            ),
            (
                "aggregation",
                lambda value: value["config"]["meta"]["public_gold"]["metrics"][
                    "metric_value"
                ].__setitem__("aggregation", "avg"),
                "metrics.metric_value.aggregation",
            ),
            (
                "zero",
                lambda value: value["config"]["meta"]["public_gold"]["metrics"][
                    "metric_value"
                ].__setitem__("zero_meaning", "다른 의미입니다."),
                "metrics.metric_value.zero_meaning",
            ),
            (
                "null",
                lambda value: value["config"]["meta"]["public_gold"]["metrics"][
                    "metric_value"
                ].__setitem__("null_meaning", "다른 null 의미입니다."),
                "metrics.metric_value.null_meaning",
            ),
            (
                "axes",
                lambda value: value["config"]["meta"]["public_gold"]["metrics"][
                    "metric_value"
                ].__setitem__("additive_axes", {"axis": "admin_dong"}),
                "metrics.metric_value.additive_axes",
            ),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                invalid = valid_manifest_node(uid)
                mutate(invalid)
                invalid_report, invalid_catalog = validator.validate_manifest(
                    valid_manifest((uid, invalid))
                )
                self.assertEqual("FAIL", invalid_report["status"], invalid_report)
                self.assertIsNone(invalid_catalog)
                self.assertTrue(
                    any(
                        error["path"].endswith(suffix)
                        for error in invalid_report["errors"]
                    ),
                    invalid_report,
                )

    def test_metric_axes_reject_internal_duplicates_and_cross_axis_overlap(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"

        def duplicate_additive(metric: dict[str, object]) -> None:
            metric["additive_axes"] = ["admin_dong", "admin_dong"]

        def duplicate_non_additive(metric: dict[str, object]) -> None:
            metric["non_additive_axes"] = ["time", "time"]

        def overlap(metric: dict[str, object]) -> None:
            metric["non_additive_axes"] = ["admin_dong"]

        cases = (
            ("duplicate_additive", duplicate_additive, "additive_axes[1]"),
            (
                "duplicate_non_additive",
                duplicate_non_additive,
                "non_additive_axes[1]",
            ),
            ("overlap", overlap, "non_additive_axes[0]"),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                node = valid_manifest_node(uid)
                metric = node["config"]["meta"]["public_gold"]["metrics"][
                    "metric_value"
                ]
                mutate(metric)
                report, catalog = validator.validate_manifest(
                    valid_manifest((uid, node))
                )
                self.assertEqual("FAIL", report["status"], report)
                self.assertIsNone(catalog)
                self.assertTrue(
                    any(error["path"].endswith(suffix) for error in report["errors"]),
                    report,
                )


if __name__ == "__main__":
    unittest.main()

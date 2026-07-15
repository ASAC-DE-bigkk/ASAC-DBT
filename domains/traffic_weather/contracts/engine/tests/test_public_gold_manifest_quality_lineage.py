from __future__ import annotations

from contracts.engine.tests.fixtures import (
    copy,
    manifest_validator_module,
    unittest,
    valid_manifest,
    valid_manifest_node,
)


class PublicGoldManifestQualityLineageTests(unittest.TestCase):
    def test_quality_state_contract_validates_tokens_explanations_and_declared_columns(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_quality"
        node = valid_manifest_node(uid)
        node["columns"]["quality_state"] = {
            "config": {
                "meta": {
                    "null_meaning": "품질 상태를 계산하지 못한 경우입니다.",
                    "semantic_role": "quality_state",
                }
            },
            "data_type": "string",
            "description": "제품 품질의 안정 상태를 나타냅니다.",
            "name": "quality_state",
        }
        node["config"]["meta"]["public_gold"]["column_order"].append("quality_state")
        node["config"]["meta"]["public_gold"]["quality"]["state_fields"] = {
            "quality_state": {
                "allowed_values": ["complete", "missing"],
                "state_explanations": {
                    "complete": "필수 증거가 모두 확인된 상태입니다.",
                    "missing": "필수 증거가 누락된 상태입니다.",
                },
            }
        }
        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("quality", catalog["resources"][0]["public_gold"])
        self.assertEqual(
            node["config"]["meta"]["public_gold"]["quality"],
            catalog["resources"][0]["public_gold"]["quality"],
        )

        cases = (
            (
                "column",
                lambda quality: quality["state_fields"].__setitem__(
                    "missing_column", quality["state_fields"].pop("quality_state")
                ),
                "state_fields.missing_column",
            ),
            (
                "token",
                lambda quality: quality["state_fields"]["quality_state"].__setitem__(
                    "allowed_values", ["Complete Value"]
                ),
                "allowed_values",
            ),
            (
                "explanation",
                lambda quality: quality["state_fields"]["quality_state"][
                    "state_explanations"
                ].__setitem__("complete", "Complete"),
                "state_explanations.complete",
            ),
            (
                "coverage",
                lambda quality: quality.__setitem__("coverage_explanation", "Coverage"),
                "coverage_explanation",
            ),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                invalid = copy.deepcopy(node)
                mutate(invalid["config"]["meta"]["public_gold"]["quality"])
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

    def test_lineage_requires_five_identifier_classes_and_declared_columns_or_relation_level(
        self,
    ) -> None:
        validator = manifest_validator_module()
        uid = "model.weather.gold_weather_public_metric"
        node = valid_manifest_node(uid)
        node["config"]["meta"]["public_gold"]["lineage"]["future_unvalidated"] = {
            "ignored": "value"
        }
        report, catalog = validator.validate_manifest(valid_manifest((uid, node)))
        self.assertEqual("PASS", report["status"], report)
        self.assertIn("lineage", catalog["resources"][0]["public_gold"])
        exported = catalog["resources"][0]["public_gold"]["lineage"]
        self.assertNotIn("future_unvalidated", exported)
        self.assertEqual(
            {"run", "raw", "request", "publication", "as_of"},
            set(exported["identifiers"]),
        )

        cases = (
            (
                "source",
                lambda lineage: lineage.__setitem__("source_relations", []),
                "source_relations",
            ),
            (
                "class",
                lambda lineage: lineage["identifiers"].pop("request"),
                "identifiers.request",
            ),
            (
                "column",
                lambda lineage: lineage["identifiers"]["run"].__setitem__(
                    "columns", ["missing_run_id"]
                ),
                "identifiers.run.columns",
            ),
        )
        for name, mutate, suffix in cases:
            with self.subTest(name=name):
                invalid = valid_manifest_node(uid)
                mutate(invalid["config"]["meta"]["public_gold"]["lineage"])
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

        relation_only = valid_manifest_node(uid)
        relation_only["config"]["meta"]["public_gold"]["lineage"]["identifiers"][
            "run"
        ] = {
            "columns": ["missing_run_id"],
            "relation_level_only": True,
        }
        relation_report, relation_catalog = validator.validate_manifest(
            valid_manifest((uid, relation_only))
        )
        self.assertEqual("FAIL", relation_report["status"], relation_report)
        self.assertIsNone(relation_catalog)
        self.assertIn(
            f"nodes.{uid}.config.meta.public_gold.lineage.identifiers.run.columns",
            [error["path"] for error in relation_report["errors"]],
        )

        relation_only_without_columns = valid_manifest_node(uid)
        relation_only_without_columns["config"]["meta"]["public_gold"]["lineage"][
            "identifiers"
        ]["run"] = {
            "relation_level_only": True,
        }
        no_columns_report, no_columns_catalog = validator.validate_manifest(
            valid_manifest((uid, relation_only_without_columns))
        )
        self.assertEqual("PASS", no_columns_report["status"], no_columns_report)
        self.assertEqual(
            [],
            no_columns_catalog["resources"][0]["public_gold"]["lineage"]["identifiers"][
                "run"
            ]["columns"],
        )

        relation_only_empty_columns = valid_manifest_node(uid)
        relation_only_empty_columns["config"]["meta"]["public_gold"]["lineage"][
            "identifiers"
        ]["run"] = {"columns": [], "relation_level_only": True}
        empty_report, empty_catalog = validator.validate_manifest(
            valid_manifest((uid, relation_only_empty_columns))
        )
        self.assertEqual("PASS", empty_report["status"], empty_report)
        self.assertEqual(
            [],
            empty_catalog["resources"][0]["public_gold"]["lineage"]["identifiers"][
                "run"
            ]["columns"],
        )


if __name__ == "__main__":
    unittest.main()

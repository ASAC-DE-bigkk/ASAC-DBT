from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = (
    REPO_ROOT
    / "domains"
    / "traffic"
    / "contracts"
    / "scripts"
    / "validate_singular_test_dependency_manifest.py"
)

REQUIRED_DEPENDENCIES = {
    "assert_gold_traffic_counts_match_silver.sql": (
        "silver_seoul_traffic_incident_current",
        "gold_traffic_incident_summary",
    ),
    "assert_gold_traffic_row_counts_positive.sql": ("gold_traffic_incident_summary",),
    "assert_gold_traffic_current_by_admin_dong_hourly_admin_stamp_exact.sql": (
        "gold_traffic_incident_current_by_admin_dong_hourly",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_fanout_reconciles.sql": (
        "silver_seoul_traffic_incident_current",
        "gold_traffic_incident_current_by_admin_dong_hourly",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_grain_unique.sql": (
        "gold_traffic_incident_current_by_admin_dong_hourly",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_hourly_completeness.sql": (
        "gold_traffic_incident_current_by_admin_dong_hourly",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_snapshot_reconciles.sql": (
        "silver_seoul_traffic_incident_current",
        "gold_traffic_incident_current_by_admin_dong_hourly",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_zero_requires_complete.sql": (
        "gold_traffic_incident_current_by_admin_dong_hourly",
    ),
    "assert_silver_seoul_traffic_incident_grain_unique.sql": ("silver_seoul_traffic_incident",),
    "assert_silver_traffic_admin_axis_consistent.sql": ("silver_seoul_traffic_incident",),
    "assert_silver_traffic_admin_axis_coverage.sql": ("silver_seoul_traffic_incident",),
    "assert_silver_traffic_event_at_matches_occurred_at.sql": ("silver_seoul_traffic_incident",),
    "assert_silver_traffic_latest_publishable_record.sql": ("silver_seoul_traffic_incident",),
    "assert_silver_traffic_location_contract.sql": ("silver_seoul_traffic_incident",),
    "assert_silver_traffic_uses_publishable_runs.sql": ("silver_seoul_traffic_incident",),
    "assert_silver_traffic_wgs84_required_when_source_coordinate_available.sql": (
        "silver_seoul_traffic_incident",
    ),
    "assert_traffic_current_pinned_publishable_run.sql": (
        "silver_seoul_traffic_incident_current",
    ),
}


def valid_manifest() -> dict[str, object]:
    nodes: dict[str, object] = {}
    for index, (filename, model_names) in enumerate(REQUIRED_DEPENDENCIES.items()):
        nodes[f"test.traffic.{index}"] = {
            "resource_type": "test",
            "original_file_path": f"tests/{filename}",
            "depends_on": {
                "nodes": [
                    *(f"model.traffic.{model_name}" for model_name in model_names),
                    "source.traffic.topis_accident",
                ]
            },
        }
    return {"nodes": nodes}


def run_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class ValidateSingularTestDependencyManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        from domains.traffic.contracts.scripts import (
            validate_singular_test_dependency_manifest as validator,
        )

        self.validator = validator

    def test_valid_manifest_passes(self) -> None:
        self.validator.validate_manifest(valid_manifest())

    def test_required_dependency_mapping_matches_validator(self) -> None:
        self.assertEqual(
            self.validator.REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES,
            REQUIRED_DEPENDENCIES,
        )

    def test_empty_dependency_array_fails_with_filename_and_node_ids(self) -> None:
        manifest = valid_manifest()
        filename = "assert_silver_traffic_location_contract.sql"
        node = next(
            node
            for node in manifest["nodes"].values()
            if node["original_file_path"] == f"tests/{filename}"
        )
        node["depends_on"]["nodes"] = []

        with self.assertRaisesRegex(
            self.validator.ManifestDependencyError,
            rf"{filename}.*model\.traffic\.silver_seoul_traffic_incident",
        ):
            self.validator.validate_manifest(manifest)

    def test_missing_required_model_dependency_fails_with_filename_and_node_ids(self) -> None:
        manifest = valid_manifest()
        filename = "assert_gold_traffic_counts_match_silver.sql"
        node = next(
            node
            for node in manifest["nodes"].values()
            if node["original_file_path"] == f"tests/{filename}"
        )
        node["depends_on"]["nodes"].remove("model.traffic.gold_traffic_incident_summary")

        with self.assertRaisesRegex(
            self.validator.ManifestDependencyError,
            rf"{filename}.*model\.traffic\.gold_traffic_incident_summary",
        ):
            self.validator.validate_manifest(manifest)

    def test_duplicate_original_file_path_fails(self) -> None:
        manifest = valid_manifest()
        original_node = next(iter(manifest["nodes"].values()))
        manifest["nodes"]["test.traffic.duplicate"] = copy.deepcopy(original_node)

        with self.assertRaisesRegex(
            self.validator.ManifestDependencyError,
            "assert_gold_traffic_counts_match_silver.sql.*expected exactly one test node.*actual 2",
        ):
            self.validator.validate_manifest(manifest)

    def test_unexpected_traffic_model_dependency_fails(self) -> None:
        manifest = valid_manifest()
        filename = "assert_gold_traffic_row_counts_positive.sql"
        node = next(
            node
            for node in manifest["nodes"].values()
            if node["original_file_path"] == f"tests/{filename}"
        )
        node["depends_on"]["nodes"].append("model.traffic.unexpected")

        with self.assertRaisesRegex(
            self.validator.ManifestDependencyError,
            rf"{filename}.*model\.traffic\.unexpected",
        ):
            self.validator.validate_manifest(manifest)

    def test_cli_prints_pass_for_valid_explicit_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(json.dumps(valid_manifest()), encoding="utf-8")

            result = run_cli("--manifest", manifest_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_cli_prints_error_for_invalid_explicit_manifest(self) -> None:
        manifest = valid_manifest()
        manifest["nodes"].pop("test.traffic.0")
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_cli("--manifest", manifest_path)

        self.assertEqual(result.returncode, 1)
        self.assertIn("assert_gold_traffic_counts_match_silver.sql", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()

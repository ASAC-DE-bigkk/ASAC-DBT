#!/usr/bin/env python3
"""Validate traffic singular-test model dependencies in an explicit dbt manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence


REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES = {
    "assert_gold_traffic_counts_match_silver.sql": (
        "silver_seoul_traffic_incident_current",
        "gold_traffic_incident_summary",
    ),
    "assert_gold_traffic_row_counts_positive.sql": ("gold_traffic_incident_summary",),
    "assert_gold_traffic_current_by_admin_dong_hourly_admin_stamp_exact.sql": (
        "gold_traffic_incident_current_by_admin_dong_hourly",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_admin_join_reconciles.sql": (
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
    "assert_gold_traffic_current_by_admin_dong_hourly_product_row_id_reproducible.sql": (
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

REQUIRED_SINGULAR_TEST_EXTERNAL_MODEL_DEPENDENCIES = {
    "assert_gold_traffic_current_by_admin_dong_hourly_admin_join_reconciles.sql": (
        "model.asac_axes.dim_admin_dong",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_admin_stamp_exact.sql": (
        "model.asac_axes.dim_admin_dong",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_fanout_reconciles.sql": (
        "model.asac_axes.dim_admin_dong",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_hourly_completeness.sql": (
        "model.asac_axes.dim_admin_dong",
    ),
    "assert_gold_traffic_current_by_admin_dong_hourly_snapshot_reconciles.sql": (
        "model.asac_axes.dim_admin_dong",
    ),
}


class ManifestDependencyError(ValueError):
    """Raised when a traffic singular test lacks its declared model graph."""


def _model_node_ids(model_names: Sequence[str]) -> list[str]:
    return [f"model.traffic.{model_name}" for model_name in model_names]


def _matching_test_nodes(nodes: Mapping[object, object], filename: str) -> list[Mapping[object, object]]:
    file_path = f"tests/{filename}"
    return [
        node
        for node in nodes.values()
        if isinstance(node, Mapping)
        and node.get("resource_type") == "test"
        and node.get("original_file_path") == file_path
    ]


def _dependency_error(filename: str, expected: list[str], actual: object, detail: str) -> ManifestDependencyError:
    return ManifestDependencyError(
        f"{filename}: {detail}; expected model node IDs {expected}; actual model node IDs {actual}"
    )


def validate_manifest(manifest: object) -> None:
    """Validate exact Traffic edges and required external-model subsets."""
    if not isinstance(manifest, Mapping):
        raise ManifestDependencyError("manifest: expected an object with a nodes mapping")

    nodes = manifest.get("nodes")
    if not isinstance(nodes, Mapping):
        raise ManifestDependencyError("manifest.nodes: expected a mapping")

    for filename, required_models in REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES.items():
        expected = _model_node_ids(required_models)
        matches = _matching_test_nodes(nodes, filename)
        if len(matches) != 1:
            raise _dependency_error(
                filename,
                expected,
                [],
                f"expected exactly one test node; actual {len(matches)} matches",
            )

        depends_on = matches[0].get("depends_on")
        dependency_nodes = depends_on.get("nodes") if isinstance(depends_on, Mapping) else None
        if not isinstance(dependency_nodes, list) or not dependency_nodes:
            actual = dependency_nodes if isinstance(dependency_nodes, list) else repr(dependency_nodes)
            raise _dependency_error(filename, expected, actual, "expected a non-empty dependency array")

        actual = sorted(
            {
                node_id
                for node_id in dependency_nodes
                if isinstance(node_id, str) and node_id.startswith("model.traffic.")
            }
        )
        if set(actual) != set(expected):
            raise _dependency_error(filename, sorted(expected), actual, "traffic model dependencies differ")

        required_external = REQUIRED_SINGULAR_TEST_EXTERNAL_MODEL_DEPENDENCIES.get(
            filename,
            (),
        )
        dependency_node_ids = {
            node_id for node_id in dependency_nodes if isinstance(node_id, str)
        }
        missing_external = sorted(set(required_external) - dependency_node_ids)
        if missing_external:
            actual_external = sorted(
                {
                    node_id
                    for node_id in dependency_nodes
                    if isinstance(node_id, str)
                    and node_id.startswith("model.")
                    and not node_id.startswith("model.traffic.")
                }
            )
            raise _dependency_error(
                filename,
                sorted(required_external),
                actual_external,
                f"required external model dependencies missing {missing_external}",
            )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to the manifest JSON to validate")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        validate_manifest(manifest)
    except (ManifestDependencyError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 1

    print("PASS: traffic singular-test dependency manifest is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

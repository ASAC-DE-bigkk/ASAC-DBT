from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = (
    REPO_ROOT
    / "domains"
    / "traffic"
    / "contracts"
    / "scripts"
    / "validate_singular_test_dependency_manifest.py"
)
PROJECT_NAME = "asac_seoul"
GOLD_PATH = "tests/traffic/transform/gold/assert_gold_contract.sql"
SILVER_PATH = "tests/traffic/transform/silver/assert_silver_contract.sql"


def _test_node(
    path: str,
    dependencies: list[object],
    *,
    raw_code: str = "{{ ref(dynamic_model_name) }}",
) -> dict[str, object]:
    phase = Path(path).parent.name
    return {
        "resource_type": "test",
        "original_file_path": path,
        "raw_code": raw_code,
        "tags": [f"ask_seoul_traffic_transform_{phase}"],
        "depends_on": {"nodes": dependencies},
    }


def valid_manifest() -> dict[str, object]:
    return {
        "metadata": {"project_name": PROJECT_NAME},
        "nodes": {
            "test.asac_seoul.gold_contract": _test_node(
                GOLD_PATH,
                [
                    "model.asac_seoul.gold_traffic_incident_summary",
                    "model.asac_axes.dim_admin_dong",
                    "source.asac_seoul.traffic_bronze.incident",
                ],
                raw_code=(
                    "-- versioned refs are resolved by dbt, not this validator\n"
                    "{{ ref('gold_traffic_incident_summary', version=1) }}"
                ),
            ),
            "test.asac_seoul.silver_contract": _test_node(
                SILVER_PATH,
                ["model.asac_seoul.silver_seoul_traffic_incident"],
            ),
        },
    }


def node_for(manifest: dict[str, object], path: str) -> dict[str, object]:
    nodes = manifest["nodes"]
    assert isinstance(nodes, dict)
    return next(node for node in nodes.values() if node["original_file_path"] == path)


def run_cli(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


@pytest.fixture
def validator():
    from domains.traffic.contracts.scripts import (
        validate_singular_test_dependency_manifest as module,
    )

    return module


def test_manifest_native_validation_uses_dbt_edges_without_source_registry(
    validator,
) -> None:
    validator.validate_manifest(valid_manifest())

    assert not hasattr(validator, "REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES")
    assert not hasattr(validator, "PHASE_TAGS")
    assert not hasattr(validator, "REF_PATTERN")
    assert not hasattr(validator, "declared_model_node_ids")
    assert not hasattr(validator, "_discover_test_paths")


def test_manifest_project_name_is_required(validator) -> None:
    for project_name in (None, "traffic"):
        manifest = valid_manifest()
        if project_name is None:
            manifest.pop("metadata")
        else:
            manifest["metadata"]["project_name"] = project_name

        with pytest.raises(
            validator.ManifestDependencyError,
            match=r"manifest\.metadata\.project_name.*asac_seoul",
        ):
            validator.validate_manifest(manifest)


def test_windows_path_separator_is_normalized(validator) -> None:
    manifest = valid_manifest()
    node_for(manifest, GOLD_PATH)["original_file_path"] = GOLD_PATH.replace("/", "\\")

    validator.validate_manifest(manifest)


def test_manifest_requires_at_least_one_scoped_singular_test(validator) -> None:
    manifest = valid_manifest()
    manifest["nodes"] = {
        "test.asac_seoul.outside": _test_node(
            "tests/traffic/source/assert_source_contract.sql",
            ["model.asac_seoul.silver_seoul_traffic_incident"],
        )
    }

    with pytest.raises(
        validator.ManifestDependencyError,
        match=r"does not contain.*tests/traffic/transform",
    ):
        validator.validate_manifest(manifest)


def test_duplicate_original_file_path_fails(validator) -> None:
    manifest = valid_manifest()
    manifest["nodes"]["test.asac_seoul.duplicate"] = copy.deepcopy(
        manifest["nodes"]["test.asac_seoul.gold_contract"]
    )

    with pytest.raises(
        validator.ManifestDependencyError, match="duplicate.*assert_gold_contract"
    ):
        validator.validate_manifest(manifest)


def test_phase_tag_is_derived_from_the_test_parent_directory(validator) -> None:
    manifest = valid_manifest()
    node_for(manifest, GOLD_PATH)["tags"] = ["ask_seoul_traffic_transform_silver"]

    with pytest.raises(
        validator.ManifestDependencyError, match="assert_gold_contract.*gold"
    ):
        validator.validate_manifest(manifest)


def test_each_scoped_singular_test_requires_a_local_project_model_edge(
    validator,
) -> None:
    manifest = valid_manifest()
    node_for(manifest, GOLD_PATH)["depends_on"]["nodes"] = [
        "model.asac_axes.dim_admin_dong",
        "source.asac_seoul.traffic_bronze.incident",
    ]

    with pytest.raises(
        validator.ManifestDependencyError, match="local asac_seoul model"
    ):
        validator.validate_manifest(manifest)


def test_raw_code_shape_does_not_change_manifest_edge_validation(validator) -> None:
    manifest = valid_manifest()
    node_for(manifest, GOLD_PATH)["raw_code"] = (
        "{% set target = 'gold_traffic_incident_summary' %}{{ ref(target, version=1) }}"
    )

    validator.validate_manifest(manifest)


def test_non_string_and_non_model_dependencies_are_ignored(validator) -> None:
    manifest = valid_manifest()
    node_for(manifest, GOLD_PATH)["depends_on"]["nodes"].extend(
        [{"malformed": "extra"}, "source.other.allowed"]
    )

    validator.validate_manifest(manifest)


def test_nodes_outside_transform_scope_are_ignored(validator) -> None:
    manifest = valid_manifest()
    manifest["nodes"]["test.asac_seoul.source_availability"] = _test_node(
        "tests/traffic/source/availability/assert_source_availability.sql",
        ["source.asac_seoul.traffic_bronze.incident"],
    )

    validator.validate_manifest(manifest)


def test_cli_validates_a_manifest_without_a_tests_root_argument() -> None:
    with tempfile.TemporaryDirectory() as directory:
        manifest_path = Path(directory) / "manifest.json"
        manifest_path.write_text(json.dumps(valid_manifest()), encoding="utf-8")

        result = run_cli("--manifest", manifest_path)

    assert result.returncode == 0, result.stdout
    assert "PASS" in result.stdout
    assert result.stderr == ""


def test_cli_rejects_the_removed_tests_root_argument() -> None:
    with tempfile.TemporaryDirectory() as directory:
        manifest_path = Path(directory) / "manifest.json"
        manifest_path.write_text(json.dumps(valid_manifest()), encoding="utf-8")

        result = run_cli("--manifest", manifest_path, "--tests-root", directory)

    assert result.returncode == 2
    assert "unrecognized arguments: --tests-root" in result.stderr


def test_cli_prints_contract_error_without_traceback() -> None:
    manifest = valid_manifest()
    node_for(manifest, GOLD_PATH)["depends_on"]["nodes"] = []
    with tempfile.TemporaryDirectory() as directory:
        manifest_path = Path(directory) / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = run_cli("--manifest", manifest_path)

    assert result.returncode == 1
    assert "ERROR" in result.stdout
    assert "Traceback" not in result.stderr

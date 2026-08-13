import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
SELECTORS = PROJECT_ROOT / "selectors.yml"

FLOW_SCOPE = "ask_seoul_traffic_transform_flow_gold_scope"
ROAD_CONTEXT_SCOPE = "ask_seoul_traffic_transform_road_context_scope"
SILVER_EXECUTION_TAG = "ask_seoul_traffic_transform_silver"
INCIDENT_SILVER = "ask_seoul_traffic_transform_incident_silver"
INCIDENT_PREFLIGHT = "ask_seoul_traffic_transform_incident_preflight_contracts"
FLOW_SILVER_MODEL = "ask_seoul_traffic_transform_flow_silver_model"
FLOW_SILVER_TESTS = "ask_seoul_traffic_transform_flow_silver_tests"
INCIDENT_MODELS = "ask_seoul_traffic_transform_gold_incident_models"
INCIDENT_GATE_TESTS = "ask_seoul_traffic_transform_gold_incident_gate_tests"
INCIDENT_HOURLY_TESTS = "ask_seoul_traffic_transform_gold_incident_hourly_tests"
INCIDENT_FULL_TESTS = "ask_seoul_traffic_transform_gold_incident_full_tests"
INCIDENT_HOT_BUILD = "ask_seoul_traffic_transform_incident_hot_build"
FLOW_HOT_BUILD = "ask_seoul_traffic_transform_flow_hot_build"
GOLD_HOT_BUILD = "ask_seoul_traffic_transform_gold_hot_build"
CORE_GOLD_HOT_BUILD = "ask_seoul_traffic_transform_core_gold_hot_build"
CORE_GOLD_INCIDENT_HOT_BUILD = "ask_seoul_traffic_transform_core_gold_incident_hot_build"
CROSS_DOMAIN_GOLD_HOT_BUILD = "ask_seoul_traffic_transform_cross_domain_gold_hot_build"
ROAD_CONTEXT_MODEL = "gold_traffic_road_congestion_context_current"

FULL_GOLD_MODELS = "ask_seoul_traffic_transform_gold_models"
FULL_GATE_TESTS = "ask_seoul_traffic_transform_gold_gate_tests"
FULL_HOURLY_TESTS = "ask_seoul_traffic_transform_gold_hourly_tests"
FULL_FULL_TESTS = "ask_seoul_traffic_transform_gold_full_tests"

EXPECTED_FLOW_MODELS = {
    "gold_traffic_flow_link_latest",
    "gold_traffic_flow_change_latest",
    "gold_traffic_flow_congestion_hotspots_hourly",
    "gold_traffic_flow_link_time_profile",
    "gold_traffic_flow_anomaly_current",
}
LINK_REFERENCE_SILVER_MODELS = {
    "silver_seoul_traffic_link_info",
    "silver_seoul_traffic_link_vertex",
    "silver_seoul_traffic_link_reference",
}
EXPECTED_FLOW_SILVER_TESTS = {
    "accepted_values_silver_seoul_traffic_flow_flow_value_quality__available__missing_value",
    "accepted_values_silver_seoul_traffic_flow_source_id__seoul_traffic_flow",
    "assert_silver_seoul_traffic_flow_pinned_rows",
    "not_null_silver_seoul_traffic_flow_dag_run_id",
    "not_null_silver_seoul_traffic_flow_flow_value_quality",
    "not_null_silver_seoul_traffic_flow_link_id",
    "not_null_silver_seoul_traffic_flow_observed_at",
    "not_null_silver_seoul_traffic_flow_payload_hash",
    "not_null_silver_seoul_traffic_flow_parent_incident_run_id",
    "not_null_silver_seoul_traffic_flow_raw_object_key",
    "not_null_silver_seoul_traffic_flow_source_id",
}
EXPECTED_INCIDENT_SILVER_MODELS = {
    "silver_seoul_traffic_incident",
    "silver_seoul_traffic_incident_current",
}
EXPECTED_D1_HOT_MODELS = {
    "gold_traffic_incident_current_by_admin_dong_hourly",
    *EXPECTED_FLOW_MODELS,
}
EXPECTED_INCIDENT_MODELS = {
    "gold_traffic_collection_slot_state",
    "gold_traffic_incident_collection_coverage_5m",
    "gold_traffic_incident_expected_slot_coverage_5m",
    "gold_traffic_incident_current_by_admin_dong_hourly",
    "gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily",
    "gold_traffic_incident_spatial_mapping_quality_daily",
    "gold_traffic_incident_summary",
    "gold_traffic_incident_x_flow",
    "gold_traffic_incident_x_weather_current_hourly",
}
EXPECTED_GOLD_MODEL_COUNT = 15
EXPECTED_INCIDENT_TEST_COUNTS = {
    INCIDENT_GATE_TESTS: 79,
    INCIDENT_HOURLY_TESTS: 99,
    INCIDENT_FULL_TESTS: 129,
}
SELECTOR_PARSE_VARS = {
    "traffic_snapshot_dag_run_id": "ci__traffic_gold_trigger_selectors",
    "traffic_flow_snapshot_dag_run_id": "ci__traffic_gold_trigger_selectors",
    "weather_snapshot_dag_run_id": "ci__traffic_gold_trigger_selectors",
}


def _selectors() -> dict:
    values = yaml.safe_load(SELECTORS.read_text(encoding="utf-8"))["selectors"]
    return {item["name"]: item["definition"] for item in values}


def _excludes_flow_scope(definition: dict) -> bool:
    return {"method": "selector", "value": FLOW_SCOPE} in definition["intersection"][1]["exclude"]


def _dbt_executable() -> str:
    configured = os.environ.get("DBT_BIN") or os.environ.get("DBT_EXECUTABLE")
    if configured:
        return configured

    executable = shutil.which("dbt")
    if executable:
        return executable

    runtime_dbt = Path("/home/airflow/dbt-venv/bin/dbt")
    if runtime_dbt.is_file():
        return str(runtime_dbt)

    pytest.skip("dbt 실행 파일이 없어 resolved selector 계약은 런타임 검증으로 이관")


def _run_dbt(
    dbt_executable: str,
    project_root: Path,
    env: dict[str, str],
    *args: str,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [
            dbt_executable,
            *args,
            "--project-dir",
            str(project_root),
            "--profiles-dir",
            str(project_root),
            "--no-use-colors",
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture(scope="module")
def resolved_selector_project(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, str]]:
    dbt_executable = _dbt_executable()
    tmp_path = tmp_path_factory.mktemp("gold-trigger-selectors")
    project_root = tmp_path / "dbt-root"
    target_path = tmp_path / "target"
    log_path = tmp_path / "logs"
    environment = os.environ.copy()
    environment["DBT_PACKAGES_INSTALL_PATH"] = str(tmp_path / "dbt-packages")
    environment["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    project_root.mkdir()
    for filename in (
        "dbt_project.yml",
        "profiles.yml",
        "selectors.yml",
    ):
        shutil.copy2(PROJECT_ROOT / filename, project_root / filename)
    for directory in ("models", "tests", "macros", "seeds"):
        shutil.copytree(PROJECT_ROOT / directory, project_root / directory)

    package_root = project_root / "packages" / "asac_axes"
    shutil.copytree(REPOSITORY_ROOT / "packages" / "asac_axes", package_root)
    (project_root / "packages.yml").write_text(
        "packages:\n  - local: packages/asac_axes\n",
        encoding="utf-8",
    )

    _run_dbt(dbt_executable, project_root, environment, "deps")
    _run_dbt(
        dbt_executable,
        project_root,
        environment,
        "parse",
        "--target",
        "dev",
        "--vars",
        json.dumps(SELECTOR_PARSE_VARS),
        "--no-partial-parse",
        "--target-path",
        str(target_path),
        "--log-path",
        str(log_path),
    )

    return project_root, environment


def _resolved_names(
    resolved_project: tuple[Path, dict[str, str]],
    selector: str,
    resource_type: str,
) -> set[str]:
    project_root, environment = resolved_project
    result = _run_dbt(
        _dbt_executable(),
        project_root,
        environment,
        "ls",
        "--target",
        "dev",
        "--selector",
        selector,
        "--resource-type",
        resource_type,
        "--output",
        "json",
        "--quiet",
    )
    return {
        json.loads(line)["name"]
        for line in result.stdout.splitlines()
        if line.startswith("{")
    }


def test_incident_gold_selectors_reuse_full_contract_and_exclude_flow_scope():
    selectors = _selectors()

    expected = {
        FLOW_SCOPE,
        ROAD_CONTEXT_SCOPE,
        INCIDENT_MODELS,
        INCIDENT_GATE_TESTS,
        INCIDENT_HOURLY_TESTS,
        INCIDENT_FULL_TESTS,
    }
    assert expected <= selectors.keys()

    assert selectors[ROAD_CONTEXT_SCOPE] == {
        "union": [
            {
                "method": "fqn",
                "value": ROAD_CONTEXT_MODEL,
                "children": True,
            }
        ]
    }

    assert selectors[FLOW_SCOPE] == {
        "intersection": [
            {
                "union": [
                    {
                        "method": "fqn",
                        "value": "gold_traffic_flow_link_latest",
                        "children": True,
                    },
                    {
                        "method": "fqn",
                        "value": "gold_traffic_flow_change_latest",
                        "children": True,
                    },
                    {
                        "method": "fqn",
                        "value": "gold_traffic_flow_congestion_hotspots_hourly",
                        "children": True,
                    },
                    {
                        "method": "fqn",
                        "value": "gold_traffic_flow_link_time_profile",
                        "children": True,
                    },
                    {
                        "method": "fqn",
                        "value": "gold_traffic_flow_anomaly_current",
                        "children": True,
                    },
                ]
            },
            {
                "exclude": [
                    {
                        "method": "selector",
                        "value": ROAD_CONTEXT_SCOPE,
                    }
                ]
            },
        ]
    }

    assert selectors[INCIDENT_MODELS]["intersection"][0] == {
        "method": "selector",
        "value": "ask_seoul_traffic_transform_gold_models",
    }
    assert _excludes_flow_scope(selectors[INCIDENT_MODELS])
    assert {
        "method": "selector",
        "value": ROAD_CONTEXT_SCOPE,
    } in selectors[INCIDENT_MODELS]["intersection"][1]["exclude"]

    for name, parent in {
        INCIDENT_GATE_TESTS: "ask_seoul_traffic_transform_gold_gate_tests",
        INCIDENT_HOURLY_TESTS: "ask_seoul_traffic_transform_gold_hourly_tests",
        INCIDENT_FULL_TESTS: "ask_seoul_traffic_transform_gold_full_tests",
    }.items():
        assert selectors[name]["intersection"][0] == {"method": "selector", "value": parent}
        assert _excludes_flow_scope(selectors[name])
        assert {
            "method": "selector",
            "value": ROAD_CONTEXT_SCOPE,
        } in selectors[name]["intersection"][1]["exclude"]


def test_incident_gold_selectors_resolve_exact_model_and_test_sets(
    resolved_selector_project: tuple[Path, dict[str, str]],
):
    full_gold_models = _resolved_names(resolved_selector_project, FULL_GOLD_MODELS, "model")
    flow_models = _resolved_names(resolved_selector_project, FLOW_SCOPE, "model")
    road_context_models = _resolved_names(
        resolved_selector_project, ROAD_CONTEXT_SCOPE, "model"
    )
    incident_models = _resolved_names(resolved_selector_project, INCIDENT_MODELS, "model")

    assert len(full_gold_models) == EXPECTED_GOLD_MODEL_COUNT
    assert flow_models == EXPECTED_FLOW_MODELS
    assert road_context_models == {ROAD_CONTEXT_MODEL}
    assert incident_models == EXPECTED_INCIDENT_MODELS
    assert incident_models == full_gold_models - flow_models - road_context_models
    assert len(incident_models) == 9

    flow_tests = _resolved_names(resolved_selector_project, FLOW_SCOPE, "test")
    road_context_tests = _resolved_names(
        resolved_selector_project, ROAD_CONTEXT_SCOPE, "test"
    )
    for incident_selector, full_selector in {
        INCIDENT_GATE_TESTS: FULL_GATE_TESTS,
        INCIDENT_HOURLY_TESTS: FULL_HOURLY_TESTS,
        INCIDENT_FULL_TESTS: FULL_FULL_TESTS,
    }.items():
        full_tests = _resolved_names(resolved_selector_project, full_selector, "test")
        incident_tests = _resolved_names(resolved_selector_project, incident_selector, "test")

        assert incident_tests == full_tests - flow_tests - road_context_tests
        assert incident_tests.isdisjoint(flow_tests)
        assert len(incident_tests) == EXPECTED_INCIDENT_TEST_COUNTS[incident_selector]


def test_flow_silver_selectors_are_narrow_and_resolve_the_pinned_row_gate(
    resolved_selector_project: tuple[Path, dict[str, str]],
):
    selectors = _selectors()

    assert selectors[FLOW_SILVER_MODEL] == {
        "intersection": [
            {
                "method": "fqn",
                "value": "silver_seoul_traffic_flow",
                "indirect_selection": "empty",
            },
            {"method": "resource_type", "value": "model"},
        ]
    }
    assert selectors[FLOW_SILVER_TESTS] == {
        "intersection": [
            {
                "method": "fqn",
                "value": "*silver_seoul_traffic_flow*",
                "indirect_selection": "empty",
            },
            {"method": "resource_type", "value": "test"},
        ]
    }

    assert _resolved_names(
        resolved_selector_project, FLOW_SILVER_MODEL, "model"
    ) == {"silver_seoul_traffic_flow"}
    flow_silver_tests = _resolved_names(
        resolved_selector_project, FLOW_SILVER_TESTS, "test"
    )
    assert flow_silver_tests == EXPECTED_FLOW_SILVER_TESTS


def test_incident_silver_selector_excludes_flow_scope():
    selectors = _selectors()

    assert selectors[SILVER_EXECUTION_TAG] == {
        "method": "tag",
        "value": SILVER_EXECUTION_TAG,
        "indirect_selection": "cautious",
    }
    assert selectors[INCIDENT_SILVER] == {
        "intersection": [
            {"method": "selector", "value": SILVER_EXECUTION_TAG},
            {
                "exclude": [
                    {
                        "method": "fqn",
                        "value": "*silver_seoul_traffic_flow*",
                        "indirect_selection": "empty",
                    },
                    *[
                        {
                            "method": "fqn",
                            "value": model,
                            "indirect_selection": "empty",
                        }
                        for model in sorted(LINK_REFERENCE_SILVER_MODELS)
                    ],
                ]
            },
        ]
    }


def test_incident_silver_resolves_only_incident_owned_models_and_tests(
    resolved_selector_project: tuple[Path, dict[str, str]],
):
    incident_models = _resolved_names(
        resolved_selector_project, INCIDENT_SILVER, "model"
    )
    incident_tests = _resolved_names(
        resolved_selector_project, INCIDENT_SILVER, "test"
    )
    flow_tests = _resolved_names(
        resolved_selector_project, FLOW_SILVER_TESTS, "test"
    )

    assert incident_models == EXPECTED_INCIDENT_SILVER_MODELS
    assert incident_tests.isdisjoint(flow_tests)
    assert "assert_silver_seoul_traffic_flow_pinned_rows" not in incident_tests
    assert "assert_traffic_current_pinned_publishable_run" in incident_tests


def test_incident_preflight_combines_availability_and_bronze_contracts(
    resolved_selector_project: tuple[Path, dict[str, str]],
):
    combined = _resolved_names(resolved_selector_project, INCIDENT_PREFLIGHT, "test")
    availability = _resolved_names(
        resolved_selector_project,
        "ask_seoul_traffic_transform_availability",
        "test",
    )
    bronze_contracts = _resolved_names(
        resolved_selector_project,
        "traffic_transform_contract_gate",
        "test",
    )

    assert combined == availability | bronze_contracts


def test_hot_build_selectors_resolve_exact_models_and_compound_receipts(
    resolved_selector_project: tuple[Path, dict[str, str]],
):
    assert _resolved_names(
        resolved_selector_project, INCIDENT_HOT_BUILD, "model"
    ) == EXPECTED_INCIDENT_SILVER_MODELS
    assert _resolved_names(
        resolved_selector_project, INCIDENT_HOT_BUILD, "test"
    ) == {"assert_traffic_incident_silver_publication_receipt"}
    assert _resolved_names(
        resolved_selector_project, FLOW_HOT_BUILD, "model"
    ) == {"silver_seoul_traffic_flow", *LINK_REFERENCE_SILVER_MODELS}
    assert _resolved_names(
        resolved_selector_project, FLOW_HOT_BUILD, "test"
    ) == {"assert_traffic_flow_silver_publication_receipt"}
    assert _resolved_names(
        resolved_selector_project, CORE_GOLD_HOT_BUILD, "model"
    ) == EXPECTED_D1_HOT_MODELS
    assert _resolved_names(
        resolved_selector_project, CORE_GOLD_HOT_BUILD, "test"
    ) == {"assert_traffic_core_gold_serving_publication_receipt"}
    assert _resolved_names(
        resolved_selector_project, CORE_GOLD_INCIDENT_HOT_BUILD, "model"
    ) == {
        "gold_traffic_incident_current_by_admin_dong_hourly",
    }
    assert _resolved_names(
        resolved_selector_project, CORE_GOLD_INCIDENT_HOT_BUILD, "test"
    ) == {"assert_traffic_core_gold_serving_publication_receipt"}
    assert _resolved_names(
        resolved_selector_project, CROSS_DOMAIN_GOLD_HOT_BUILD, "model"
    ) == {
        "gold_traffic_incident_current_by_admin_dong_hourly",
        "gold_traffic_incident_x_weather_current_hourly",
        ROAD_CONTEXT_MODEL,
    }
    assert _resolved_names(
        resolved_selector_project, CROSS_DOMAIN_GOLD_HOT_BUILD, "test"
    ) == {"assert_traffic_gold_serving_publication_receipt"}

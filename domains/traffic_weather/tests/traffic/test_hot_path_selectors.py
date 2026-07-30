from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTORS_PATH = PROJECT_ROOT / "selectors.yml"
HOT_TESTS = Path(__file__).resolve().parent / "hot_path"

INCIDENT_HOT = "ask_seoul_traffic_transform_incident_hot_build"
FLOW_HOT = "ask_seoul_traffic_transform_flow_hot_build"
GOLD_HOT = "ask_seoul_traffic_transform_gold_hot_build"
GOLD_INCIDENT_HOT = "ask_seoul_traffic_transform_gold_incident_hot_build"
GOLD_BOOTSTRAP_HOT = "ask_seoul_traffic_transform_gold_bootstrap_hot_build"
GOLD_INCIDENT_BOOTSTRAP_HOT = (
    "ask_seoul_traffic_transform_gold_incident_bootstrap_hot_build"
)
DAILY_ASSURANCE = "ask_seoul_traffic_daily_assurance"

INCIDENT_RECEIPT = "assert_traffic_incident_silver_publication_receipt"
FLOW_RECEIPT = "assert_traffic_flow_silver_publication_receipt"
GOLD_RECEIPT = "assert_traffic_gold_serving_publication_receipt"

TRAFFIC_D1_MODELS = {
    "gold_traffic_incident_x_weather_current_hourly",
    "gold_traffic_flow_congestion_hotspots_hourly",
    "gold_traffic_flow_link_latest",
    "gold_traffic_flow_change_latest",
    "gold_traffic_flow_link_time_profile",
    "gold_traffic_flow_anomaly_current",
}
TRAFFIC_INCIDENT_ANCHOR = "gold_traffic_incident_current_by_admin_dong_hourly"


def _selectors() -> dict[str, dict]:
    values = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))["selectors"]
    return {item["name"]: item["definition"] for item in values}


def _explicit_fqns(definition: dict) -> set[str]:
    return {
        item["value"]
        for item in definition["union"]
        if item.get("method") == "fqn"
    }


def test_hot_path_selectors_define_exact_traffic_models_and_receipts():
    selectors = _selectors()

    assert _explicit_fqns(selectors[INCIDENT_HOT]) == {
        "silver_seoul_traffic_incident",
        "silver_seoul_traffic_incident_current",
        INCIDENT_RECEIPT,
    }
    assert _explicit_fqns(selectors[FLOW_HOT]) == {
        "silver_seoul_traffic_flow",
        FLOW_RECEIPT,
    }
    assert _explicit_fqns(selectors[GOLD_HOT]) == TRAFFIC_D1_MODELS | {
        GOLD_RECEIPT
    }
    assert _explicit_fqns(selectors[GOLD_INCIDENT_HOT]) == {
        "gold_traffic_incident_x_weather_current_hourly",
        GOLD_RECEIPT,
    }


def test_gold_bootstrap_selectors_add_only_the_missing_incident_anchor():
    selectors = _selectors()

    assert _explicit_fqns(selectors[GOLD_BOOTSTRAP_HOT]) == (
        TRAFFIC_D1_MODELS | {TRAFFIC_INCIDENT_ANCHOR, GOLD_RECEIPT}
    )
    assert _explicit_fqns(selectors[GOLD_INCIDENT_BOOTSTRAP_HOT]) == {
        TRAFFIC_INCIDENT_ANCHOR,
        "gold_traffic_incident_x_weather_current_hourly",
        GOLD_RECEIPT,
    }


def test_daily_assurance_preserves_every_full_traffic_contract_family():
    selectors = _selectors()
    selected = {
        item["value"]
        for item in selectors[DAILY_ASSURANCE]["union"]
        if item.get("method") == "selector"
    }

    assert selected == {
        "ask_seoul_traffic_transform_incident_preflight_contracts",
        "ask_seoul_traffic_transform_silver",
        "ask_seoul_traffic_transform_flow_silver_tests",
        "ask_seoul_traffic_transform_common_admin",
        "ask_seoul_traffic_transform_asac_axes_contract",
        "ask_seoul_traffic_transform_gold_full_tests_without_commerce",
    }


def test_compound_receipts_are_fail_closed_for_pinned_identity_and_critical_keys():
    incident = (HOT_TESTS / f"{INCIDENT_RECEIPT}.sql").read_text(encoding="utf-8")
    flow = (HOT_TESTS / f"{FLOW_RECEIPT}.sql").read_text(encoding="utf-8")
    gold = (HOT_TESTS / f"{GOLD_RECEIPT}.sql").read_text(encoding="utf-8")

    assert "var('traffic_snapshot_dag_run_id')" in incident
    assert "missing_pinned_run" in incident
    assert "stale_or_mixed_current_row" in incident
    assert "missing_current_row" in incident
    assert "extra_current_row" in incident
    assert "invalid_critical_field" in incident
    assert "duplicate_source_record_id" in incident

    assert "var('traffic_flow_snapshot_dag_run_id', '')" in flow
    assert "missing_pinned_run" in flow
    assert "invalid_critical_field" in flow
    assert "duplicate_link_id" in flow

    assert "var('traffic_flow_snapshot_dag_run_id', '')" in gold
    assert "invalid_product_row_id" in gold
    assert "duplicate_product_row_id" in gold
    assert "ref(model_name)" in gold
    for model in TRAFFIC_D1_MODELS:
        assert model in gold


def test_receipt_anti_join_keeps_right_alias_addressable_in_trino():
    for receipt_name in (INCIDENT_RECEIPT, FLOW_RECEIPT):
        receipt = (HOT_TESTS / f"{receipt_name}.sql").read_text(encoding="utf-8")

        assert "left join pinned_run using (dag_run_id)" not in receipt
        assert (
            "on pinned_run.dag_run_id = configured_run.dag_run_id"
            in receipt
        )

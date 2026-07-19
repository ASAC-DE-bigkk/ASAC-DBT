from pathlib import Path

import yaml


SELECTORS = Path(__file__).resolve().parents[2] / "selectors.yml"

FLOW_SCOPE = "ask_seoul_traffic_transform_flow_gold_scope"
INCIDENT_MODELS = "ask_seoul_traffic_transform_gold_incident_models"
INCIDENT_GATE_TESTS = "ask_seoul_traffic_transform_gold_incident_gate_tests"
INCIDENT_HOURLY_TESTS = "ask_seoul_traffic_transform_gold_incident_hourly_tests"
INCIDENT_FULL_TESTS = "ask_seoul_traffic_transform_gold_incident_full_tests"


def _selectors() -> dict:
    values = yaml.safe_load(SELECTORS.read_text(encoding="utf-8"))["selectors"]
    return {item["name"]: item["definition"] for item in values}


def _excludes_flow_scope(definition: dict) -> bool:
    return {"method": "selector", "value": FLOW_SCOPE} in definition["intersection"][1]["exclude"]


def test_incident_gold_selectors_reuse_full_contract_and_exclude_flow_scope():
    selectors = _selectors()

    expected = {
        FLOW_SCOPE,
        INCIDENT_MODELS,
        INCIDENT_GATE_TESTS,
        INCIDENT_HOURLY_TESTS,
        INCIDENT_FULL_TESTS,
    }
    assert expected <= selectors.keys()

    assert selectors[FLOW_SCOPE] == {
        "union": [
            {"method": "fqn", "value": "gold_traffic_flow_link_latest", "children": True},
            {"method": "fqn", "value": "gold_traffic_flow_change_latest", "children": True},
            {
                "method": "fqn",
                "value": "gold_traffic_flow_congestion_hotspots_hourly",
                "children": True,
            },
            {"method": "fqn", "value": "gold_traffic_flow_link_time_profile", "children": True},
        ]
    }

    assert selectors[INCIDENT_MODELS]["intersection"][0] == {
        "method": "selector",
        "value": "ask_seoul_traffic_transform_gold_models",
    }
    assert _excludes_flow_scope(selectors[INCIDENT_MODELS])

    for name, parent in {
        INCIDENT_GATE_TESTS: "ask_seoul_traffic_transform_gold_gate_tests",
        INCIDENT_HOURLY_TESTS: "ask_seoul_traffic_transform_gold_hourly_tests",
        INCIDENT_FULL_TESTS: "ask_seoul_traffic_transform_gold_full_tests",
    }.items():
        assert selectors[name]["intersection"][0] == {"method": "selector", "value": parent}
        assert _excludes_flow_scope(selectors[name])

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


MANIFEST_ENV = "ASK_SEOUL_FRESH_MANIFEST"
ANALYSIS_NODE_ID = "analysis.asac_seoul.admin_dong_hour_context"
EXPECTED_PUBLIC_MODELS = {
    "model.asac_seoul.gold_traffic_incident_current_by_admin_dong_hourly",
    "model.asac_seoul.gold_weather_forecast_by_admin_dong",
}


def test_fresh_analysis_node_has_real_traffic_weather_manifest_edges() -> None:
    manifest_value = os.environ.get(MANIFEST_ENV)
    if manifest_value is None:
        pytest.skip(f"{MANIFEST_ENV} is set by the fresh dbt parse integration gate")

    manifest_path = Path(manifest_value)
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    node = manifest["nodes"][ANALYSIS_NODE_ID]

    assert node["resource_type"] == "analysis"
    assert set(node["depends_on"]["nodes"]) == EXPECTED_PUBLIC_MODELS

    expected_groups = {
        "model.asac_seoul.gold_traffic_incident_current_by_admin_dong_hourly": (
            "traffic"
        ),
        "model.asac_seoul.gold_weather_forecast_by_admin_dong": "weather",
    }
    for node_id, expected_group in expected_groups.items():
        producer = manifest["nodes"][node_id]
        assert producer["access"] == "public"
        assert producer["group"] == expected_group

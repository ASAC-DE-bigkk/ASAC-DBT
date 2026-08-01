from __future__ import annotations

from pathlib import Path

import yaml


PROJECT_DIR = Path(__file__).resolve().parents[1]
GOLD_DIRS = (
    PROJECT_DIR / "models" / "traffic" / "transform" / "gold",
    PROJECT_DIR / "models" / "weather" / "transform" / "gold",
)

EXPECTED_PRODUCTS = {
    "traffic_incident_x_weather_current_hourly",
    "traffic_flow_congestion_hotspots_hourly",
    "traffic_flow_link_latest",
    "traffic_flow_change_latest",
    "traffic_flow_link_time_profile",
    "traffic_flow_anomaly_current",
    "weather_place_current_outlook",
    "weather_place_precipitation_window",
    "weather_place_risk_window",
    "weather_place_forecast_change_daily",
}

EXPECTED_PUBLIC_PROJECTIONS = {
    "weather_place_current_outlook": [
        "product_row_id", "place_id", "place_name", "alias_names", "admin_dong_code", "admin_dong",
        "gu_code", "gu", "latitude", "longitude", "forecast_at", "forecast_category_count",
        "forecast_issued_at_min", "forecast_issued_at_max", "forecast_collected_at_max", "temp_c",
        "humidity_pct", "wind_ms", "wind_dir_deg", "precip_prob_pct", "sky_code", "sky_label",
        "pty_code", "pty_label", "is_precipitating", "pcp_raw", "pcp_mm", "sno_raw", "sno_cm",
        "forecast_lead_hours",
    ],
    "weather_place_precipitation_window": [
        "product_row_id", "place_id", "window_start_at", "window_end_at",
    ],
    "weather_place_risk_window": [
        "product_row_id", "place_id", "forecast_at", "risk_labels",
    ],
    "weather_place_forecast_change_daily": [
        "product_row_id", "place_id", "forecast_date", "latest_issued_at", "change_state",
    ],
    "traffic_incident_x_weather_current_hourly": [
        "product_row_id", "admin_dong_code", "hour_at", "admin_dong", "gu_code", "gu",
        "admin_dong_revision_date", "incident_count", "has_incident", "quality_state",
        "snapshot_as_of_at", "status_observed_at", "published_at", "weather_category_coverage_count",
        "weather_latest_issued_at", "weather_latest_collected_at", "weather_latest_published_at",
        "tmp_value_num", "pop_value_num", "reh_value_num", "wsd_value_num", "sky_qualitative_code",
        "pty_qualitative_code", "is_precipitating",
    ],
    "traffic_flow_congestion_hotspots_hourly": [
        "product_row_id", "link_id", "hour_at", "flow_speed", "flow_travel_time",
        "flow_value_quality", "observed_at_kst", "congestion_rank", "observed_link_count",
        "hotspot_state",
    ],
    "traffic_flow_link_latest": [
        "product_row_id", "link_id", "flow_speed", "flow_travel_time", "flow_value_quality",
        "observed_at_kst", "collected_at_kst",
    ],
    "traffic_flow_change_latest": [
        "product_row_id", "link_id", "flow_speed", "flow_travel_time", "flow_value_quality",
        "observed_at_utc", "observed_at_kst", "previous_flow_speed", "previous_flow_travel_time",
        "previous_observed_at_kst", "flow_speed_change", "flow_travel_time_change", "speed_change_state",
    ],
    "traffic_flow_link_time_profile": [
        "product_row_id", "link_id", "kst_day_of_week", "kst_hour", "observation_count",
        "speed_observation_count", "avg_flow_speed", "min_flow_speed", "max_flow_speed",
        "avg_flow_travel_time", "first_observed_at_kst", "last_observed_at_kst",
    ],
    "traffic_flow_anomaly_current": [
        "product_row_id", "link_id", "flow_speed", "flow_travel_time", "flow_value_quality",
        "observed_at_kst", "collected_at_kst", "kst_day_of_week", "kst_hour",
        "profile_observation_count", "distinct_observation_date_count", "speed_observation_count",
        "p25_flow_speed", "median_flow_speed", "p75_flow_speed", "profile_first_observed_at_kst",
        "profile_last_observed_at_kst", "baseline_state", "speed_delta_from_median",
        "speed_ratio_to_median", "anomaly_direction",
    ],
}

INTERNAL_PUBLIC_FIELD_FRAGMENTS = {
    "raw_object_key",
    "payload_hash",
    "request_id",
    "dag_run_id",
    "source_run_id",
    "snapshot_dag_run_id",
    "representative_dag_run_id",
    "api_key",
    "service_key",
    "access_key",
    "secret",
    "token",
    "password",
    "credential",
    "email",
    "ip_address",
}

REQUIRED_SERVING_FIELDS = {
    "enabled",
    "external",
    "product_id",
    "product_question",
    "grain",
    "primary_key",
    "publication_mode",
    "zero_policy",
    "publication_trigger",
}

LEGACY_SERVING_FIELDS = {
    "serving_tier",
    "serving_gold_candidate",
    "external",
    "refresh",
}


def _models() -> dict[str, dict]:
    models: dict[str, dict] = {}
    for directory in GOLD_DIRS:
        for path in directory.glob("*.yml"):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for model in payload.get("models", []):
                models[model["name"]] = model
    return models


def _test_names(column: dict) -> set[str]:
    names: set[str] = set()
    for test in column.get("tests", []):
        if isinstance(test, str):
            names.add(test)
        elif isinstance(test, dict):
            names.update(test)
    return names


def test_public_d1_products_have_complete_non_legacy_serving_contracts() -> None:
    models = _models()

    for product_id in EXPECTED_PRODUCTS:
        model_name = f"gold_{product_id}"
        assert model_name in models, f"missing dbt model contract: {model_name}"

        model = models[model_name]
        meta = model.get("config", {}).get("meta", {})
        serving = meta.get("serving")
        assert serving is not None, f"missing meta.serving: {model_name}"
        assert serving["product_id"] == product_id
        assert REQUIRED_SERVING_FIELDS <= serving.keys()
        assert serving["enabled"] is True
        assert serving["external"] is True
        assert LEGACY_SERVING_FIELDS.isdisjoint(meta)

        columns = {
            column["name"]: column
            for column in model.get("columns", [])
        }
        for primary_key in serving["primary_key"]:
            assert primary_key in columns
            assert "not_null" in _test_names(columns[primary_key])


def test_public_d1_product_ids_are_unique() -> None:
    products: list[str] = []
    for model in _models().values():
        serving = model.get("config", {}).get("meta", {}).get("serving")
        if serving is not None:
            products.append(serving["product_id"])

    assert len(products) == len(set(products))


def test_enabled_external_d1_products_match_portfolio() -> None:
    active_products = {
        serving["product_id"]
        for model in _models().values()
        if (serving := model.get("config", {}).get("meta", {}).get("serving"))
        and serving.get("enabled") is True
        and serving.get("external") is True
    }

    assert active_products == EXPECTED_PRODUCTS


def test_public_d1_products_declare_exact_ordered_public_projection() -> None:
    models = _models()

    assert set(EXPECTED_PUBLIC_PROJECTIONS) == EXPECTED_PRODUCTS
    for product_id, expected_columns in EXPECTED_PUBLIC_PROJECTIONS.items():
        model = models[f"gold_{product_id}"]
        serving = model["config"]["meta"]["serving"]

        assert serving["public_projection"] == {
            "schema_version": "1.0.0",
            "columns": expected_columns,
        }


def test_public_d1_projection_columns_are_declared_and_public_safe() -> None:
    models = _models()

    for product_id, expected_columns in EXPECTED_PUBLIC_PROJECTIONS.items():
        model = models[f"gold_{product_id}"]
        columns = {column["name"]: column for column in model.get("columns", [])}

        for column_name in expected_columns:
            assert column_name in columns, f"{product_id}.{column_name} missing column declaration"
            lowered = column_name.lower()
            assert not any(fragment in lowered for fragment in INTERNAL_PUBLIC_FIELD_FRAGMENTS), (
                f"{product_id}.{column_name} exposes an internal/secret identifier"
            )
            column = columns[column_name]
            meta = column.get("config", {}).get("meta", {})
            assert column.get("description"), f"{product_id}.{column_name} missing description"
            assert column.get("data_type"), f"{product_id}.{column_name} missing data_type"
            assert meta.get("semantic_role"), f"{product_id}.{column_name} missing semantic_role"
            assert isinstance(meta.get("nullable"), bool), f"{product_id}.{column_name} missing nullable boolean"
            assert meta.get("null_meaning"), f"{product_id}.{column_name} missing null_meaning"
            assert meta.get("unit"), f"{product_id}.{column_name} missing unit"

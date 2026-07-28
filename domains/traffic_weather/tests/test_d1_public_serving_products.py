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

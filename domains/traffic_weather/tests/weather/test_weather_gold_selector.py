from pathlib import Path

import yaml


SELECTORS_PATH = Path(__file__).resolve().parents[2] / "selectors.yml"
GOLD_SELECTOR = "ask_seoul_weather_transform_gold"
COMMERCE_SCOPE = "ask_seoul_weather_transform_commerce_gold_scope"
SCHEDULED_SELECTOR = "ask_seoul_weather_transform_gold_without_commerce"
SERVING_SELECTOR = "ask_seoul_weather_transform_serving_products"
SNAPSHOT_REFRESH_SELECTOR = "ask_seoul_weather_serving_snapshot_refresh"
HISTORICAL_SERVING_SELECTOR = "ask_seoul_weather_historical_serving_products"
SERVING_MODELS = {
    "gold_weather_place_hourly_outlook",
    "gold_weather_place_current_outlook",
    "gold_weather_place_precipitation_window",
    "gold_weather_place_risk_window",
    "gold_weather_place_forecast_change_daily",
    "gold_weather_grid_hourly_outlook",
    "gold_weather_grid_current_outlook",
    "gold_weather_grid_precipitation_window",
}
HISTORICAL_SERVING_MODELS = {
    "gold_weather_place_hourly_outlook",
    "gold_weather_place_daily_outlook",
    *SERVING_MODELS,
}
SNAPSHOT_REFRESH_MODELS = {
    "gold_weather_place_hourly_outlook",
    "gold_weather_place_current_outlook",
    "gold_weather_place_precipitation_window",
    "gold_weather_place_risk_window",
    "gold_weather_place_forecast_change_daily",
}


def _selectors() -> dict[str, dict]:
    document = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))
    return {
        selector["name"]: selector["definition"] for selector in document["selectors"]
    }


def test_full_weather_gold_keeps_cross_domain_scope():
    selectors = _selectors()

    assert GOLD_SELECTOR in selectors
    assert COMMERCE_SCOPE not in selectors
    assert SCHEDULED_SELECTOR not in selectors


def test_weather_serving_selector_rebuilds_products_from_shared_hourly_source():
    selectors = _selectors()

    definition = selectors[SERVING_SELECTOR]
    selected_models = {
        item["value"]
        for item in definition["union"]
        if item["method"] == "fqn"
    }
    assert selected_models == SERVING_MODELS
    assert all(item["indirect_selection"] == "cautious" for item in definition["union"])


def test_hourly_serving_snapshot_refresh_excludes_grid_audit_models():
    selectors = _selectors()

    definition = selectors[SNAPSHOT_REFRESH_SELECTOR]
    selected_models = {
        item["value"]
        for item in definition["union"]
        if item["method"] == "fqn"
    }

    assert selected_models == SNAPSHOT_REFRESH_MODELS
    assert all(
        item["indirect_selection"] == "cautious"
        for item in definition["union"]
        if item["method"] == "fqn"
    )


def test_weather_historical_serving_selector_rebuilds_serving_dependencies():
    selectors = _selectors()

    definition = selectors[HISTORICAL_SERVING_SELECTOR]
    selected_models = {
        item["value"]
        for item in definition["union"]
        if item["method"] == "fqn"
    }
    assert selected_models == HISTORICAL_SERVING_MODELS
    assert all(item["indirect_selection"] == "cautious" for item in definition["union"])

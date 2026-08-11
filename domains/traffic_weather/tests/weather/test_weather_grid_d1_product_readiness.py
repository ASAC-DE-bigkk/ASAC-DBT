from pathlib import Path

import yaml


PROJECT_DIR = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_DIR / "models" / "weather" / "transform" / "gold"

CURRENT_YML = GOLD_DIR / "gold_weather_grid_current_outlook.yml"
CURRENT_SQL = GOLD_DIR / "gold_weather_grid_current_outlook.sql"
HOURLY_YML = GOLD_DIR / "gold_weather_grid_hourly_outlook.yml"
PRECIP_YML = GOLD_DIR / "gold_weather_grid_precipitation_window.yml"
PRECIP_SQL = GOLD_DIR / "gold_weather_grid_precipitation_window.sql"
PLACE_SERVING_YML = GOLD_DIR / "_serving_gold.yml"

CURRENT_PROJECTION = [
    "product_row_id", "grid_id", "nx", "ny", "coverage_scope", "forecast_at",
    "forecast_category_count", "forecast_issued_at_min", "forecast_issued_at_max",
    "forecast_collected_at_max", "temp_c", "humidity_pct", "wind_ms",
    "wind_dir_deg", "precip_prob_pct", "sky_code", "sky_label", "pty_code",
    "pty_label", "is_precipitating", "pcp_raw", "pcp_mm", "sno_raw", "sno_cm",
    "forecast_lead_hours",
]
PRECIP_PROJECTION = [
    "product_row_id", "grid_id", "nx", "ny", "coverage_scope", "window_start_at",
    "window_end_at", "precipitation_hour_count", "precip_prob_max_pct", "pcp_max_mm",
    "sno_max_cm", "forecast_issued_at_min", "forecast_issued_at_max",
    "forecast_collected_at_max",
]


def _model(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["models"][0]


def _models_by_name(path: Path) -> dict[str, dict]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {model["name"]: model for model in payload["models"]}


def test_grid_gold_contracts_are_retained_for_internal_audit_not_public_d1() -> None:
    assert CURRENT_YML.exists()
    assert CURRENT_SQL.exists()
    assert PRECIP_YML.exists()
    assert PRECIP_SQL.exists()

    current_model = _model(CURRENT_YML)
    precipitation_model = _model(PRECIP_YML)
    current = current_model["config"]["meta"]["serving"]
    precipitation = precipitation_model["config"]["meta"]["serving"]

    assert current_model["access"] == "protected"
    assert precipitation_model["access"] == "protected"

    assert current["product_id"] == "weather_grid_current_outlook"
    assert current["enabled"] is False
    assert current["external"] is False
    assert current["retire_on_publish"] is True
    assert current["zero_policy"] == "fail"
    assert current["quality_coverage"] == {
        "field": "grid_id",
        "expected_distinct_count": 80,
        "minimum_ratio": 1.0,
        "measurement_scope": "published_rows",
    }
    assert current["public_projection"]["columns"] == CURRENT_PROJECTION

    assert precipitation["product_id"] == "weather_grid_precipitation_window"
    assert precipitation["enabled"] is False
    assert precipitation["external"] is False
    assert precipitation["retire_on_publish"] is True
    assert precipitation["zero_policy"] == "allow"
    assert precipitation["empty_result_freshness"] == {
        "relation": "gold_weather_grid_hourly_outlook",
        "field": "forecast_collected_at_max",
    }
    assert precipitation["public_projection"]["columns"] == PRECIP_PROJECTION
    assert "not_applicable_reason" in precipitation["quality_coverage"]


def test_empty_result_freshness_sources_declare_their_physical_column() -> None:
    place_hourly = _models_by_name(PLACE_SERVING_YML)[
        "gold_weather_place_hourly_outlook"
    ]
    grid_hourly = _model(HOURLY_YML)

    for hourly in (place_hourly, grid_hourly):
        columns = {column["name"] for column in hourly["columns"]}
        assert "forecast_collected_at_max" in columns


def test_grid_gold_models_preserve_grid_grain_without_place_fanout() -> None:
    hourly_sql = (GOLD_DIR / "gold_weather_grid_hourly_outlook.sql").read_text(
        encoding="utf-8"
    )
    current_sql = CURRENT_SQL.read_text(encoding="utf-8")
    precip_sql = PRECIP_SQL.read_text(encoding="utf-8")

    assert "ref('gold_weather_forecast_by_grid_serving')" in hourly_sql
    assert "partition by hourly.grid_id" in current_sql
    assert "partition by grid_id" in precip_sql
    assert "dim_weather_place" not in hourly_sql

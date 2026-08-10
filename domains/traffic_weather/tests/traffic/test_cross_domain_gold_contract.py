from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"
GOLD_TEST_DIR = PROJECT_ROOT / "tests" / "traffic" / "transform" / "gold"
TRAFFIC_DOCS_DIR = PROJECT_ROOT / "docs" / "traffic"
PORTFOLIO_CATALOG = PROJECT_ROOT / "contracts" / "serving_gold_catalog.yml"
WEATHER_MODEL_PATH = GOLD_DIR / "gold_traffic_incident_x_weather_current_hourly.sql"
WEATHER_NO_HINDSIGHT_TEST_PATH = (
    GOLD_TEST_DIR
    / "assert_gold_traffic_incident_x_weather_current_hourly_no_hindsight.sql"
)


def _compact(text: str) -> str:
    return " ".join(text.lower().split())


def _gold_models() -> dict[str, dict]:
    models: dict[str, dict] = {}
    for yml_path in sorted(GOLD_DIR.glob("*.yml")):
        document = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
        for model in document.get("models", []):
            models[model["name"]] = model
    return models


def test_design_and_implementation_plan_exist_for_issue_234() -> None:
    specs = list(
        (TRAFFIC_DOCS_DIR / "superpowers" / "specs").glob(
            "2026-07-16-traffic-cross-domain-gold*.md"
        )
    )
    plans = list(
        (TRAFFIC_DOCS_DIR / "superpowers" / "plans").glob(
            "2026-07-16-traffic-cross-domain-gold*.md"
        )
    )
    assert specs
    assert plans
    assert any(
        "gold_traffic_incident_x_weather_current_hourly" in path.read_text(
            encoding="utf-8"
        )
        for path in sorted(specs + plans)
    )


def test_cross_domain_gold_metadata_locks_served_weather_context_products() -> None:
    models = _gold_models()
    actual = {
        name
        for name, model in models.items()
        if model.get("config", {}).get("meta", {}).get("cross_domain_gold") is True
    }
    assert actual == {
        "gold_traffic_incident_x_weather_current_hourly",
        "gold_traffic_road_congestion_context_current",
    }


def test_unserved_traffic_cross_domain_leaves_are_removed_from_catalog() -> None:
    catalog = yaml.safe_load(PORTFOLIO_CATALOG.read_text(encoding="utf-8"))
    serving_models = set(catalog["domains"]["traffic"]["serving_models"])
    removed = {
        "gold_traffic_incident_x_citydata_crowding_current_hourly",
        "gold_traffic_incident_x_citydata_live_context_current",
        "gold_traffic_incident_x_transit_hourly",
        "gold_traffic_incident_x_culture_activity_daily",
        "gold_traffic_incident_x_culture_event_schedule_daily",
        "gold_traffic_incident_x_commerce_business_exposure_current",
    }
    assert serving_models.isdisjoint(removed)
    for model_name in removed:
        assert not (GOLD_DIR / f"{model_name}.sql").exists()


def test_weather_cross_domain_gold_contract() -> None:
    sql = WEATHER_MODEL_PATH.read_text(encoding="utf-8")
    compact_sql = _compact(sql)

    assert "ref('gold_traffic_incident_current_by_admin_dong_hourly')" in sql
    assert "ref('bridge_weather_admin_dong_grid')" in sql
    assert "ref('silver_kma_vilage_fcst_grid')" in sql
    assert "ref('asac_seoul', 'gold_weather_forecast_by_admin_dong')" not in sql
    assert "-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}" in sql
    assert "from {{ asac_axes.pinned_dim_admin_dong() }}" in sql
    assert "cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'" in compact_sql
    assert "traffic.admin_dong_code = weather_bridge.admin_dong_code" in compact_sql
    assert "weather_bridge.nx = weather.nx" in compact_sql
    assert "weather_bridge.ny = weather.ny" in compact_sql
    assert (
        "cast(date_trunc('hour', weather.forecast_at) as timestamp(6)) = traffic.hour_at"
        in compact_sql
    )
    assert "weather.issued_at <= traffic.status_observed_at" in compact_sql
    assert "weather_w2_grid_winner_order_key('weather')" in sql
    assert "lower(weather.category) in ('tmp', 'pop', 'reh', 'wsd', 'sky', 'pty')" in compact_sql
    assert "count(distinct category) as weather_category_coverage_count" in compact_sql
    assert "max(issued_at) as weather_latest_issued_at" in compact_sql
    assert "traffic.incident_count" in compact_sql
    assert "traffic.has_incident" in compact_sql
    assert "traffic.quality_state" in compact_sql


def test_weather_no_hindsight_guard_detects_missing_expected_categories() -> None:
    sql = _compact(WEATHER_NO_HINDSIGHT_TEST_PATH.read_text(encoding="utf-8"))
    assert "count(distinct lower(cast(weather.category as varchar)))" in sql
    assert "expected_category_coverage_count" in sql
    assert "weather_category_coverage_count" in sql
    assert "full outer join eligible_weather" in sql

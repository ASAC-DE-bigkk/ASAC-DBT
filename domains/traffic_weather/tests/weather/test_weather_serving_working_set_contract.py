from __future__ import annotations

from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
MODEL = (
    PROJECT_DIR
    / "models"
    / "weather"
    / "transform"
    / "place_mart"
    / "silver_weather_forecast_by_admin_dong_serving.sql"
)
GOLD = (
    PROJECT_DIR
    / "models"
    / "weather"
    / "transform"
    / "gold"
    / "gold_weather_place_forecast_change_daily.sql"
)


def test_serving_working_set_is_partitioned_and_bounded_before_fanout() -> None:
    sql = MODEL.read_text(encoding="utf-8")

    assert "incremental_strategy='merge'" in sql
    assert "full_refresh=false" in sql
    assert "ARRAY['day(forecast_at)']" in sql
    assert "delete from {{ this }} where cast(forecast_at as date) <" in sql
    assert "cast(forecast_at as date) >= kst_window.min_forecast_date" in sql
    assert "max_by(" in sql
    assert sql.index("selected_grid_forecast as") < sql.index("joined_payload as")
    assert "row_number() over" not in sql


def test_public_forecast_change_reads_the_bounded_serving_relation() -> None:
    sql = GOLD.read_text(encoding="utf-8")

    assert "ref('silver_weather_forecast_by_admin_dong_serving')" in sql
    assert "ref('silver_weather_forecast_by_admin_dong')" not in sql

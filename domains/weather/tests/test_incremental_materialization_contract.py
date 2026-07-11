from pathlib import Path


WEATHER_DIR = Path(__file__).parents[1]


def test_grid_silver_declares_incremental_merge_and_grain_key():
    sql = (WEATHER_DIR / "models/silver/silver_kma_vilage_fcst.sql").read_text()
    assert "materialized='incremental'" in sql
    assert "incremental_strategy='merge'" in sql
    assert "unique_key=['place_id', 'nx', 'ny', 'base_date', 'base_time', 'category', 'fcst_date', 'fcst_time']" in sql
    assert "interval '30' minute" in sql


def test_admin_dong_silver_declares_incremental_merge_and_grain_key():
    sql = (WEATHER_DIR / "models/silver/silver_weather_forecast_by_admin_dong.sql").read_text()
    assert "materialized='incremental'" in sql
    assert "incremental_strategy='merge'" in sql
    assert "unique_key=['place_id', 'issued_at', 'forecast_at', 'category']" in sql
    assert "interval '30' minute" in sql

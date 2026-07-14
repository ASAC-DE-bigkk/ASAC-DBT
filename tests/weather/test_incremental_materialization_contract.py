from pathlib import Path


WEATHER_MODELS = Path(__file__).resolve().parents[2] / "models" / "weather"


def read_model(name: str) -> str:
    matches = list(WEATHER_MODELS.rglob(f"{name}.sql"))
    assert len(matches) == 1
    return matches[0].read_text(encoding="utf-8")


def test_grid_silver_declares_incremental_merge_and_grain_key():
    sql = read_model("silver_kma_vilage_fcst")
    assert "materialized='incremental'" in sql
    assert "incremental_strategy='merge'" in sql
    assert (
        "unique_key=['place_id', 'nx', 'ny', 'issued_at', 'category', 'forecast_at']"
        in sql
    )
    # 증분 커서는 collected_at 워터마크 — dag_run_id 앙티조인 금지(DL-013 순환)
    assert "is_incremental()" in sql
    assert "max(collected_at)" in sql
    assert ">= (" in sql
    assert "weather_w1_lookback_minutes()" in sql
    assert "- interval '{{ weather_w1_lookback_minutes() }}' minute" in sql
    # R2 카탈로그 유령 뷰 409 우회(#70) + 스키마 드리프트 명시 실패(#137)
    assert "views_enabled=false" in sql
    assert "on_table_exists='drop'" in sql
    assert "on_schema_change='fail'" in sql


def test_admin_dong_silver_declares_incremental_merge_and_grain_key():
    sql = read_model("silver_weather_forecast_by_admin_dong")
    assert "materialized='incremental'" in sql
    assert "incremental_strategy='merge'" in sql
    assert "unique_key=['place_id', 'issued_at', 'forecast_at', 'category']" in sql
    assert "is_incremental()" in sql
    assert "max(collected_at)" in sql
    assert ">= (" in sql
    assert "weather_w1_lookback_minutes()" in sql
    assert "- interval '{{ weather_w1_lookback_minutes() }}' minute" in sql
    assert "views_enabled=false" in sql
    assert "on_table_exists='drop'" in sql
    assert "on_schema_change='fail'" in sql

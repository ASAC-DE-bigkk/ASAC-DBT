from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_historical_w1_models_scope_each_run_to_the_explicit_snapshot():
    silver = _source("models/weather/transform/silver/silver_kma_vilage_fcst.sql")
    place_silver = _source(
        "models/weather/transform/place_mart/silver_weather_forecast_by_admin_dong.sql"
    )
    place_gold = _source(
        "models/weather/transform/place_mart/gold_weather_forecast_by_place.sql"
    )

    assert "weather_historical_transform" in silver
    assert "is_incremental() and not historical_transform" in silver
    assert "where dag_run_id =" in place_silver
    assert "affected_grains as" in place_gold
    assert "inner join affected_grains" in place_gold


def test_historical_w2_models_require_one_prod_snapshot_and_preserve_newer_winners():
    macro = _source("macros/weather/weather_w2_contract.sql")
    observation = _source(
        "models/weather/special/silver/silver_kma_vilage_fcst_observation.sql"
    )
    grid = _source("models/weather/special/silver/silver_kma_vilage_fcst_grid.sql")
    gold = _source(
        "models/weather/special/gold/gold_weather_forecast_by_admin_dong.sql"
    )

    assert "weather_w2_historical_snapshot_context" in macro
    assert "weather_w1_prod_snapshot_bootstrap_allowed" in macro
    assert "weather_w2_assert_historical_snapshot_evidence" in observation
    assert "not historical_snapshot" in observation
    assert "weather_w2_grid_winner_is_newer('current', 'candidate')" in grid
    assert "selected_dag_run_id" in gold

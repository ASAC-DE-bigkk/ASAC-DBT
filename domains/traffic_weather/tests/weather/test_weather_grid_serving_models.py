from pathlib import Path

import yaml


MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "weather" / "transform"
GRID_MODELS = {
    "grid_mart/dim_weather_coverage_grid.sql",
    "grid_mart/silver_weather_forecast_by_coverage_grid_serving.sql",
    "grid_mart/gold_weather_forecast_by_grid_serving.sql",
}
GRID_MART_CONTRACT_TEST = (
    MODEL_DIR.parents[2]
    / "tests"
    / "weather"
    / "transform"
    / "grid_mart"
    / "assert_dim_weather_coverage_grid_canonical_80.sql"
)
SELECTORS_PATH = MODEL_DIR.parents[2] / "selectors.yml"


def _read(relative_path: str) -> str:
    return (MODEL_DIR / relative_path).read_text(encoding="utf-8")


def test_grid_serving_models_are_present_for_all_collector_grids():
    missing = [path for path in GRID_MODELS if not (MODEL_DIR / path).exists()]

    assert not missing, f"missing grid serving models: {missing}"


def test_grid_working_set_joins_coverage_dimension_before_public_gold():
    dimension_sql = _read("grid_mart/dim_weather_coverage_grid.sql")
    working_set_sql = _read(
        "grid_mart/silver_weather_forecast_by_coverage_grid_serving.sql"
    )
    serving_sql = _read("grid_mart/gold_weather_forecast_by_grid_serving.sql")

    assert "ref('weather_coverage_grid')" in dimension_sql
    assert "ref('dim_weather_coverage_grid')" in working_set_sql
    assert "unique_key=['grid_id', 'issued_at', 'forecast_at', 'category']" in working_set_sql
    assert "ref('silver_weather_forecast_by_coverage_grid_serving')" in serving_sql


def test_grid_mart_selector_runs_the_exact_80_grid_runtime_contract() -> None:
    assert GRID_MART_CONTRACT_TEST.exists()
    sql = GRID_MART_CONTRACT_TEST.read_text(encoding="utf-8")
    assert "ref('dim_weather_coverage_grid')" in sql
    assert "count(*) <> 80" in sql
    assert "count(distinct concat(cast(nx as varchar), '|', cast(ny as varchar))) <> 80" in sql

    selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))["selectors"]
    grid_mart_selector = next(
        selector
        for selector in selectors
        if selector["name"] == "ask_seoul_weather_transform_serving_grid_mart"
    )
    paths = {
        item["value"]
        for item in grid_mart_selector["definition"]["union"]
        if item["method"] == "path"
    }
    assert (
        "tests/weather/transform/grid_mart/"
        "assert_dim_weather_coverage_grid_canonical_80.sql"
    ) in paths

from pathlib import Path

import yaml


SELECTORS_PATH = Path(__file__).resolve().parents[2] / "selectors.yml"

CANONICAL_MODEL_PATHS = {
    "models/weather/special/silver/silver_kma_vilage_fcst_observation.sql",
    "models/weather/special/silver/silver_kma_vilage_fcst_grid.sql",
    "models/weather/special/gold/gold_weather_forecast_by_admin_dong.sql",
}

CANONICAL_CONTRACT_PATHS = {
    "tests/weather/special/assert_gold_weather_forecast_by_admin_dong_admin_join_reconciles.sql",
    "tests/weather/special/assert_gold_weather_forecast_by_admin_dong_admin_revision_exact.sql",
    "tests/weather/special/assert_gold_weather_forecast_by_admin_dong_admin_stamp_exact.sql",
    "tests/weather/special/assert_gold_weather_forecast_by_admin_dong_bridge_exclusions_reconcile.sql",
    "tests/weather/special/assert_gold_weather_forecast_by_admin_dong_canonical_source_contract.sql",
    "tests/weather/special/assert_gold_weather_forecast_by_admin_dong_grain_unique.sql",
    "tests/weather/special/assert_gold_weather_forecast_by_admin_dong_latest_grid_record.sql",
    "tests/weather/special/assert_gold_weather_forecast_by_admin_dong_product_row_id_reproducible.sql",
    "tests/weather/special/recovery/winner/assert_gold_weather_forecast_by_admin_dong_repair_no_downgrade.sql",
    "tests/weather/special/recovery/reconciliation/assert_gold_weather_forecast_by_admin_dong_repair_reconciles.sql",
}


def _selectors_by_name():
    document = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))
    return {selector["name"]: selector for selector in document["selectors"]}


def _path_criteria(selector):
    criteria = selector["definition"]["union"]
    assert all(criterion["method"] == "path" for criterion in criteria)
    assert all(criterion["indirect_selection"] == "empty" for criterion in criteria)
    return {criterion["value"] for criterion in criteria}


def test_canonical_w2_model_selector_has_only_owned_models():
    selector = _selectors_by_name()["ask_seoul_weather_w2_canonical_models"]

    assert _path_criteria(selector) == CANONICAL_MODEL_PATHS


def test_canonical_w2_contract_selector_has_only_required_contracts():
    selector = _selectors_by_name()["ask_seoul_weather_w2_canonical_contracts"]

    actual_paths = _path_criteria(selector)
    assert actual_paths == CANONICAL_CONTRACT_PATHS
    assert all("weather_admin_dong_grid_bridge_history" not in path for path in actual_paths)
    assert all("bridge_weather_admin_dong_grid" not in path for path in actual_paths)

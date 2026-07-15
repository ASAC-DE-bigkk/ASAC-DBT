from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
RECOVERY_SELECTORS = {
    "ask_seoul_weather_w2_recovery_window_models",
    "ask_seoul_weather_w2_recovery_window_contracts",
    "ask_seoul_weather_w2_recovery_lineage_contract",
    "ask_seoul_weather_w2_recovery_final_contract",
}


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def model_contract(path: str, model_name: str) -> dict:
    document = load_yaml(REPO_ROOT / path)
    return next(model for model in document["models"] if model["name"] == model_name)


def test_weather_recovery_models_own_one_direct_phase_tag_each() -> None:
    expected = {
        (
            "models/weather/special/silver/_special_silver.yml",
            "silver_kma_vilage_fcst_observation",
        ): "ask_seoul_weather_w2_recovery_window_models",
        (
            "models/weather/special/silver/_special_silver.yml",
            "silver_kma_vilage_fcst_grid",
        ): "ask_seoul_weather_w2_recovery_window_models",
        (
            "models/weather/special/gold/gold_weather_forecast_by_admin_dong.yml",
            "gold_weather_forecast_by_admin_dong",
        ): "ask_seoul_weather_w2_recovery_window_models",
        (
            "models/weather/special/recovery/_recovery.yml",
            "weather_w2_observation_recovery_lineage_workset",
        ): "ask_seoul_weather_w2_recovery_window_models",
    }

    for (properties_path, model_name), phase_tag in expected.items():
        model = model_contract(properties_path, model_name)
        assert model["config"]["tags"] == [phase_tag]


def test_weather_recovery_singular_tests_live_in_phase_owned_folders() -> None:
    project = load_yaml(REPO_ROOT / "dbt_project.yml")
    recovery = project["data_tests"]["asac_seoul"]["weather"]["special"]["recovery"]
    assert recovery == {
        "reconciliation": {"+tags": ["ask_seoul_weather_w2_recovery_window_contracts"]},
        "lineage": {"+tags": ["ask_seoul_weather_w2_recovery_lineage_contract"]},
        "final": {"+tags": ["ask_seoul_weather_w2_recovery_final_contract"]},
    }

    expected_paths = (
        "tests/weather/special/recovery/reconciliation/"
        "assert_gold_weather_forecast_by_admin_dong_repair_reconciles.sql",
        "tests/weather/special/recovery/reconciliation/"
        "assert_gold_weather_forecast_by_admin_dong_repair_window_no_extra_rows.sql",
        "tests/weather/special/recovery/lineage/"
        "assert_gold_weather_forecast_by_admin_dong_repair_window_lineage.sql",
        "tests/weather/special/recovery/final/"
        "assert_weather_observation_publishable_and_counts_reconcile.sql",
    )
    assert all((REPO_ROOT / path).is_file() for path in expected_paths)


def test_weather_recovery_named_selectors_match_their_direct_tags() -> None:
    selectors = load_yaml(REPO_ROOT / "selectors.yml")["selectors"]
    by_name = {selector["name"]: selector for selector in selectors}

    assert RECOVERY_SELECTORS <= set(by_name)
    for selector_name in RECOVERY_SELECTORS:
        assert by_name[selector_name]["description"].strip()
        assert by_name[selector_name]["definition"] == {
            "method": "tag",
            "value": selector_name,
            "indirect_selection": "cautious",
        }

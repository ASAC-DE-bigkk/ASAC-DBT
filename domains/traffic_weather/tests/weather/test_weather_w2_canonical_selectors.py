from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SELECTORS_PATH = PROJECT_ROOT / "selectors.yml"

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
LATEST_GRID_FAST_PATH = (
    "tests/weather/special/"
    "assert_gold_weather_forecast_by_admin_dong_latest_grid_record.sql"
)
LATEST_GRID_FULL_PATH = (
    "tests/weather/special/"
    "assert_gold_weather_forecast_by_admin_dong_latest_grid_record_full.sql"
)
LATEST_GRID_FULL_SQL = PROJECT_ROOT / LATEST_GRID_FULL_PATH
FULL_CANONICAL_CONTRACT_PATHS = (
    CANONICAL_CONTRACT_PATHS - {LATEST_GRID_FAST_PATH}
) | {LATEST_GRID_FULL_PATH}
CANONICAL_BRIDGE_RECONCILE_PATH = (
    "tests/weather/special/"
    "assert_gold_weather_forecast_by_admin_dong_bridge_exclusions_reconcile.sql"
)

STAGE_WINDOW_CONTRACT_PATH = (
    "tests/weather/special/recovery/stage/"
    "assert_weather_w2_recovery_stage_window.sql"
)
STAGE_MODEL_SELECTOR = "ask_seoul_weather_w2_recovery_stage_model"
STAGE_MODEL_NAME = "weather_w2_observation_recovery_stage"
STAGE_FINAL_CONTRACT_PATH = (
    "tests/weather/special/recovery/stage/"
    "assert_weather_w2_recovery_stage_final_reconciles.sql"
)
STAGE_WINNER_CONTRACT_PATH = (
    "tests/weather/special/recovery/stage/"
    "assert_weather_w2_recovery_stage_no_downgrade.sql"
)
STAGE_LINEAGE_CONTRACT_PATH = (
    "tests/weather/special/recovery/stage/"
    "assert_weather_w2_recovery_stage_lineage.sql"
)


def _selectors_by_name():
    document = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))
    return {selector["name"]: selector for selector in document["selectors"]}


def _path_criteria(selector):
    criteria = selector["definition"]["union"]
    assert all(criterion["method"] == "path" for criterion in criteria)
    assert all(criterion["indirect_selection"] == "empty" for criterion in criteria)
    return {criterion["value"] for criterion in criteria}


def _model_names_with_tag(tag):
    names = set()
    for properties_path in (PROJECT_ROOT / "models").rglob("*.yml"):
        document = yaml.safe_load(properties_path.read_text(encoding="utf-8")) or {}
        for model in document.get("models", []) or []:
            tags = model.get("config", {}).get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            if tag in tags:
                names.add(model["name"])
    return names


def test_canonical_w2_model_selector_has_only_owned_models():
    selector = _selectors_by_name()["ask_seoul_weather_w2_canonical_models"]

    assert _path_criteria(selector) == CANONICAL_MODEL_PATHS


def test_canonical_w2_contract_selector_has_only_required_contracts():
    selector = _selectors_by_name()["ask_seoul_weather_w2_canonical_contracts"]

    actual_paths = _path_criteria(selector)
    assert actual_paths == CANONICAL_CONTRACT_PATHS
    assert all("weather_admin_dong_grid_bridge_history" not in path for path in actual_paths)
    assert all("bridge_weather_admin_dong_grid" not in path for path in actual_paths)


def test_canonical_full_contract_selector_replaces_fast_latest_record():
    selectors = _selectors_by_name()
    routine = _path_criteria(selectors["ask_seoul_weather_w2_canonical_contracts"])
    full = _path_criteria(selectors["ask_seoul_weather_w2_canonical_full_contracts"])

    assert routine == CANONICAL_CONTRACT_PATHS
    assert full == FULL_CANONICAL_CONTRACT_PATHS
    assert LATEST_GRID_FAST_PATH in routine
    assert LATEST_GRID_FULL_PATH not in routine
    assert LATEST_GRID_FAST_PATH not in full
    assert LATEST_GRID_FULL_PATH in full
    assert len(routine) == len(full) == 10


def test_canonical_full_latest_record_preserves_no_downgrade_winners():
    sql = LATEST_GRID_FULL_SQL.read_text(encoding="utf-8")
    normal_mode = sql.rsplit("{% else %}", maxsplit=1)[1]

    assert (
        "not {{ weather_w2_gold_winner_is_not_older('actual', 'expected') }}"
        in normal_mode
    )
    assert (
        "{{ weather_w2_gold_winner_is_not_older('expected', 'actual') }}"
        in normal_mode
    )


def test_recovery_stage_window_selector_owns_one_lightweight_contract():
    selector = _selectors_by_name()[
        "ask_seoul_weather_w2_recovery_stage_window_contract"
    ]

    assert _path_criteria(selector) == {STAGE_WINDOW_CONTRACT_PATH}


def test_recovery_stage_model_selector_owns_only_internal_stage():
    selector = _selectors_by_name()[STAGE_MODEL_SELECTOR]

    assert selector["definition"] == {
        "method": "tag",
        "value": STAGE_MODEL_SELECTOR,
        "indirect_selection": "cautious",
    }
    assert _model_names_with_tag(STAGE_MODEL_SELECTOR) == {STAGE_MODEL_NAME}


def test_recovery_post_publish_selector_owns_full_bridge_reconcile_only():
    selector = _selectors_by_name()[
        "ask_seoul_weather_w2_recovery_post_publish_bridge_contract"
    ]

    assert _path_criteria(selector) == {CANONICAL_BRIDGE_RECONCILE_PATH}


def test_recovery_stage_final_selectors_each_own_one_bounded_contract():
    selectors = _selectors_by_name()

    assert _path_criteria(
        selectors["ask_seoul_weather_w2_recovery_stage_final"]
    ) == {STAGE_FINAL_CONTRACT_PATH}
    assert _path_criteria(
        selectors["ask_seoul_weather_w2_recovery_stage_winner"]
    ) == {STAGE_WINNER_CONTRACT_PATH}
    assert _path_criteria(
        selectors["ask_seoul_weather_w2_recovery_stage_lineage"]
    ) == {STAGE_LINEAGE_CONTRACT_PATH}

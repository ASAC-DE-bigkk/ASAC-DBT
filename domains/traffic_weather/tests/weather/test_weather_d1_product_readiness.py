from __future__ import annotations

from pathlib import Path

import yaml


PROJECT_DIR = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_DIR / "models" / "weather" / "transform" / "gold"
GOLD_TEST_DIR = PROJECT_DIR / "tests" / "weather" / "transform" / "gold"
SELECTORS_PATH = PROJECT_DIR / "selectors.yml"
DBT_PROJECT_PATH = PROJECT_DIR / "dbt_project.yml"

CURRENT_MODEL = GOLD_DIR / "gold_weather_place_current_outlook.yml"
CURRENT_SQL = GOLD_DIR / "gold_weather_place_current_outlook.sql"
PRECIP_MODEL = GOLD_DIR / "gold_weather_place_precipitation_window.yml"
FORECAST_CHANGE_MODEL = GOLD_DIR / "gold_weather_place_forecast_change_daily.yml"

CURRENT_READINESS_TEST = GOLD_TEST_DIR / "assert_gold_weather_place_current_outlook_readiness.sql"
PRECIP_VALID_EMPTY_TEST = GOLD_TEST_DIR / "assert_gold_weather_place_precipitation_window_valid_empty.sql"
PRECIP_NON_OVERLAPPING_TEST = GOLD_TEST_DIR / "assert_gold_weather_place_precipitation_window_non_overlapping.sql"
FORECAST_CHANGE_CONSISTENCY_TEST = (
    GOLD_TEST_DIR / "assert_gold_weather_place_forecast_change_daily_consistent.sql"
)

CURRENT_PUBLIC_PROJECTION = [
    "product_row_id", "place_id", "place_name", "alias_names", "admin_dong_code", "admin_dong",
    "gu_code", "gu", "latitude", "longitude", "forecast_at", "forecast_category_count",
    "forecast_issued_at_min", "forecast_issued_at_max", "forecast_collected_at_max", "temp_c",
    "humidity_pct", "wind_ms", "wind_dir_deg", "precip_prob_pct", "sky_code", "sky_label",
    "pty_code", "pty_label", "is_precipitating", "pcp_raw", "pcp_mm", "sno_raw", "sno_cm",
    "forecast_lead_hours",
]
PRECIP_PUBLIC_PROJECTION = ["product_row_id", "place_id", "window_start_at", "window_end_at"]
FORECAST_CHANGE_V1_PUBLIC_PROJECTION = [
    "product_row_id", "place_id", "forecast_date", "latest_issued_at", "change_state",
]
FORECAST_CHANGE_PUBLIC_PROJECTION = [
    "product_row_id", "place_id", "forecast_date", "latest_issued_at", "change_state",
    "place_name", "admin_dong_code", "admin_dong", "gu_code", "gu", "previous_issued_at", "issue_gap_hours",
    "latest_category_count", "previous_category_count", "latest_forecast_hour_count",
    "previous_forecast_hour_count", "latest_min_temp_c", "previous_min_temp_c",
    "min_temp_change_c", "latest_max_temp_c", "previous_max_temp_c", "max_temp_change_c",
    "latest_max_precip_prob_pct", "previous_max_precip_prob_pct", "max_precip_prob_change_pct",
    "latest_first_precipitation_at", "previous_first_precipitation_at", "latest_collected_at_max",
    "previous_collected_at_max",
]


def _model(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload["models"][0]


def _columns(model: dict) -> dict[str, dict]:
    return {column["name"]: column for column in model["columns"]}


def _test_names(column: dict) -> set[str]:
    names: set[str] = set()
    for test in column.get("tests", []):
        if isinstance(test, str):
            names.add(test)
        elif isinstance(test, dict):
            names.update(test)
    return names


def test_weather_wave_a_serving_contracts_keep_truth_labels() -> None:
    current = _model(CURRENT_MODEL)
    precipitation = _model(PRECIP_MODEL)

    current_serving = current["config"]["meta"]["serving"]
    precip_serving = precipitation["config"]["meta"]["serving"]

    assert current_serving["zero_policy"] == "fail"
    assert precip_serving["zero_policy"] == "allow"
    assert current_serving["public_projection"]["columns"] == CURRENT_PUBLIC_PROJECTION
    assert precip_serving["public_projection"]["columns"] == PRECIP_PUBLIC_PROJECTION
    assert "snapshot_as_of_hour" not in current_serving["public_projection"]["columns"]

    assert "예보" in current["description"]
    assert "실측" in current["config"]["meta"]["public_gold"]["semantic_caveats"]
    assert "예보" in precipitation["description"]
    assert "관측" in precipitation["description"]
    assert "보장" in precipitation["description"]


def test_current_outlook_declares_internal_snapshot_anchor_without_public_projection() -> None:
    model = _model(CURRENT_MODEL)
    columns = _columns(model)
    public_gold = model["config"]["meta"]["public_gold"]
    public_projection = model["config"]["meta"]["serving"]["public_projection"]["columns"]

    assert "snapshot_as_of_hour" in columns
    assert list(columns) == public_gold["column_order"]
    assert "snapshot_as_of_hour" not in public_projection
    anchor = columns["snapshot_as_of_hour"]
    meta = anchor["config"]["meta"]

    assert anchor["data_type"] == "timestamp(6)"
    assert "not_null" in _test_names(anchor)
    assert meta["semantic_role"] == "internal_build_anchor"
    assert meta["visibility"] == "internal"
    assert meta["nullable"] is False
    assert meta["unit"] == "not_applicable"

    sql = CURRENT_SQL.read_text(encoding="utf-8")
    assert "snapshot_as_of_hour" in sql
    assert "current_hour_at as snapshot_as_of_hour" in sql


def test_forecast_change_declares_public_gold_semantic_contract() -> None:
    model = _model(FORECAST_CHANGE_MODEL)
    config = model["config"]
    serving = config["meta"]["serving"]
    public_gold = config["meta"]["public_gold"]
    columns = _columns(model)

    assert config["contract"] == {"enforced": True}
    assert public_gold["contract_version"] == "1.0"
    assert public_gold["product_question"] == serving["product_question"]
    assert public_gold["grain"] == serving["grain"]
    assert public_gold["primary_key"] == serving["primary_key"]
    assert public_gold["column_order"] == serving["public_projection"]["columns"]
    assert public_gold["time"]["canonical_timezone"] == "Asia/Seoul"

    expected_time_columns = {
        "latest_issued_at",
        "previous_issued_at",
        "latest_first_precipitation_at",
        "previous_first_precipitation_at",
        "latest_collected_at_max",
        "previous_collected_at_max",
    }
    assert set(public_gold["time"]["roles"]) == expected_time_columns
    for column_name in expected_time_columns:
        role = public_gold["time"]["roles"][column_name]
        column_meta = columns[column_name]["config"]["meta"]
        assert role["time_role"] == column_meta["time_role"]
        assert role["timezone"] == column_meta["timezone"]

    change_state = public_gold["quality"]["state_fields"]["change_state"]
    assert change_state["allowed_values"] == [
        "no_previous_issue",
        "partial_comparison",
        "changed",
        "unchanged",
    ]
    assert set(change_state["state_explanations"]) == set(
        change_state["allowed_values"]
    )
    assert all(change_state["state_explanations"].values())

    assert public_gold["lineage"]["source_relations"] == [
        "model.asac_seoul.silver_weather_forecast_by_admin_dong"
    ]
    assert "실측" in public_gold["do_not_use_for"]


def test_forecast_change_projection_exposes_the_comparison_evidence() -> None:
    model = _model(FORECAST_CHANGE_MODEL)
    serving = model["config"]["meta"]["serving"]

    assert serving["public_projection"] == {
        "schema_version": "1.1.0",
        "columns": FORECAST_CHANGE_PUBLIC_PROJECTION,
    }
    assert serving["public_projection"]["columns"][:5] == FORECAST_CHANGE_V1_PUBLIC_PROJECTION
    assert "직전" in serving["product_question"]
    assert {
        "previous_issued_at",
        "min_temp_change_c",
        "max_temp_change_c",
        "max_precip_prob_change_pct",
        "latest_first_precipitation_at",
        "previous_first_precipitation_at",
    } <= set(serving["public_projection"]["columns"])


def test_forecast_change_normalizes_utc_collection_time_to_contract_timezone() -> None:
    sql = (
        GOLD_DIR / "gold_weather_place_forecast_change_daily.sql"
    ).read_text(encoding="utf-8")

    assert "asac_axes.utc_to_kst('forecast.collected_at')" in sql
    assert "as collected_at_max" in sql


def test_weather_wave_a_readiness_singular_tests_are_wired_to_gold_selector() -> None:
    selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))["selectors"]
    selector_names = {selector["name"] for selector in selectors}
    dbt_project = yaml.safe_load(DBT_PROJECT_PATH.read_text(encoding="utf-8"))

    assert "ask_seoul_weather_transform_gold" in selector_names
    assert dbt_project["data_tests"]["asac_seoul"]["weather"]["transform"]["gold"]["+tags"] == [
        "ask_seoul_weather_transform_gold"
    ]

    expected = {
        CURRENT_READINESS_TEST: [
            "ref('gold_weather_place_current_outlook')",
            "ref('gold_weather_place_hourly_outlook')",
            "snapshot_as_of_hour",
        ],
        PRECIP_VALID_EMPTY_TEST: [
            "ref('gold_weather_place_precipitation_window')",
            "ref('gold_weather_place_hourly_outlook')",
            "precipitation_hour_count",
            "pty_code is null",
        ],
        PRECIP_NON_OVERLAPPING_TEST: [
            "ref('gold_weather_place_precipitation_window')",
            "precipitation_hour_count",
            "date_diff('hour', window_start_at, window_end_at) + 1",
        ],
        FORECAST_CHANGE_CONSISTENCY_TEST: [
            "ref('gold_weather_place_forecast_change_daily')",
            "previous_issued_at is null",
            "min_temp_change_c is distinct from",
            "max_temp_change_c is distinct from",
            "max_precip_prob_change_pct is distinct from",
            "expected_change_state is distinct from change_state",
        ],
    }
    for path, required_fragments in expected.items():
        assert path.exists(), f"missing readiness singular test: {path.name}"
        sql = path.read_text(encoding="utf-8")
        for fragment in required_fragments:
            assert fragment in sql, f"{path.name} missing {fragment}"

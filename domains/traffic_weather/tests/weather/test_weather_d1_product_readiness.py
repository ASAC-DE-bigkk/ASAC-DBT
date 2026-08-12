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
RISK_WINDOW_MODEL = GOLD_DIR / "gold_weather_place_risk_window.yml"
HOURLY_MODEL = GOLD_DIR / "_serving_gold.yml"
HOURLY_SQL = GOLD_DIR / "gold_weather_place_hourly_outlook.sql"
QUERY_AVAILABILITY_MODEL = GOLD_DIR / "gold_weather_place_risk_query_availability.yml"
QUERY_AVAILABILITY_SQL = GOLD_DIR / "gold_weather_place_risk_query_availability.sql"

CURRENT_READINESS_TEST = GOLD_TEST_DIR / "assert_gold_weather_place_current_outlook_readiness.sql"
PRECIP_VALID_EMPTY_TEST = GOLD_TEST_DIR / "assert_gold_weather_place_precipitation_window_valid_empty.sql"
PRECIP_NON_OVERLAPPING_TEST = GOLD_TEST_DIR / "assert_gold_weather_place_precipitation_window_non_overlapping.sql"
FORECAST_CHANGE_CONSISTENCY_TEST = (
    GOLD_TEST_DIR / "assert_gold_weather_place_forecast_change_daily_consistent.sql"
)
RISK_FUTURE_ONLY_TEST = GOLD_TEST_DIR / "assert_gold_weather_place_risk_window_future_only.sql"
QUERY_AVAILABILITY_GRAIN_TEST = (
    GOLD_TEST_DIR / "assert_gold_weather_place_risk_query_availability_grain_unique.sql"
)
QUERY_AVAILABILITY_POPULATION_TEST = (
    GOLD_TEST_DIR / "assert_gold_weather_place_risk_query_availability_population_reconciles.sql"
)
QUERY_AVAILABILITY_RECONCILES_TEST = (
    GOLD_TEST_DIR / "assert_gold_weather_place_risk_query_availability_reconciles.sql"
)
QUERY_AVAILABILITY_UNIT_TEST_SELECTOR = (
    "ask_seoul_weather_risk_query_availability_unit_tests"
)
QUERY_AVAILABILITY_UNIT_TEST_NAMES = {
    "risk_query_availability_complete_prefix",
    "risk_query_availability_first_slot_missing",
    "risk_query_availability_middle_gap_truncates_prefix",
    "risk_query_availability_required_evidence_missing",
    "risk_query_availability_raw_no_precip_numeric_null_complete",
}
GRID_PRECIP_VALID_EMPTY_TEST = (
    GOLD_TEST_DIR / "assert_gold_weather_grid_precipitation_window_valid_empty.sql"
)
SERVING_AS_OF_HOUR_MACRO = (
    PROJECT_DIR / "macros" / "weather" / "weather_serving_as_of_hour.sql"
)
SERVING_TIME_BOUNDARY_SQL = (
    CURRENT_SQL,
    GOLD_DIR / "gold_weather_place_precipitation_window.sql",
    GOLD_DIR / "gold_weather_place_risk_window.sql",
    GOLD_DIR / "gold_weather_place_forecast_change_daily.sql",
    GOLD_DIR / "gold_weather_grid_current_outlook.sql",
    GOLD_DIR / "gold_weather_grid_precipitation_window.sql",
    PRECIP_VALID_EMPTY_TEST,
    RISK_FUTURE_ONLY_TEST,
    GRID_PRECIP_VALID_EMPTY_TEST,
    QUERY_AVAILABILITY_SQL,
    QUERY_AVAILABILITY_RECONCILES_TEST,
)
QUERY_AVAILABILITY_NO_DIRECT_CURRENT_TIME_SQL = (
    QUERY_AVAILABILITY_GRAIN_TEST,
    QUERY_AVAILABILITY_POPULATION_TEST,
)

PUBLIC_WEATHER_MODEL_PATHS = (
    CURRENT_MODEL,
    PRECIP_MODEL,
    RISK_WINDOW_MODEL,
    FORECAST_CHANGE_MODEL,
    GOLD_DIR / "gold_weather_grid_current_outlook.yml",
    GOLD_DIR / "gold_weather_grid_precipitation_window.yml",
)
PUBLIC_WEATHER_PRODUCT_IDS = {
    "weather_place_current_outlook",
    "weather_place_precipitation_window",
    "weather_place_risk_window",
    "weather_place_forecast_change_daily",
}

CURRENT_PUBLIC_PROJECTION = [
    "product_row_id", "place_id", "place_name", "alias_names", "admin_dong_code", "admin_dong",
    "gu_code", "gu", "latitude", "longitude", "forecast_at", "forecast_category_count",
    "forecast_issued_at_min", "forecast_issued_at_max", "forecast_collected_at_max", "snapshot_as_of_hour", "temp_c",
    "humidity_pct", "wind_ms", "wind_dir_deg", "precip_prob_pct", "sky_code", "sky_label",
    "pty_code", "pty_label", "is_precipitating", "pcp_raw", "pcp_mm", "sno_raw", "sno_cm",
    "forecast_lead_hours",
]
PRECIP_PUBLIC_PROJECTION = [
    "product_row_id", "place_id", "place_name", "admin_dong_code", "admin_dong", "gu_code", "gu",
    "window_start_at", "window_end_at", "precipitation_hour_count", "precip_prob_max_pct", "pcp_max_mm",
    "sno_max_cm", "forecast_issued_at_min", "forecast_issued_at_max", "forecast_collected_at_max",
]
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


def _named_model(path: Path, name: str) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return next(model for model in payload["models"] if model["name"] == name)


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
    assert current_serving["freshness_field"] == "forecast_collected_at_max"
    assert current_serving["publication_trigger"] == {"schedule_cron": "0 * * * *"}
    assert current_serving["mcp_projection"]["currentness"] == {
        "field": "forecast_at",
        "minimum": "current_kst_hour",
    }
    assert precip_serving["zero_policy"] == "allow"
    assert precip_serving["freshness_field"] == "forecast_collected_at_max"
    assert precip_serving["publication_trigger"] == {"schedule_cron": "0 * * * *"}
    assert precip_serving["empty_result_freshness"] == {
        "relation": "gold_weather_place_hourly_outlook",
        "field": "forecast_collected_at_max",
    }
    assert precip_serving["mcp_projection"]["empty_result"] == {
        "state": "valid_empty",
        "code": "no_upcoming_precipitation_forecast",
        "message_ko": "현재 수집된 유효 단기예보에는 향후 강수(비·눈) 구간이 없습니다.",
    }
    risk_serving = _model(RISK_WINDOW_MODEL)["config"]["meta"]["serving"]
    assert risk_serving["zero_policy"] == "allow"
    assert risk_serving["publication_trigger"] == {"schedule_cron": "0 * * * *"}
    assert risk_serving["empty_result_freshness"] == {
        "relation": "gold_weather_place_hourly_outlook",
        "field": "forecast_collected_at_max",
    }
    assert risk_serving["mcp_projection"]["empty_result"] == {
        "state": "valid_empty",
        "code": "no_upcoming_weather_risk_candidate",
        "message_ko": "현재 수집된 유효 단기예보에는 설정된 기준을 충족한 향후 기상 위험 후보 구간이 없습니다.",
    }
    assert current_serving["public_projection"]["columns"] == CURRENT_PUBLIC_PROJECTION
    assert precip_serving["public_projection"]["columns"] == PRECIP_PUBLIC_PROJECTION
    assert set(precip_serving["public_projection"]["columns"]) <= set(_columns(precipitation))
    assert current_serving["public_projection"]["schema_version"] == "1.1.0"
    assert precip_serving["public_projection"]["schema_version"] == "1.2.0"
    assert "snapshot_as_of_hour" in current_serving["public_projection"]["columns"]

    assert "예보" in current["description"]
    assert "실측" in current["config"]["meta"]["public_gold"]["semantic_caveats"]
    assert "예보" in precipitation["description"]
    assert "관측" in precipitation["description"]
    assert "보장" in precipitation["description"]


def test_current_outlook_exposes_snapshot_anchor_with_collection_freshness() -> None:
    model = _model(CURRENT_MODEL)
    columns = _columns(model)
    public_gold = model["config"]["meta"]["public_gold"]
    public_projection = model["config"]["meta"]["serving"]["public_projection"]["columns"]

    assert "snapshot_as_of_hour" in columns
    assert list(columns) == public_gold["column_order"]
    assert "snapshot_as_of_hour" in public_projection
    anchor = columns["snapshot_as_of_hour"]
    meta = anchor["config"]["meta"]

    assert anchor["data_type"] == "timestamp(6)"
    assert "not_null" in _test_names(anchor)
    assert meta["semantic_role"] == "snapshot_time"
    assert meta["visibility"] == "public"
    assert meta["nullable"] is False
    assert meta["unit"] == "not_applicable"

    sql = CURRENT_SQL.read_text(encoding="utf-8")
    assert "snapshot_as_of_hour" in sql
    assert "current_hour_at as snapshot_as_of_hour" in sql


def test_weather_serving_models_and_singular_tests_share_one_frozen_kst_hour() -> None:
    macro = SERVING_AS_OF_HOUR_MACRO.read_text(encoding="utf-8")

    assert "weather_serving_as_of_hour" in macro
    assert "modules.re.fullmatch" in macro
    assert "current_timestamp at time zone 'Asia/Seoul'" in macro
    for path in SERVING_TIME_BOUNDARY_SQL:
        sql = path.read_text(encoding="utf-8")
        assert "{{ weather_serving_as_of_hour() }}" in sql, path.name
        assert "current_timestamp at time zone 'Asia/Seoul'" not in sql, path.name


def test_query_availability_non_anchor_assertions_do_not_read_wall_clock() -> None:
    for path in QUERY_AVAILABILITY_NO_DIRECT_CURRENT_TIME_SQL:
        sql = path.read_text(encoding="utf-8")
        assert "current_timestamp at time zone 'Asia/Seoul'" not in sql, path.name
        assert "{{ weather_serving_as_of_hour() }}" not in sql, path.name


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
        "model.asac_seoul.silver_weather_forecast_by_admin_dong_serving"
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


def test_risk_window_declares_coverage_not_applicable_for_sparse_events() -> None:
    model = _model(RISK_WINDOW_MODEL)
    serving = model["config"]["meta"]["serving"]

    assert serving["quality_coverage"] == {
        "not_applicable_reason": (
            "위험 조건을 충족한 장소·예보시각만 게시하는 희소 이벤트 제품이므로, "
            "게시 행의 place_id 수는 전체 장소 모집단의 커버리지를 뜻하지 않습니다."
        ),
    }


def test_risk_query_availability_companion_is_private_and_declares_place_horizon_contract() -> None:
    model = _model(QUERY_AVAILABILITY_MODEL)
    columns = _columns(model)

    assert model["access"] == "private"
    assert model["config"]["materialized"] == "table"
    assert list(columns) == [
        "place_id", "snapshot_as_of_hour", "available_from_at", "available_to_at",
        "forecast_collected_at_min", "forecast_collected_at_max",
        "expected_forecast_hour_count", "observed_forecast_hour_count",
        "availability_status", "source_population_revision",
    ]
    assert "427" in model["description"]
    assert "dim_weather_place" in model["description"]
    assert _test_names(columns["place_id"]) == {"not_null", "unique"}
    assert _test_names(columns["availability_status"]) == {"not_null", "accepted_values"}
    assert columns["available_from_at"]["config"]["meta"]["nullable"] is True
    assert columns["available_to_at"]["config"]["meta"]["nullable"] is True
    assert columns["forecast_collected_at_min"]["config"]["meta"]["nullable"] is True
    assert columns["forecast_collected_at_max"]["config"]["meta"]["nullable"] is True


def test_risk_window_declares_private_query_availability_companion() -> None:
    risk_serving = _model(RISK_WINDOW_MODEL)["config"]["meta"]["serving"]
    assert risk_serving["query_availability"] == {
        "relation": "gold_weather_place_risk_query_availability",
    }


def test_hourly_outlook_exposes_required_risk_category_freshness_bounds() -> None:
    hourly = _named_model(HOURLY_MODEL, "gold_weather_place_hourly_outlook")
    columns = _columns(hourly)
    sql = HOURLY_SQL.read_text(encoding="utf-8")

    assert "risk_evidence_collected_at_min" in columns
    assert "risk_evidence_collected_at_max" in columns
    assert "risk_evidence_collected_category_count" in columns
    assert columns["risk_evidence_collected_at_min"]["data_type"] == "timestamp(6)"
    assert columns["risk_evidence_collected_at_max"]["data_type"] == "timestamp(6)"
    assert columns["risk_evidence_collected_category_count"]["data_type"] == "bigint"
    assert "count(distinct case" in sql
    assert "collected_at is not null" in sql
    assert "category in ('TMP', 'WSD') and fcst_value_num is not null" in sql
    assert "category in ('PTY', 'PCP', 'SNO')" in sql
    assert "risk_evidence_collected_at_min" in sql
    assert "risk_evidence_collected_at_max" in sql

    companion_sql = QUERY_AVAILABILITY_SQL.read_text(encoding="utf-8")
    assert "risk_evidence_collected_category_count = 5" in companion_sql


def test_risk_query_availability_dbt_unit_fixtures_are_model_bound_and_selected() -> None:
    document = yaml.safe_load(QUERY_AVAILABILITY_MODEL.read_text(encoding="utf-8"))
    unit_tests = document["unit_tests"]
    by_name = {unit_test["name"]: unit_test for unit_test in unit_tests}

    assert set(by_name) == QUERY_AVAILABILITY_UNIT_TEST_NAMES
    literal_expected_outcomes = {
        "risk_query_availability_complete_prefix": (
            "2026-08-12 00:00:00",
            "2026-08-12 02:00:00",
            3,
            3,
            "complete",
        ),
        "risk_query_availability_first_slot_missing": (
            None,
            None,
            3,
            2,
            "incomplete",
        ),
        "risk_query_availability_middle_gap_truncates_prefix": (
            "2026-08-12 00:00:00",
            "2026-08-12 00:00:00",
            3,
            2,
            "incomplete",
        ),
        "risk_query_availability_required_evidence_missing": (
            None,
            None,
            1,
            0,
            "incomplete",
        ),
        "risk_query_availability_raw_no_precip_numeric_null_complete": (
            "2026-08-12 00:00:00",
            "2026-08-12 00:00:00",
            1,
            1,
            "complete",
        ),
    }
    for unit_test in by_name.values():
        assert unit_test["model"] == "gold_weather_place_risk_query_availability"
        assert unit_test["config"]["tags"] == [
            "ask_seoul_weather_risk_query_availability_unit"
        ]
        assert unit_test["overrides"]["vars"]["weather_serving_as_of_hour"] == (
            "2026-08-12 00:00:00"
        )
        assert {given["input"] for given in unit_test["given"]} == {
            "ref('dim_weather_place')",
            "ref('gold_weather_place_hourly_outlook')",
        }
        assert unit_test["expect"]["rows"]
        assert set(unit_test["expect"]["rows"][0]) == {
            "place_id",
            "snapshot_as_of_hour",
            "available_from_at",
            "available_to_at",
            "forecast_collected_at_min",
            "forecast_collected_at_max",
            "expected_forecast_hour_count",
            "observed_forecast_hour_count",
            "availability_status",
            "source_population_revision",
        }
        expected_row = unit_test["expect"]["rows"][0]
        assert (
            expected_row["available_from_at"],
            expected_row["available_to_at"],
            expected_row["expected_forecast_hour_count"],
            expected_row["observed_forecast_hour_count"],
            expected_row["availability_status"],
        ) == literal_expected_outcomes[unit_test["name"]]
        assert expected_row["source_population_revision"] == (
            "kma_admin_dong_grid_20260325:"
            "638f0e8260b47eeb0335126a87a8a38e7b456da872bf0ea7e28eecf427610e32"
        )

    selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))["selectors"]
    by_selector = {selector["name"]: selector["definition"] for selector in selectors}
    assert by_selector[QUERY_AVAILABILITY_UNIT_TEST_SELECTOR] == {
        "intersection": [
            {
                "method": "tag",
                "value": "ask_seoul_weather_risk_query_availability_unit",
                "indirect_selection": "empty",
            },
            {"method": "test_type", "value": "unit"},
        ]
    }
    for serving_selector in (
        "ask_seoul_weather_serving_snapshot_refresh",
        "ask_seoul_weather_transform_serving_gold",
    ):
        assert {
            "method": "selector",
            "value": QUERY_AVAILABILITY_UNIT_TEST_SELECTOR,
            "indirect_selection": "empty",
        } in by_selector[serving_selector]["union"]


def test_exactly_four_place_weather_products_are_public_and_external() -> None:
    public_products = {
        _model(path)["config"]["meta"]["serving"]["product_id"]
        for path in PUBLIC_WEATHER_MODEL_PATHS
        if _model(path)["config"]["meta"]["serving"]["enabled"]
        and _model(path)["config"]["meta"]["serving"]["external"]
    }

    assert public_products == PUBLIC_WEATHER_PRODUCT_IDS


def test_weather_wave_a_readiness_singular_tests_are_wired_to_gold_selector() -> None:
    selectors = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))["selectors"]
    selector_names = {selector["name"] for selector in selectors}
    dbt_project = yaml.safe_load(DBT_PROJECT_PATH.read_text(encoding="utf-8"))

    assert "ask_seoul_weather_transform_gold" in selector_names
    serving_selector = next(
        selector
        for selector in selectors
        if selector["name"] == "ask_seoul_weather_transform_serving_gold"
    )
    serving_paths = {
        entry["value"]
        for entry in serving_selector["definition"]["union"]
        if entry["method"] == "path"
    }
    assert {
        "tests/weather/transform/gold/assert_gold_weather_place_current_outlook_readiness.sql",
        "tests/weather/transform/gold/assert_gold_weather_place_precipitation_window_valid_empty.sql",
        "tests/weather/transform/gold/assert_gold_weather_place_precipitation_window_non_overlapping.sql",
        "tests/weather/transform/gold/assert_gold_weather_place_forecast_change_daily_consistent.sql",
        "tests/weather/transform/gold/assert_gold_weather_place_risk_window_future_only.sql",
    } <= serving_paths
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
        RISK_FUTURE_ONLY_TEST: [
            "ref('gold_weather_place_risk_window')",
            "forecast_at < kst_now.current_hour_at",
        ],
    }
    for path, required_fragments in expected.items():
        assert path.exists(), f"missing readiness singular test: {path.name}"
        sql = path.read_text(encoding="utf-8")
        for fragment in required_fragments:
            assert fragment in sql, f"{path.name} missing {fragment}"

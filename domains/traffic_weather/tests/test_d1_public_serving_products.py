from __future__ import annotations

from pathlib import Path
import re

import yaml

from serving_contract.projection_identity import projection_schema_hash


PROJECT_DIR = Path(__file__).resolve().parents[1]
GOLD_DIRS = (
    PROJECT_DIR / "models" / "traffic" / "transform" / "gold",
    PROJECT_DIR / "models" / "weather" / "transform" / "gold",
)

EXPECTED_PRODUCTS = {
    "traffic_incident_x_weather_current_hourly",
    "traffic_flow_congestion_hotspots_hourly",
    "traffic_flow_link_latest",
    "traffic_flow_change_latest",
    "traffic_flow_link_time_profile",
    "traffic_flow_anomaly_current",
    "weather_place_current_outlook",
    "weather_place_precipitation_window",
    "weather_place_risk_window",
    "weather_place_forecast_change_daily",
}

EXPECTED_PUBLIC_PROJECTIONS = {
    "weather_place_current_outlook": [
        "product_row_id", "place_id", "place_name", "alias_names", "admin_dong_code", "admin_dong",
        "gu_code", "gu", "latitude", "longitude", "forecast_at", "forecast_category_count",
        "forecast_issued_at_min", "forecast_issued_at_max", "forecast_collected_at_max", "temp_c",
        "humidity_pct", "wind_ms", "wind_dir_deg", "precip_prob_pct", "sky_code", "sky_label",
        "pty_code", "pty_label", "is_precipitating", "pcp_raw", "pcp_mm", "sno_raw", "sno_cm",
        "forecast_lead_hours",
    ],
    "weather_place_precipitation_window": [
        "product_row_id", "place_id", "place_name", "window_start_at", "window_end_at",
    ],
    "weather_place_risk_window": [
        "product_row_id", "place_id", "place_name", "admin_dong_code", "admin_dong", "gu_code", "gu",
        "forecast_at", "temp_c", "wind_ms", "precip_prob_pct", "pty_code", "pcp_mm", "sno_cm",
        "heat_risk", "cold_risk", "heavy_rain_risk", "snow_risk", "wind_risk", "risk_labels",
        "forecast_issued_at_min", "forecast_issued_at_max", "forecast_collected_at_max",
    ],
    "weather_place_forecast_change_daily": [
        "product_row_id", "place_id", "forecast_date", "latest_issued_at", "change_state",
        "place_name", "admin_dong_code", "admin_dong", "gu_code", "gu", "previous_issued_at", "issue_gap_hours",
        "latest_category_count", "previous_category_count", "latest_forecast_hour_count",
        "previous_forecast_hour_count", "latest_min_temp_c", "previous_min_temp_c",
        "min_temp_change_c", "latest_max_temp_c", "previous_max_temp_c", "max_temp_change_c",
        "latest_max_precip_prob_pct", "previous_max_precip_prob_pct", "max_precip_prob_change_pct",
        "latest_first_precipitation_at", "previous_first_precipitation_at", "latest_collected_at_max",
        "previous_collected_at_max",
    ],
    "traffic_incident_x_weather_current_hourly": [
        "product_row_id", "admin_dong_code", "hour_at", "admin_dong", "gu_code", "gu",
        "admin_dong_revision_date", "incident_count", "has_incident", "quality_state",
        "snapshot_as_of_at", "status_observed_at", "published_at", "weather_category_coverage_count",
        "weather_latest_issued_at", "weather_latest_collected_at", "weather_latest_published_at",
        "tmp_value_num", "pop_value_num", "reh_value_num", "wsd_value_num", "sky_qualitative_code",
        "pty_qualitative_code", "is_precipitating",
    ],
    "traffic_flow_congestion_hotspots_hourly": [
        "product_row_id", "link_id", "hour_at", "flow_speed", "flow_travel_time",
        "flow_value_quality", "observed_at_kst", "congestion_rank", "observed_link_count",
        "hotspot_state",
    ],
    "traffic_flow_link_latest": [
        "product_row_id", "link_id", "flow_speed", "flow_travel_time", "flow_value_quality",
        "observed_at_kst", "collected_at_kst",
    ],
    "traffic_flow_change_latest": [
        "product_row_id", "link_id", "flow_speed", "flow_travel_time", "flow_value_quality",
        "observed_at_utc", "observed_at_kst", "previous_flow_speed", "previous_flow_travel_time",
        "previous_observed_at_kst", "flow_speed_change", "flow_travel_time_change", "speed_change_state",
    ],
    "traffic_flow_link_time_profile": [
        "product_row_id", "link_id", "kst_day_of_week", "kst_hour", "observation_count",
        "speed_observation_count", "avg_flow_speed", "min_flow_speed", "max_flow_speed",
        "avg_flow_travel_time", "first_observed_at_kst", "last_observed_at_kst",
    ],
    "traffic_flow_anomaly_current": [
        "product_row_id", "link_id", "flow_speed", "flow_travel_time", "flow_value_quality",
        "observed_at_kst", "collected_at_kst", "kst_day_of_week", "kst_hour",
        "profile_observation_count", "distinct_observation_date_count", "speed_observation_count",
        "p25_flow_speed", "median_flow_speed", "p75_flow_speed", "profile_first_observed_at_kst",
        "profile_last_observed_at_kst", "baseline_state", "speed_delta_from_median",
        "speed_ratio_to_median", "anomaly_direction",
    ],
}

EXPECTED_PUBLIC_PROJECTION_VERSIONS = {
    product_id: "1.0.0"
    for product_id in EXPECTED_PRODUCTS
}
EXPECTED_PUBLIC_PROJECTION_VERSIONS["weather_place_forecast_change_daily"] = "1.1.0"
EXPECTED_PUBLIC_PROJECTION_VERSIONS["weather_place_risk_window"] = "1.2.0"
EXPECTED_PUBLIC_PROJECTION_VERSIONS["weather_place_precipitation_window"] = "1.1.0"

EXPECTED_PUBLIC_PROJECTION_HASHES = {
    "traffic_flow_anomaly_current": "5973ee5d82abc24c34f3854976a0814bdbf94945233e2b9d790c038b74d509ef",
    "traffic_flow_change_latest": "528a6fbefa3bf4776cf7f0f6f68b102359154389fe13b0c89ff413d3d5c47c9a",
    "traffic_flow_congestion_hotspots_hourly": "65d41e4848057702d9a7ae4a7317a7a5f2641b82f33610c2ac6fa8e5f26ce6bd",
    "traffic_flow_link_latest": "c42d19c3ca3981577f0415bd80adac76c7d8fb102024a0bd17c2f348a43420c0",
    "traffic_flow_link_time_profile": "3481b492166efc5ae85240441b67a6e4fdd0f0d4eaf198b031f64ae5cef9fd35",
    "traffic_incident_x_weather_current_hourly": "79e6a5ebaa7df4629292c71e32b3b47e3d5d41510b45a9abc6cab401d2693c23",
    "weather_place_current_outlook": "62db82904ff1b66450676f3b64adc4d42c8729849f9e0ae83a9f8ec41ddef07b",
    "weather_place_forecast_change_daily": "75ae5336e3b826cf9352ce474b61c247915d921aad481da4f589b3e63ceb23cd",
    "weather_place_precipitation_window": "b9060e16dc077170e2d6448934a0650b4c773264308cfbea9605e3965d39bdc3",
    "weather_place_risk_window": "47e401e6422e4a54b0abbf1adf6a9b1e5d65d63edd6a3c4e87ac37e1e2a91e7b",
}

INTERNAL_PUBLIC_FIELD_FRAGMENTS = {
    "raw_object_key",
    "payload_hash",
    "request_id",
    "dag_run_id",
    "source_run_id",
    "snapshot_dag_run_id",
    "representative_dag_run_id",
    "api_key",
    "service_key",
    "access_key",
    "secret",
    "token",
    "password",
    "credential",
    "email",
    "ip_address",
}

REQUIRED_SERVING_FIELDS = {
    "enabled",
    "external",
    "product_id",
    "product_question",
    "grain",
    "primary_key",
    "publication_mode",
    "zero_policy",
    "publication_trigger",
}

V1_USAGE_PATTERN_EXPECTATIONS = {
    "weather_place_forecast_change_daily": {
        "pattern_id": "forecast_change_for_place_date",
        "question_fragment": "장소",
        "axes": "장소·예보일 필터 — 최신·직전 발표 변화 비교",
        "requires": ["select_columns"],
        "sql_fragments": [
            "FROM gold_weather_place_forecast_change_daily",
            "WHERE place_id = :place_id",
            "forecast_date = :forecast_date",
            "change_state",
            "max_precip_prob_change_pct",
        ],
    },
    "traffic_incident_x_weather_current_hourly": {
        "pattern_id": "incident_weather_for_dong_hour",
        "question_fragment": "행정동",
        "axes": "행정동·평가 시각 필터 — 돌발 현황과 no-hindsight 날씨 맥락",
        "requires": ["select_columns"],
        "sql_fragments": [
            "FROM gold_traffic_incident_x_weather_current_hourly",
            "WHERE admin_dong_code = :admin_dong_code",
            "hour_at = :hour_at",
            "quality_state",
            "weather_category_coverage_count",
        ],
    },
}

MIN_EXTERNAL_USAGE_PATTERNS = 8
MAX_EXTERNAL_USAGE_PATTERNS = 20  # Serving#217: 저작 패턴 채택으로 상향(masondev 승인)
ALLOWED_USAGE_PATTERN_REQUIRES = {
    "select_columns",
    "sort",
    "aggregate",
    "group_by",
    "having",
    "join",
    "subquery",
    "window",
    "filter_range",
    "filter_set",
    "filter_null",
}

LEGACY_SERVING_FIELDS = {
    "serving_tier",
    "serving_gold_candidate",
    "external",
    "refresh",
}


def _models() -> dict[str, dict]:
    models: dict[str, dict] = {}
    for directory in GOLD_DIRS:
        for path in directory.glob("*.yml"):
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for model in payload.get("models", []):
                models[model["name"]] = model
    return models


def _test_names(column: dict) -> set[str]:
    names: set[str] = set()
    for test in column.get("tests", []):
        if isinstance(test, str):
            names.add(test)
        elif isinstance(test, dict):
            names.update(test)
    return names


def test_public_d1_products_have_complete_non_legacy_serving_contracts() -> None:
    models = _models()

    for product_id in EXPECTED_PRODUCTS:
        model_name = f"gold_{product_id}"
        assert model_name in models, f"missing dbt model contract: {model_name}"

        model = models[model_name]
        meta = model.get("config", {}).get("meta", {})
        serving = meta.get("serving")
        assert serving is not None, f"missing meta.serving: {model_name}"
        assert serving["product_id"] == product_id
        assert REQUIRED_SERVING_FIELDS <= serving.keys()
        assert serving["enabled"] is True
        assert serving["external"] is True
        assert LEGACY_SERVING_FIELDS.isdisjoint(meta)

        columns = {
            column["name"]: column
            for column in model.get("columns", [])
        }
        for primary_key in serving["primary_key"]:
            assert primary_key in columns
            assert "not_null" in _test_names(columns[primary_key])


def test_public_d1_product_ids_are_unique() -> None:
    products: list[str] = []
    for model in _models().values():
        serving = model.get("config", {}).get("meta", {}).get("serving")
        if serving is not None:
            products.append(serving["product_id"])

    assert len(products) == len(set(products))


def test_enabled_external_d1_products_match_portfolio() -> None:
    active_products = {
        serving["product_id"]
        for model in _models().values()
        if (serving := model.get("config", {}).get("meta", {}).get("serving"))
        and serving.get("enabled") is True
        and serving.get("external") is True
    }

    assert active_products == EXPECTED_PRODUCTS


def test_public_d1_products_declare_exact_ordered_public_projection() -> None:
    models = _models()

    assert set(EXPECTED_PUBLIC_PROJECTIONS) == EXPECTED_PRODUCTS
    for product_id, expected_columns in EXPECTED_PUBLIC_PROJECTIONS.items():
        model = models[f"gold_{product_id}"]
        serving = model["config"]["meta"]["serving"]

        assert serving["public_projection"] == {
            "schema_version": EXPECTED_PUBLIC_PROJECTION_VERSIONS[product_id],
            "columns": expected_columns,
        }


def test_public_d1_projection_identity_hashes_are_pinned() -> None:
    models = _models()

    assert set(EXPECTED_PUBLIC_PROJECTION_HASHES) == EXPECTED_PRODUCTS
    for product_id, expected_hash in EXPECTED_PUBLIC_PROJECTION_HASHES.items():
        model = models[f"gold_{product_id}"]
        serving = model["config"]["meta"]["serving"]
        columns = {column["name"]: column for column in model.get("columns", [])}

        actual_hash = projection_schema_hash(serving["public_projection"], columns)
        assert actual_hash == expected_hash, f"{product_id} projection identity drifted"


def test_public_d1_projection_columns_are_declared_and_public_safe() -> None:
    models = _models()

    for product_id, expected_columns in EXPECTED_PUBLIC_PROJECTIONS.items():
        model = models[f"gold_{product_id}"]
        columns = {column["name"]: column for column in model.get("columns", [])}

        for column_name in expected_columns:
            assert column_name in columns, f"{product_id}.{column_name} missing column declaration"
            lowered = column_name.lower()
            assert not any(fragment in lowered for fragment in INTERNAL_PUBLIC_FIELD_FRAGMENTS), (
                f"{product_id}.{column_name} exposes an internal/secret identifier"
            )
            column = columns[column_name]
            meta = column.get("config", {}).get("meta", {})
            assert column.get("description"), f"{product_id}.{column_name} missing description"
            assert column.get("data_type"), f"{product_id}.{column_name} missing data_type"
            assert meta.get("semantic_role"), f"{product_id}.{column_name} missing semantic_role"
            assert isinstance(meta.get("nullable"), bool), f"{product_id}.{column_name} missing nullable boolean"
            assert meta.get("null_meaning"), f"{product_id}.{column_name} missing null_meaning"
            assert meta.get("unit"), f"{product_id}.{column_name} missing unit"


def test_v1_skill_products_keep_verified_reference_usage_patterns() -> None:
    models = _models()

    for product_id, expected in V1_USAGE_PATTERN_EXPECTATIONS.items():
        serving = models[f"gold_{product_id}"]["config"]["meta"]["serving"]
        patterns = serving.get("usage_patterns")

        assert isinstance(patterns, list) and patterns, f"{product_id} missing usage_patterns"
        by_id = {pattern.get("pattern_id"): pattern for pattern in patterns}
        assert expected["pattern_id"] in by_id, f"{product_id} missing V1 usage pattern"

        pattern = by_id[expected["pattern_id"]]
        assert expected["question_fragment"] in pattern["question_ko"]
        assert pattern["axes"] == expected["axes"]
        assert pattern["requires"] == expected["requires"]
        assert pattern["allow_empty"] is True
        assert isinstance(pattern.get("verified_rows"), int) and pattern["verified_rows"] >= 0
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", pattern.get("verified_at", ""))
        assert re.fullmatch(r"[0-9a-f]{32}", pattern.get("verified_publication_id", ""))
        for fragment in expected["sql_fragments"]:
            assert fragment in pattern["sql"]


def test_external_d1_products_declare_eight_distinct_usage_patterns() -> None:
    models = _models()

    for product_id in EXPECTED_PRODUCTS:
        serving = models[f"gold_{product_id}"]["config"]["meta"]["serving"]
        patterns = serving.get("usage_patterns")

        assert isinstance(patterns, list), f"{product_id} usage_patterns must be a list"
        assert len(patterns) >= MIN_EXTERNAL_USAGE_PATTERNS, (
            f"{product_id} needs at least {MIN_EXTERNAL_USAGE_PATTERNS} external usage patterns"
        )
        assert len(patterns) <= MAX_EXTERNAL_USAGE_PATTERNS, (
            f"{product_id} must keep at most {MAX_EXTERNAL_USAGE_PATTERNS} external usage patterns"
        )

        pattern_ids = [pattern.get("pattern_id") for pattern in patterns]
        assert all(isinstance(pattern_id, str) and pattern_id for pattern_id in pattern_ids)
        assert len(pattern_ids) == len(set(pattern_ids)), f"{product_id} has duplicate pattern IDs"

        for pattern in patterns:
            assert isinstance(pattern.get("question_ko"), str) and pattern["question_ko"].strip()
            assert isinstance(pattern.get("axes"), str) and pattern["axes"].strip()
            assert isinstance(pattern.get("sql"), str) and pattern["sql"].strip()
            assert f"FROM gold_{product_id}" in pattern["sql"]
            assert isinstance(pattern.get("allow_empty"), bool)
            lowered_sql = pattern["sql"].lower()
            assert not any(fragment in lowered_sql for fragment in INTERNAL_PUBLIC_FIELD_FRAGMENTS), (
                f"{product_id}.{pattern['pattern_id']} references an internal/secret field"
            )

            assert isinstance(pattern.get("verified_rows"), int) and pattern["verified_rows"] >= 0
            # Serving#217: 검증 스탬프는 **검증된 패턴에만** 강제한다. 저작 채택 패턴은
            # verified_rows=0(스탬프 대기)로 카탈로그에 올라오되, 게이트웨이가 verified_at
            # 없는 패턴을 runnable=false 로 막아 실행 시 409 를 준다 — 미검증이 소비자에게
            # 잘못 서빙되지 않으므로, 스탬프 전 카탈로그 등재를 계약이 허용한다(masondev 승인).
            # 검증됐다고 선언한 패턴(verified_rows>0 또는 스탬프 존재)은 여전히 유효한 스탬프 필수.
            _has_stamp = bool(pattern.get("verified_at")) or bool(pattern.get("verified_publication_id"))
            if pattern["verified_rows"] > 0 or _has_stamp:
                assert re.fullmatch(
                    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                    pattern.get("verified_at", ""),
                ), f"{product_id}.{pattern['pattern_id']} 검증됐다면 verified_at 스탬프가 유효해야 한다"
                assert re.fullmatch(
                    r"[0-9a-f]{32}",
                    pattern.get("verified_publication_id", ""),
                ), f"{product_id}.{pattern['pattern_id']} 검증됐다면 verified_publication_id 가 유효해야 한다"

            executable_sql = re.sub(r"--.*$", "", pattern["sql"], flags=re.MULTILINE)
            placeholders = set(re.findall(r":([a-z][a-z0-9_]*)", executable_sql))
            documented_params = set(
                re.findall(r":([a-z][a-z0-9_]*)\s*=", pattern["sql"])
            )
            assert placeholders <= documented_params, (
                f"{product_id}.{pattern['pattern_id']} lacks reproducible verified parameters"
            )
            n_match = re.search(r":n=(\d+)", pattern["sql"])
            if n_match:
                assert pattern["verified_rows"] <= int(n_match.group(1)), (
                    f"{product_id}.{pattern['pattern_id']} verified rows exceed documented :n"
                )

            requires = pattern.get("requires")
            assert isinstance(requires, list) and requires
            assert set(requires) <= ALLOWED_USAGE_PATTERN_REQUIRES


def test_contract_critical_usage_patterns_keep_complete_quality_states() -> None:
    models = _models()

    congestion_patterns = models[
        "gold_traffic_flow_congestion_hotspots_hourly"
    ]["config"]["meta"]["serving"]["usage_patterns"]
    missing_speed = next(
        pattern for pattern in congestion_patterns
        if pattern["pattern_id"] == "missing_speed_for_hour"
    )
    assert "hotspot_state = 'missing_speed'" in missing_speed["sql"]

    incident_patterns = models[
        "gold_traffic_incident_x_weather_current_hourly"
    ]["config"]["meta"]["serving"]["usage_patterns"]
    incomplete_weather = next(
        pattern for pattern in incident_patterns
        if pattern["pattern_id"] == "incomplete_weather_context"
    )
    assert "coalesce(weather_category_coverage_count, 0) < :required_category_count" in incomplete_weather["sql"]


def test_public_d1_not_null_projection_columns_are_non_nullable() -> None:
    models = _models()
    conflicts: list[str] = []

    for product_id, projected_columns in EXPECTED_PUBLIC_PROJECTIONS.items():
        model = models[f"gold_{product_id}"]
        columns = {column["name"]: column for column in model.get("columns", [])}

        for column_name in projected_columns:
            column = columns[column_name]
            if "not_null" not in _test_names(column):
                continue
            nullable = column.get("config", {}).get("meta", {}).get("nullable")
            if nullable is not False:
                conflicts.append(f"{product_id}.{column_name}")

    assert not conflicts, f"not_null projection columns declared nullable: {conflicts}"

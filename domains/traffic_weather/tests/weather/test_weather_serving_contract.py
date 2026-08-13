from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import yaml

from serving_contract.verify_stamp import resolve_params, substitute


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_SCHEMA = (
    PROJECT_ROOT / "models/weather/transform/gold/_gold.yml"
)
HOURLY_OUTLOOK_SQL = (
    PROJECT_ROOT / "models/weather/transform/gold/gold_weather_place_hourly_outlook.sql"
)
CURRENT_OUTLOOK_SCHEMA = (
    PROJECT_ROOT / "models/weather/transform/gold/gold_weather_place_current_outlook.yml"
)
MODEL_NAME = "gold_weather_current_wide_by_admin_dong"


def _weather_current_model() -> dict:
    payload = yaml.safe_load(GOLD_SCHEMA.read_text(encoding="utf-8"))
    return next(model for model in payload["models"] if model["name"] == MODEL_NAME)


def _current_outlook_pattern(pattern_id: str) -> dict:
    payload = yaml.safe_load(CURRENT_OUTLOOK_SCHEMA.read_text(encoding="utf-8"))
    model = next(
        model
        for model in payload["models"]
        if model["name"] == "gold_weather_place_current_outlook"
    )
    patterns = model["config"]["meta"]["serving"]["usage_patterns"]
    return next(pattern for pattern in patterns if pattern["pattern_id"] == pattern_id)


def test_weather_current_wide_declares_v11_serving_contract():
    model = _weather_current_model()
    serving = model["config"]["meta"]["serving"]

    assert serving == {
        "enabled": False,
        "external": False,
        "contract_version": "v1",
        "product_id": "weather_current_by_admin_dong",
        "product_question": "서울 행정동별 현재 최신 KMA 예보는 무엇인가?",
        "grain": "행정동(admin_dong_code)마다 한 행",
        "primary_key": ["admin_dong_code"],
        "event_time": "forecast_at",
        "freshness_slo_minutes": 240,
        "publication_mode": "snapshot",
        "zero_policy": "retain_last_good",
        "shape": "wide",
        "publication_trigger": {
            "schedule_cron": "50 2,5,8,11,14,17,20,23 * * *",
        },
    }


def test_weather_current_wide_keeps_primary_key_evidence_and_no_legacy_serving_meta():
    model = _weather_current_model()
    meta = model["config"]["meta"]
    columns = {column["name"]: column for column in model["columns"]}

    assert {"serving_tier", "serving_gold_candidate", "external", "refresh"}.isdisjoint(
        meta
    )
    assert columns["admin_dong_code"]["tests"] == ["not_null", "unique"]


def test_weather_hourly_converts_bronze_utc_collection_time_to_kst_for_gold_freshness():
    sql = HOURLY_OUTLOOK_SQL.read_text(encoding="utf-8")

    assert "max(cast({{ asac_axes.utc_to_kst('collected_at') }} as timestamp(6))) as forecast_collected_at_max" in sql


def test_current_outlook_default_window_includes_the_current_hour_snapshot():
    pattern = _current_outlook_pattern("outlook_forecast_window")
    # 2026-08-13 17:19 UTC = 2026-08-14 02:19 KST. The published snapshot is 02:00 KST.
    now = datetime(2026, 8, 13, 17, 19, 0, tzinfo=timezone.utc)
    executable, resolved, unresolved = resolve_params(
        pattern["sql"],
        param_defaults=pattern["param_defaults"],
        now=now,
    )

    assert unresolved == []
    assert resolved["from_at"] == "'2026-08-14'"
    assert resolved["to_at"] == "'2026-08-16 00:00:00'"

    with sqlite3.connect(":memory:") as connection:
        connection.executescript(
            """
            CREATE TABLE gold_weather_place_current_outlook (
                place_id TEXT,
                place_name TEXT,
                gu TEXT,
                forecast_at TEXT,
                temp_c REAL,
                precip_prob_pct REAL,
                sky_label TEXT,
                pty_label TEXT
            );
            INSERT INTO gold_weather_place_current_outlook VALUES (
                'seoul_admd_1117059000', '가상동', '가상구',
                '2026-08-14 02:00:00', 27.0, 20.0, '맑음', '없음'
            );
            """
        )
        rows = connection.execute(substitute(executable, resolved)).fetchall()

    assert len(rows) == 1

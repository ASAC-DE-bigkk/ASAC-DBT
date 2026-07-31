from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_SCHEMA = (
    PROJECT_ROOT / "models/weather/transform/gold/_gold.yml"
)
MODEL_NAME = "gold_weather_current_wide_by_admin_dong"


def _weather_current_model() -> dict:
    payload = yaml.safe_load(GOLD_SCHEMA.read_text(encoding="utf-8"))
    return next(model for model in payload["models"] if model["name"] == MODEL_NAME)


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

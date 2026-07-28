from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "weather"
    / "transform"
    / "gold"
    / "gold_weather_x_citydata_ppltn_hourly.sql"
)


def test_citydata_weather_gold_uses_aggregate_winner_without_hindsight() -> None:
    sql = MODEL_PATH.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "max_by(" in sql
    assert "row_number() over" not in sql.lower()
    assert "weather.issued_at <= citydata.event_at" in normalized
    assert (
        "group by citydata.area_cd, citydata.event_at, "
        "upper(cast(weather.category as varchar))"
    ) in normalized
    assert "winner.issued_at" in sql
    assert "winner.collected_at" in sql
    assert "winner.value_num" in sql
    assert "winner.value_raw" in sql

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

MODEL_EXPECTATIONS = {
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "gold"
    / "gold_traffic_incident_x_culture_activity_daily.sql": (
        "cast(kopis_festivals_count as bigint) as kopis_festivals_count",
        "culture.kopis_festivals_count",
    ),
    PROJECT_ROOT
    / "models"
    / "weather"
    / "transform"
    / "gold"
    / "gold_weather_x_culture_activity_daily.sql": (
        "kopis_festivals_count,",
        "culture.kopis_festivals_count",
    ),
}


def test_cross_domain_gold_models_follow_culture_kopis_festivals_column_contract():
    for model_path, required_fragments in MODEL_EXPECTATIONS.items():
        sql = model_path.read_text(encoding="utf-8")

        for fragment in required_fragments:
            assert fragment in sql
        assert re.search(r"\bfestivals_count\b", sql) is None

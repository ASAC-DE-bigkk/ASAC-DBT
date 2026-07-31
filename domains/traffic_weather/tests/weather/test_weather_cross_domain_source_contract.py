from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEATHER_SOURCES_PATH = PROJECT_ROOT / "models" / "weather" / "sources.yml"
CITYDATA_SCHEMA = (
    "{{ env_var('SEOUL_CITYDATA_SCHEMA', "
    "'citydata' if target.name == 'prod' else 'seoul_citydata') }}"
)


def test_weather_citydata_source_uses_target_aware_physical_schema() -> None:
    document = yaml.safe_load(WEATHER_SOURCES_PATH.read_text(encoding="utf-8")) or {}
    sources = {source["name"]: source for source in document.get("sources", [])}

    assert sources["citydata_gold"]["schema"] == CITYDATA_SCHEMA

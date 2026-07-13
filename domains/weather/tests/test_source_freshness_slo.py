"""Weather/Traffic source freshness SLO alignment contract."""
from __future__ import annotations

from pathlib import Path

import yaml


DBT_ROOT = Path(__file__).resolve().parents[3]


def _load_sources(domain: str) -> dict:
    path = DBT_ROOT / "domains" / domain / "models" / "sources.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _source(document: dict, name: str) -> dict:
    return next(source for source in document["sources"] if source["name"] == name)


def _table(source: dict, name: str) -> dict:
    return next(table for table in source["tables"] if table["name"] == name)


def test_weather_and_traffic_source_freshness_match_watchdog_slos():
    weather = _source(_load_sources("weather"), "weather_bronze")
    traffic = _source(_load_sources("traffic"), "traffic_bronze")
    traffic_manifest = _table(traffic, "collection_run_manifest")

    assert weather["freshness"] == {
        "warn_after": {"count": 4, "period": "hour"},
        "error_after": {"count": 6, "period": "hour"},
    }
    assert traffic_manifest["freshness"] == {
        "warn_after": {"count": 15, "period": "minute"},
        "error_after": {"count": 30, "period": "minute"},
    }

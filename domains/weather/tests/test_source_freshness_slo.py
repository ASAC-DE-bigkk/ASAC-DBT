"""Weather source freshness SLO alignment contract."""
from __future__ import annotations

from pathlib import Path

import yaml


DBT_ROOT = Path(__file__).resolve().parents[3]


def _load_sources(domain: str) -> dict:
    path = DBT_ROOT / "domains" / domain / "models" / "sources.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _source(document: dict, name: str) -> dict:
    return next(source for source in document["sources"] if source["name"] == name)


def test_weather_source_freshness_matches_watchdog_slo():
    weather = _source(_load_sources("weather"), "weather_bronze")

    assert weather["freshness"] == {
        "warn_after": {"count": 4, "period": "hour"},
        "error_after": {"count": 6, "period": "hour"},
    }

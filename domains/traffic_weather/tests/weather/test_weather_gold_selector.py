from pathlib import Path

import yaml


SELECTORS_PATH = Path(__file__).resolve().parents[2] / "selectors.yml"
GOLD_SELECTOR = "ask_seoul_weather_transform_gold"
COMMERCE_SCOPE = "ask_seoul_weather_transform_commerce_gold_scope"
SCHEDULED_SELECTOR = "ask_seoul_weather_transform_gold_without_commerce"


def _selectors() -> dict[str, dict]:
    document = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))
    return {
        selector["name"]: selector["definition"] for selector in document["selectors"]
    }


def test_scheduled_weather_gold_uses_full_cross_domain_scope():
    selectors = _selectors()

    assert GOLD_SELECTOR in selectors
    assert COMMERCE_SCOPE not in selectors
    assert SCHEDULED_SELECTOR not in selectors

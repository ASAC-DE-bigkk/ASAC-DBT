from pathlib import Path

import yaml


SELECTORS_PATH = Path(__file__).resolve().parents[2] / "selectors.yml"
GOLD_SELECTOR = "ask_seoul_weather_transform_gold"
COMMERCE_SCOPE = "ask_seoul_weather_transform_commerce_gold_scope"
SCHEDULED_SELECTOR = "ask_seoul_weather_transform_gold_without_commerce"
COMMERCE_MODEL = "gold_weather_x_commerce_business_exposure_daily"


def _selectors() -> dict[str, dict]:
    document = yaml.safe_load(SELECTORS_PATH.read_text(encoding="utf-8"))
    return {
        selector["name"]: selector["definition"] for selector in document["selectors"]
    }


def test_scheduled_weather_gold_excludes_only_the_commerce_leaf_scope():
    selectors = _selectors()

    assert selectors[COMMERCE_SCOPE] == {
        "union": [
            {
                "method": "fqn",
                "value": COMMERCE_MODEL,
                "children": True,
            }
        ]
    }
    assert selectors[SCHEDULED_SELECTOR] == {
        "intersection": [
            {"method": "selector", "value": GOLD_SELECTOR},
            {"exclude": [{"method": "selector", "value": COMMERCE_SCOPE}]},
        ]
    }

from __future__ import annotations

from pathlib import Path
import re
import unittest

import yaml


PROJECT_DIR = Path(__file__).resolve().parents[1]
TRAFFIC_GOLD_DIR = PROJECT_DIR / "models" / "traffic" / "transform" / "gold"
WEATHER_GOLD_DIR = PROJECT_DIR / "models" / "weather" / "transform" / "gold"
TRAFFIC_SOURCES = PROJECT_DIR / "models" / "traffic" / "sources.yml"
WEATHER_SOURCES = PROJECT_DIR / "models" / "weather" / "sources.yml"
PORTFOLIO_CATALOG = PROJECT_DIR / "contracts" / "serving_gold_catalog.yml"


def portfolio_catalog() -> dict:
    return yaml.safe_load(PORTFOLIO_CATALOG.read_text(encoding="utf-8"))


PORTFOLIO = portfolio_catalog()
TRAFFIC_SERVING_MODELS = set(PORTFOLIO["domains"]["traffic"]["serving_models"])
WEATHER_SERVING_MODELS = set(PORTFOLIO["domains"]["weather"]["serving_models"])
OPERATIONS_OR_QUALITY_MODELS = set(PORTFOLIO["operations_or_quality_models"])


def sql_models(directory: Path) -> set[str]:
    return {path.stem for path in directory.glob("gold_*.sql")}


def source_names(path: Path) -> set[str]:
    return set(re.findall(r"^  - name: ([A-Za-z0-9_]+)$", path.read_text(), re.MULTILINE))


def model_metadata(directory: Path) -> dict[str, dict]:
    models: dict[str, dict] = {}
    for path in directory.glob("*.yml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for model in document.get("models", []):
            models[model["name"]] = model
    return models


class ServingGoldPortfolioContractTest(unittest.TestCase):
    def test_catalog_targets_existing_traffic_and_weather_schemas(self) -> None:
        self.assertEqual(PORTFOLIO["catalog_status"], "dev_pending")
        self.assertEqual(PORTFOLIO["domains"]["traffic"]["schema"], "traffic")
        self.assertEqual(PORTFOLIO["domains"]["weather"]["schema"], "weather")

    def test_traffic_serving_portfolio_has_exactly_fifteen_models(self) -> None:
        self.assertEqual(len(TRAFFIC_SERVING_MODELS), 15)
        self.assertTrue(
            TRAFFIC_SERVING_MODELS.issubset(sql_models(TRAFFIC_GOLD_DIR)),
            "Traffic serving Gold SQL models are incomplete",
        )

    def test_weather_serving_portfolio_has_exactly_fifteen_models(self) -> None:
        self.assertEqual(len(WEATHER_SERVING_MODELS), 15)
        self.assertTrue(
            WEATHER_SERVING_MODELS.issubset(sql_models(WEATHER_GOLD_DIR)),
            "Weather serving Gold SQL models are incomplete",
        )

    def test_quality_models_are_not_listed_as_serving_models(self) -> None:
        serving_models = TRAFFIC_SERVING_MODELS | WEATHER_SERVING_MODELS
        self.assertTrue(
            serving_models.isdisjoint(OPERATIONS_OR_QUALITY_MODELS),
            "quality/operations model leaked into serving portfolio",
        )

    def test_traffic_quality_models_stay_outside_the_serving_portfolio(self) -> None:
        metadata = model_metadata(TRAFFIC_GOLD_DIR)
        traffic_quality_models = {
            name
            for name, model in metadata.items()
            if model.get("config", {}).get("meta", {}).get("traffic_quality_product") is True
        }

        self.assertTrue(traffic_quality_models)
        self.assertTrue(traffic_quality_models.issubset(OPERATIONS_OR_QUALITY_MODELS))
        self.assertTrue(TRAFFIC_SERVING_MODELS.isdisjoint(traffic_quality_models))

    def test_traffic_and_weather_source_names_are_unambiguous(self) -> None:
        duplicate_names = source_names(TRAFFIC_SOURCES) & source_names(WEATHER_SOURCES)
        self.assertEqual(
            duplicate_names,
            set(),
            "source() names must be unique across the combined dbt project",
        )


if __name__ == "__main__":
    unittest.main()

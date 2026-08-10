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
MCP_OPERATION_BY_MODEL = {
    "gold_weather_place_current_outlook": "weather.get_current_outlook",
    "gold_weather_place_precipitation_window": "weather.find_precipitation_windows",
    "gold_weather_place_risk_window": "weather.find_risk_windows",
    "gold_weather_place_forecast_change_daily": "weather.compare_forecast_change_daily",
    "gold_traffic_incident_x_weather_current_hourly": "traffic.get_incident_weather_context",
    "gold_traffic_flow_congestion_hotspots_hourly": "traffic.list_congestion_hotspots",
    "gold_traffic_flow_link_latest": "traffic.get_link_latest",
    "gold_traffic_flow_change_latest": "traffic.get_flow_change",
    "gold_traffic_flow_link_time_profile": "traffic.get_link_time_profile",
    "gold_traffic_flow_anomaly_current": "traffic.list_flow_anomalies",
}


def sql_models(directory: Path) -> set[str]:
    return {path.stem for path in directory.glob("gold_*.sql")}


def source_names(path: Path) -> set[str]:
    return set(
        re.findall(
            r"^  - name: ([A-Za-z0-9_]+)$",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )


def model_metadata(directory: Path) -> dict[str, dict]:
    models: dict[str, dict] = {}
    for path in directory.glob("*.yml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for model in document.get("models", []):
            models[model["name"]] = model
    return models


def all_model_metadata() -> dict[str, dict]:
    models: dict[str, dict] = {}
    for path in (PROJECT_DIR / "models").rglob("*.yml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for model in document.get("models", []):
            models[model["name"]] = model
    return models


def mcp_projections(metadata: dict[str, dict]) -> dict[str, dict]:
    projections: dict[str, dict] = {}
    for name, model in metadata.items():
        config = model.get("config") if isinstance(model, dict) else None
        meta = config.get("meta") if isinstance(config, dict) else None
        serving = meta.get("serving") if isinstance(meta, dict) else None
        projection = serving.get("mcp_projection") if isinstance(serving, dict) else None
        if isinstance(projection, dict):
            projections[name] = projection
    return projections


class ServingGoldPortfolioContractTest(unittest.TestCase):
    def test_mcp_projection_collector_includes_every_declared_model(self) -> None:
        approved = {
            "schema_version": "mcp-product-projection/v1",
            "operation": {"id": "weather.get_current_outlook"},
            "question_examples": ["현재 예보를 보여주세요."],
        }
        extra = {
            "schema_version": "mcp-product-projection/v1",
            "operation": {"id": "weather.unapproved_operation"},
            "question_examples": ["승인되지 않은 질문입니다."],
        }
        metadata = {
            "gold_weather_place_current_outlook": {
                "config": {"meta": {"serving": {"mcp_projection": approved}}}
            },
            "gold_weather_unapproved": {
                "config": {"meta": {"serving": {"mcp_projection": extra}}}
            },
            "gold_weather_without_projection": {"config": {"meta": {"serving": {}}}},
        }

        self.assertEqual(
            {
                "gold_weather_place_current_outlook": approved,
                "gold_weather_unapproved": extra,
            },
            mcp_projections(metadata),
        )

    def test_catalog_targets_existing_traffic_and_weather_schemas(self) -> None:
        self.assertEqual(PORTFOLIO["catalog_status"], "dev_pending")
        self.assertEqual(PORTFOLIO["domains"]["traffic"]["schema"], "traffic")
        self.assertEqual(PORTFOLIO["domains"]["weather"]["schema"], "weather")

    def test_traffic_serving_portfolio_has_exactly_seven_d1_models(self) -> None:
        self.assertEqual(len(TRAFFIC_SERVING_MODELS), 7)
        self.assertTrue(
            TRAFFIC_SERVING_MODELS.issubset(sql_models(TRAFFIC_GOLD_DIR)),
            "Traffic serving Gold SQL models are incomplete",
        )

    def test_weather_serving_portfolio_has_exactly_seventeen_models(self) -> None:
        self.assertEqual(len(WEATHER_SERVING_MODELS), 17)
        self.assertTrue(
            {
                "gold_weather_grid_current_outlook",
                "gold_weather_grid_precipitation_window",
            }.issubset(WEATHER_SERVING_MODELS)
        )
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

    def test_mcp_portfolio_has_ten_operations_and_thirty_examples(self) -> None:
        projections = mcp_projections(all_model_metadata())
        self.assertEqual(set(MCP_OPERATION_BY_MODEL), set(projections))
        self.assertEqual(
            set(MCP_OPERATION_BY_MODEL.values()),
            {projection["operation"]["id"] for projection in projections.values()},
        )
        self.assertTrue(
            all(
                len(projection["question_examples"]) == 3
                and len(set(projection["question_examples"])) == 3
                and all(re.search(r"[가-힣]", question) for question in projection["question_examples"])
                for projection in projections.values()
            )
        )
        self.assertEqual(
            30,
            sum(len(projection["question_examples"]) for projection in projections.values()),
        )
        self.assertTrue(
            all(
                projection["operation"]["approval_status"] == "approved"
                and projection["operation"]["execution_mode"] == "catalog_only"
                for projection in projections.values()
            )
        )

    def test_traffic_and_weather_source_names_are_unambiguous(self) -> None:
        duplicate_names = source_names(TRAFFIC_SOURCES) & source_names(WEATHER_SOURCES)
        self.assertEqual(
            duplicate_names,
            set(),
            "source() names must be unique across the combined dbt project",
        )


if __name__ == "__main__":
    unittest.main()

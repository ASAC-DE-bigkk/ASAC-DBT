from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"
APPROVED_PRODUCTS = {
    "gold_traffic_incident_current_by_admin_dong_hourly",
    "gold_traffic_incident_x_flow",
    "gold_traffic_incident_collection_coverage_5m",
    "gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily",
    "gold_traffic_incident_spatial_mapping_quality_daily",
}
SUMMARY_MODEL = "gold_traffic_incident_summary"


def _gold_model_metadata() -> dict[str, dict]:
    models: dict[str, dict] = {}
    for path in sorted(GOLD_DIR.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for model in document.get("models", []):
            name = model["name"]
            assert name not in models, f"duplicate Gold metadata for {name}"
            models[name] = model
    return models


def _meta(model: dict) -> dict:
    return model.get("config", {}).get("meta", {})


def test_existing_traffic_quality_gold_classification() -> None:
    models = _gold_model_metadata()

    assert _meta(
        models["gold_traffic_incident_current_by_admin_dong_hourly"]
    ).get("traffic_quality_product") is True
    assert _meta(models["gold_traffic_incident_x_flow"]).get(
        "traffic_quality_product"
    ) is True
    assert _meta(models[SUMMARY_MODEL]).get("traffic_quality_product") is False
    assert _meta(models[SUMMARY_MODEL]).get("support_only") is True


def test_traffic_quality_gold_metadata_ship_set_is_exactly_five() -> None:
    models = _gold_model_metadata()
    actual = {
        name
        for name, model in models.items()
        if _meta(model).get("traffic_quality_product") is True
    }

    assert actual == APPROVED_PRODUCTS
    assert SUMMARY_MODEL not in actual


def test_traffic_quality_gold_physical_ship_set_is_exactly_five() -> None:
    actual = {
        path.stem
        for path in GOLD_DIR.glob("gold_traffic_incident_*.sql")
        if path.stem != SUMMARY_MODEL
    }

    assert actual == APPROVED_PRODUCTS

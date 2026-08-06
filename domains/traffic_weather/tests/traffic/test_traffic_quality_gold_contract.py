from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"
PORTFOLIO_CATALOG = PROJECT_ROOT / "contracts" / "serving_gold_catalog.yml"
APPROVED_PRODUCTS = {
    "gold_traffic_incident_current_by_admin_dong_hourly",
    "gold_traffic_incident_x_flow",
    "gold_traffic_incident_collection_coverage_5m",
    "gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily",
    "gold_traffic_incident_spatial_mapping_quality_daily",
}
SUMMARY_MODEL = "gold_traffic_incident_summary"
CROSS_DOMAIN_GOLD_PRODUCTS = {
    "gold_traffic_incident_x_weather_current_hourly",
}


def _traffic_serving_gold_products() -> set[str]:
    catalog = yaml.safe_load(PORTFOLIO_CATALOG.read_text(encoding="utf-8")) or {}
    return set(catalog["domains"]["traffic"]["serving_models"])


TRAFFIC_SERVING_GOLD_PRODUCTS = _traffic_serving_gold_products()


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
        and path.stem not in CROSS_DOMAIN_GOLD_PRODUCTS
        and path.stem not in TRAFFIC_SERVING_GOLD_PRODUCTS
    }

    assert actual == APPROVED_PRODUCTS


def test_traffic_serving_gold_products_are_not_quality_products() -> None:
    models = _gold_model_metadata()

    assert TRAFFIC_SERVING_GOLD_PRODUCTS.issubset(models)
    for name in TRAFFIC_SERVING_GOLD_PRODUCTS:
        assert _meta(models[name]).get("traffic_quality_product") is not True


def test_cross_domain_gold_products_are_not_traffic_quality_products() -> None:
    models = _gold_model_metadata()

    assert set(CROSS_DOMAIN_GOLD_PRODUCTS).issubset(models)
    for name in CROSS_DOMAIN_GOLD_PRODUCTS:
        meta = _meta(models[name])
        assert meta.get("cross_domain_gold") is True
        assert meta.get("traffic_quality_product") is False

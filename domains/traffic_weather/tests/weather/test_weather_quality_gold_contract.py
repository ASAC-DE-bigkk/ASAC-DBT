from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEATHER_ROOT = PROJECT_ROOT / "models" / "weather"
GOLD_ROOT = WEATHER_ROOT / "transform" / "gold"
TEST_ROOT = PROJECT_ROOT / "tests" / "weather" / "transform" / "gold"
DOC_ROOT = PROJECT_ROOT / "docs" / "weather"

GOLD_YML = GOLD_ROOT / "_gold.yml"
SOURCES_YML = WEATHER_ROOT / "sources.yml"
README = WEATHER_ROOT / "README.md"
CONTRACTS = DOC_ROOT / "dbt_contracts.md"

NEW_GOLD_MODELS = {
    "gold_weather_forecast_completeness_by_admin_dong_hourly": {
        "grain": "admin_dong_code × forecast_at",
        "marker": "weather_new_gold_product",
    },
    "gold_weather_forecast_issue_cycle_coverage_daily": {
        "grain": "issued_at × forecast_date",
        "marker": "weather_new_gold_product",
    },
    "gold_weather_x_culture_activity_daily": {
        "grain": "admin_dong_code × forecast_date",
        "marker": "weather_new_gold_product",
    },
    "gold_weather_x_transit_hourly": {
        "grain": "admin_dong_code × hour_at",
        "marker": "weather_new_gold_product",
    },
    "gold_weather_x_commerce_business_exposure_daily": {
        "grain": "admin_dong_code × forecast_date",
        "marker": "weather_new_gold_product",
    },
}

CORE8 = ("TMP", "REH", "WSD", "POP", "SKY", "PTY", "PCP", "SNO")

REQUIRED_SINGULAR_TESTS = {
    "assert_gold_weather_forecast_completeness_by_admin_dong_hourly_grain_unique.sql",
    "assert_gold_weather_forecast_completeness_by_admin_dong_hourly_reconciles.sql",
    "assert_gold_weather_forecast_issue_cycle_coverage_daily_grain_unique.sql",
    "assert_gold_weather_forecast_issue_cycle_coverage_daily_bounds.sql",
    "assert_gold_weather_forecast_issue_cycle_coverage_daily_issue_slots_preserved.sql",
    "assert_gold_weather_forecast_issue_cycle_coverage_daily_reconciles_expected_cells.sql",
    "assert_gold_weather_x_culture_activity_daily_grain_unique.sql",
    "assert_gold_weather_x_culture_activity_daily_weather_anchor_preserved.sql",
    "assert_gold_weather_x_culture_activity_daily_present_zero_absent_null.sql",
    "assert_gold_weather_x_transit_hourly_grain_unique.sql",
    "assert_gold_weather_x_transit_hourly_weather_anchor_preserved.sql",
    "assert_gold_weather_x_transit_hourly_present_zero_absent_null.sql",
    "assert_gold_weather_x_commerce_business_exposure_daily_grain_unique.sql",
    "assert_gold_weather_x_commerce_business_exposure_daily_weather_anchor_preserved.sql",
    "assert_gold_weather_x_commerce_business_exposure_daily_no_hindsight.sql",
}


def _yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _models():
    return {item["name"]: item for item in _yaml(GOLD_YML)["models"]}


def _sources():
    return {item["name"]: item for item in _yaml(SOURCES_YML)["sources"]}


def _sql(model_name):
    return (GOLD_ROOT / f"{model_name}.sql").read_text(encoding="utf-8")


def test_new_weather_gold_model_contracts_are_exact_and_separate():
    models = _models()
    new_marked = {
        name: model["config"]["meta"]["weather_new_gold_product"]
        for name, model in models.items()
        if model.get("config", {}).get("meta", {}).get("weather_new_gold_product") is True
    }

    assert set(new_marked) == set(NEW_GOLD_MODELS)
    assert all(value is True for value in new_marked.values())

    for name, expectation in NEW_GOLD_MODELS.items():
        meta = models[name]["config"]["meta"]
        assert "public_gold" not in meta
        assert meta["grain"] == expectation["grain"]
        assert meta["anchor_universe"]
        assert meta["row_meaning"]
        assert (GOLD_ROOT / f"{name}.sql").exists()

    # The superseded 7-normal-Gold WIP must not leave metadata on existing models.
    assert not any(
        "quality_gold" in model.get("config", {}).get("meta", {})
        for name, model in models.items()
        if name not in NEW_GOLD_MODELS
    )


def test_sources_are_weather_owned_and_physical_contract_only():
    sources = _sources()
    expected = {
        "culture_gold": ("culture", "gold_culture_activity_by_dong"),
        "transit_gold": ("transit", "gold_transit_dong_hourly"),
        "commerce_gold": ("commerce", "gold_license_dong_summary"),
    }

    for source_name, (schema, table_name) in expected.items():
        source = sources[source_name]
        assert source["database"] == "{{ target.database }}"
        assert source["schema"] == schema
        assert [table["name"] for table in source["tables"]] == [table_name]
        assert "freshness" not in source
        assert "tests" not in source["tables"][0]


def test_quality_sql_locks_core8_denominators_and_lineage():
    completeness = _sql("gold_weather_forecast_completeness_by_admin_dong_hourly")
    issue = _sql("gold_weather_forecast_issue_cycle_coverage_daily")

    for category in CORE8:
        assert f"'{category}'" in completeness
        assert f"'{category}'" in issue

    assert "ref('gold_weather_forecast_by_admin_dong')" in completeness
    assert "forecast_at" in completeness
    assert "observed_core_category_count" in completeness
    assert "expected_core_category_count" in completeness
    assert "missing_core_category_count" in completeness
    assert "weather_collected_at_max" in completeness
    assert "weather_published_at_max" in completeness

    assert "ref('silver_kma_vilage_fcst_grid')" in issue
    assert "ref('bridge_weather_admin_dong_grid')" in issue
    assert "bridge_version" in issue
    assert "weather_admin_dong_grid_bridge_v1" in issue
    assert "canonical_join_eligible" in issue
    assert "mapped_admin_dong_count" in issue
    assert "426" in issue
    assert "mapped_admin_universe" in issue
    assert "bridge_summary" in issue
    assert "observed_cell_keys" in issue
    assert "bridge_contract_mismatch" in issue
    assert "where expected_agg.mapped_admin_dong_count = 425" not in issue.lower()
    assert "expected_cell_count" in issue
    assert "observed_cell_count" in issue
    assert "missing_cell_count" in issue
    assert "native grid count" not in issue.lower()
    assert "accuracy" not in issue.lower()
    assert "schedule adherence" not in issue.lower()


def test_cross_domain_sql_locks_presence_asof_no_hindsight_semantics():
    culture = _sql("gold_weather_x_culture_activity_daily")
    transit = _sql("gold_weather_x_transit_hourly")
    commerce = _sql("gold_weather_x_commerce_business_exposure_daily")

    assert "source('culture_gold', 'gold_culture_activity_by_dong')" in culture
    assert "culture_observation_present" in culture
    assert "external_freshness_status" in culture
    assert "not_exposed_by_upstream_gold" in culture
    assert "coalesce(culture" not in culture.lower()

    assert "source('transit_gold', 'gold_transit_dong_hourly')" in transit
    for presence in (
        "transit_observation_present",
        "bus_observation_present",
        "subway_observation_present",
        "parking_observation_present",
    ):
        assert presence in transit
    assert "not_exposed_by_upstream_gold" in transit
    assert "coalesce(transit" not in transit.lower()

    assert "source('commerce_gold', 'gold_license_dong_summary')" in commerce
    assert "commerce_observation_present" in commerce
    assert "commerce_latest_collected_at" in commerce
    assert "date(commerce.latest_collected_at) <= weather.forecast_date" in commerce
    assert "causal" not in commerce.lower()
    assert "loss" not in commerce.lower()


def test_docs_and_singular_tests_cover_required_semantics():
    readme = README.read_text(encoding="utf-8")
    contracts = CONTRACTS.read_text(encoding="utf-8")
    combined_docs = readme + "\n" + contracts

    for name, expectation in NEW_GOLD_MODELS.items():
        assert name in combined_docs
        assert expectation["grain"] in combined_docs

    for phrase in (
        "weather_new_gold_product",
        "gold_weather_forecast_by_admin_dong remains the only Weather published producer",
        "core8 TMP, REH, WSD, POP, SKY, PTY, PCP, SNO",
        "Entirely absent forecast slots are out of scope",
        "not_exposed_by_upstream_gold",
        "sparse subway",
        "parking null risk",
        "no hindsight",
        "not forecast accuracy",
        "not official schedule adherence",
    ):
        assert phrase in combined_docs

    existing_tests = {path.name for path in TEST_ROOT.glob("assert_gold_weather_*.sql")}
    assert REQUIRED_SINGULAR_TESTS <= existing_tests

    for test_name in REQUIRED_SINGULAR_TESTS:
        text = (TEST_ROOT / test_name).read_text(encoding="utf-8")
        if test_name == "assert_gold_weather_forecast_issue_cycle_coverage_daily_bounds.sql":
            assert "observed_cell_count > expected_cell_count" in text
            assert "missing_cell_count < 0" in text
            assert "issue_cycle_coverage_ratio > 1" in text
        else:
            assert "missing_context" in text or "except" in text.lower() or "full outer join" in text.lower()

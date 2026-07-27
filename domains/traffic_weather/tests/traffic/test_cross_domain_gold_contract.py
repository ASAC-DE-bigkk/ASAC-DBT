from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"
GOLD_TEST_DIR = PROJECT_ROOT / "tests" / "traffic" / "transform" / "gold"
TRAFFIC_DOCS_DIR = PROJECT_ROOT / "docs" / "traffic"
TRAFFIC_SOURCES_PATH = PROJECT_ROOT / "models" / "traffic" / "sources.yml"
TRAFFIC_EXTERNAL_SNAPSHOT_MACRO_PATH = (
    PROJECT_ROOT / "macros" / "traffic" / "traffic_external_snapshot.sql"
)
WEATHER_MODEL_PATH = GOLD_DIR / "gold_traffic_incident_x_weather_current_hourly.sql"
CITYDATA_MODEL_PATH = (
    GOLD_DIR / "gold_traffic_incident_x_citydata_crowding_current_hourly.sql"
)
CITYDATA_RECONCILIATION_TEST_PATH = (
    GOLD_TEST_DIR
    / "assert_gold_traffic_incident_x_citydata_crowding_current_hourly_latest_per_area_reconciles.sql"
)
CITYDATA_SNAPSHOT_LINEAGE_TEST_PATH = (
    GOLD_TEST_DIR
    / "assert_gold_traffic_incident_x_citydata_crowding_current_hourly_snapshot_lineage.sql"
)
GOLD_METADATA_PATH = GOLD_DIR / "_gold.yml"


def _compact(text: str) -> str:
    return " ".join(text.lower().split())


def _gold_models() -> dict[str, dict]:
    models: dict[str, dict] = {}
    for yml_path in sorted(GOLD_DIR.glob("*.yml")):
        document = yaml.safe_load(yml_path.read_text(encoding="utf-8")) or {}
        for model in document.get("models", []):
            models[model["name"]] = model
    return models


def test_design_and_implementation_plan_exist_for_issue_234() -> None:
    specs = list(
        (TRAFFIC_DOCS_DIR / "superpowers" / "specs").glob(
            "2026-07-16-traffic-cross-domain-gold*.md"
        )
    )
    plans = list(
        (TRAFFIC_DOCS_DIR / "superpowers" / "plans").glob(
            "2026-07-16-traffic-cross-domain-gold*.md"
        )
    )

    assert specs, "missing issue #234 design spec"
    assert plans, "missing issue #234 implementation plan"
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(specs + plans)
    )
    assert "gold_traffic_incident_x_weather_current_hourly" in combined
    assert "gold_traffic_incident_x_citydata_crowding_current_hourly" in combined
    assert "issued_at <= traffic.status_observed_at" in combined
    assert "do not mark either new model with `traffic_quality_product: true`" in combined


def test_cross_domain_gold_metadata_locks_exact_two_models_and_grains() -> None:
    models = _gold_models()
    expected = {
        "gold_traffic_incident_x_weather_current_hourly",
        "gold_traffic_incident_x_citydata_crowding_current_hourly",
    }
    actual = {
        name
        for name, model in models.items()
        if model.get("config", {}).get("meta", {}).get("cross_domain_gold") is True
    }

    assert actual == expected
    for name in expected:
        meta = models[name]["config"]["meta"]
        assert meta.get("traffic_quality_product") is False
        assert "admin_dong_code" in meta["grain"]
        assert "hour_at" in meta["grain"]

    citydata_model = models[
        "gold_traffic_incident_x_citydata_crowding_current_hourly"
    ]
    assert citydata_model["config"]["meta"]["reconciliation_tests"] == [
        "assert_gold_traffic_incident_x_citydata_crowding_current_hourly_latest_per_area_reconciles",
        "assert_gold_traffic_incident_x_citydata_crowding_current_hourly_snapshot_lineage",
    ]
    columns = {column["name"]: column for column in citydata_model["columns"]}
    assert columns["citydata_crowding_snapshot_id"]["tests"] == [
        {
            "not_null": {
                "config": {"tags": ["traffic_gold_gate"]},
            }
        }
    ]


def test_weather_cross_domain_gold_contract() -> None:
    sql = WEATHER_MODEL_PATH.read_text(encoding="utf-8")
    compact_sql = _compact(sql)

    assert "ref('gold_traffic_incident_current_by_admin_dong_hourly')" in sql
    assert "ref('asac_seoul', 'gold_weather_forecast_by_admin_dong')" in sql
    assert "traffic.admin_dong_code = weather.admin_dong_code" in compact_sql
    assert (
        "cast(date_trunc('hour', weather.forecast_at) as timestamp(6)) = traffic.hour_at"
        in compact_sql
    )
    assert "weather.issued_at <= traffic.status_observed_at" in compact_sql
    assert "lower(weather.category) in ('tmp', 'pop', 'reh', 'wsd', 'sky', 'pty')" in compact_sql
    assert "cast(weather.value_num as double) as value_num" in compact_sql
    assert "cast(weather.qualitative_code as varchar) as qualitative_code" in compact_sql
    assert "count(distinct category) as weather_category_coverage_count" in compact_sql
    assert "max(issued_at) as weather_latest_issued_at" in compact_sql
    assert "max(collected_at) as weather_latest_collected_at" in compact_sql
    assert "max(published_at) as weather_latest_published_at" in compact_sql
    assert "cast(weather.published_at as timestamp(6)) as published_at" in compact_sql
    assert "qualitative_code end) = '0' then false" in compact_sql
    assert (
        "qualitative_code end) in ('1', '2', '3', '4', '5', '6', '7') then true"
        in compact_sql
    )
    assert "coalesce(weather_hourly." not in compact_sql
    assert "traffic.incident_count" in compact_sql
    assert "traffic.has_incident" in compact_sql
    assert "traffic.quality_state" in compact_sql


def test_citydata_source_contract_lives_in_traffic_sources() -> None:
    document = yaml.safe_load(TRAFFIC_SOURCES_PATH.read_text(encoding="utf-8")) or {}
    sources = {source["name"]: source for source in document.get("sources", [])}

    assert "traffic_citydata_gold" in sources
    citydata = sources["traffic_citydata_gold"]
    assert citydata["schema"] == "{{ env_var('SEOUL_CITYDATA_SCHEMA', 'seoul_citydata') }}"
    tables = {table["name"]: table for table in citydata["tables"]}
    table = tables["gold_citydata_ppltn_by_time"]
    assert table["identifier"] == "gold_citydata_ppltn_by_time"
    column_defs = {column["name"]: column for column in table["columns"]}
    columns = {column["name"] for column in table["columns"]}
    assert {
        "event_at",
        "area_cd",
        "admin_dong_code",
        "avg_ppltn",
        "collected_at",
    }.issubset(columns)
    assert "tests" not in column_defs["admin_dong_code"]


def test_citydata_external_snapshot_macro_is_fail_closed_and_pinned() -> None:
    macro_sql = TRAFFIC_EXTERNAL_SNAPSHOT_MACRO_PATH.read_text(encoding="utf-8")

    assert "var('traffic_citydata_crowding_snapshot_id', none)" in macro_sql
    assert (
        "{%- if snapshot_id is none and not execute -%}\n"
        "    {{ return(0) }}\n"
        "  {%- endif -%}"
    ) in macro_sql
    assert "snapshot_id is not integer or snapshot_id <= 0" in macro_sql
    assert "snapshot_id is not number" not in macro_sql
    assert "exceptions.raise_compiler_error" in macro_sql
    assert "FOR VERSION AS OF" in macro_sql
    assert "source('traffic_citydata_gold', 'gold_citydata_ppltn_by_time')" in macro_sql


def test_citydata_cross_domain_gold_contract() -> None:
    sql = CITYDATA_MODEL_PATH.read_text(encoding="utf-8")
    compact_sql = _compact(sql)
    reconcile_sql = CITYDATA_RECONCILIATION_TEST_PATH.read_text(encoding="utf-8")

    assert "ref('gold_traffic_incident_current_by_admin_dong_hourly')" in sql
    assert "traffic_citydata_crowding_source_at_snapshot()" in sql
    assert "traffic_citydata_crowding_source_at_snapshot()" in reconcile_sql
    assert (
        "cast({{ traffic_citydata_crowding_snapshot_id() }} as bigint) "
        "as citydata_crowding_snapshot_id"
    ) in compact_sql
    assert "source('traffic_citydata_gold', 'gold_citydata_ppltn_by_time')" not in sql
    assert (
        "source('traffic_citydata_gold', 'gold_citydata_ppltn_by_time')"
        not in reconcile_sql
    )
    assert "traffic.admin_dong_code = crowding.admin_dong_code" in compact_sql
    assert (
        "cast(date_trunc('hour', crowding.event_at) as timestamp(6)) = traffic.hour_at"
        in compact_sql
    )
    assert "row_number() over (" in compact_sql
    assert "partition by admin_dong_code, hour_at, area_cd" in compact_sql
    assert "order by event_at desc nulls last, collected_at desc nulls last" in compact_sql
    assert "count(*) as monitored_place_count" in compact_sql
    assert "avg(avg_ppltn) as avg_place_avg_ppltn" in compact_sql
    assert "max(avg_ppltn) as peak_place_avg_ppltn" in compact_sql
    assert "sum(avg_ppltn)" not in compact_sql
    assert "resident" not in compact_sql
    assert "traffic.incident_count" in compact_sql
    assert "traffic.has_incident" in compact_sql
    assert "traffic.quality_state" in compact_sql


def test_citydata_cross_domain_gold_snapshot_lineage_contract() -> None:
    assert CITYDATA_SNAPSHOT_LINEAGE_TEST_PATH.is_file()
    lineage_sql = _compact(
        CITYDATA_SNAPSHOT_LINEAGE_TEST_PATH.read_text(encoding="utf-8")
    )

    assert "select product_row_id" in lineage_sql
    assert (
        "from {{ ref('gold_traffic_incident_x_citydata_crowding_current_hourly') }}"
        in lineage_sql
    )
    assert (
        "where citydata_crowding_snapshot_id is distinct from "
        "cast({{ traffic_citydata_crowding_snapshot_id() }} as bigint)"
    ) in lineage_sql

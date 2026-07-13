import hashlib
from pathlib import Path

import yaml


WEATHER_DIR = Path(__file__).parents[1]

MODEL_NAME = "gold_weather_forecast_by_admin_dong"
BRIDGE_VERSION = "weather_admin_dong_grid_bridge_v1"
EXPECTED_COLUMNS = [
    "product_row_id",
    "admin_dong_code",
    "forecast_at",
    "category",
    "admin_dong",
    "gu_code",
    "gu",
    "admin_dong_revision_date",
    "bridge_version",
    "nx",
    "ny",
    "source_grid_place_id",
    "issued_at",
    "collected_at",
    "published_at",
    "fcst_value_raw",
    "fcst_value_num",
    "value_representation",
    "value_num",
    "value_lower_bound",
    "value_upper_bound",
    "qualitative_code",
    "forecast_lead_hours",
    "source_id",
    "dag_run_id",
    "raw_object_key",
    "request_id",
]
NAMED_TESTS = {
    "assert_gold_weather_forecast_by_admin_dong_admin_stamp_exact",
    "assert_gold_weather_forecast_by_admin_dong_admin_revision_exact",
    "assert_gold_weather_forecast_by_admin_dong_admin_join_reconciles",
}
DATA_TESTS = NAMED_TESTS | {
    "assert_gold_weather_forecast_by_admin_dong_grain_unique",
    "assert_gold_weather_forecast_by_admin_dong_product_row_id_reproducible",
    "assert_gold_weather_forecast_by_admin_dong_latest_grid_record",
    "assert_gold_weather_forecast_by_admin_dong_bridge_exclusions_reconcile",
    "assert_gold_weather_forecast_by_admin_dong_repair_reconciles",
    "assert_gold_weather_forecast_by_admin_dong_repair_no_downgrade",
}


def read(relative_path: str) -> str:
    return (WEATHER_DIR / relative_path).read_text(encoding="utf-8")


def compact(text: str) -> str:
    return " ".join(text.lower().split())


def model_contract() -> dict:
    schema = yaml.safe_load(read("models/schema.yml"))
    return next(model for model in schema["models"] if model["name"] == MODEL_NAME)


def test_legacy_compatibility_sql_remains_byte_identical():
    expected = {
        "models/silver/silver_kma_vilage_fcst.sql": (
            "890e1f938ffe47f010f023aff24e579a99c93a5184b79a7b05bde75ba83b18cb"
        ),
        "models/silver/silver_weather_forecast_by_admin_dong.sql": (
            "66dcd5b4a3fa50f66ff74d295ff007c53de4bb98a00242a331731a5585f7bbbb"
        ),
        "models/gold/dim_weather_place.sql": (
            "eba54dedea0fd686d346b1cbcb6465651fc2d7503ec3dcd9fb64c5fa4698157f"
        ),
        "models/gold/gold_weather_forecast_by_place.sql": (
            "31465a74b03bb5058e8951cfb5922d99c23ffe3519fc2c4728712c7678dfda87"
        ),
    }
    for relative_path, expected_hash in expected.items():
        payload = (WEATHER_DIR / relative_path).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(payload).hexdigest() == expected_hash


def test_repair_inputs_and_shared_dev_guard_fail_closed():
    macro = compact(read("macros/weather_w2_contract.sql"))
    for token in (
        "weather_w2_repair_mode",
        "bounded_reconcile",
        "weather_w2_repair_start_at",
        "weather_w2_publishable_cutoff_at",
        "weather_w2_bridge_version",
        BRIDGE_VERSION,
        "timestamp(6)",
        "24",
        "flags.full_refresh",
        "target.name",
        "iceberg_dev",
        "weather",
        "exceptions.raise_compiler_error",
    ):
        assert token in macro
    assert "target.name != 'dev'" in macro or "target.name == 'dev'" in macro
    assert "start" in macro and "cutoff" in macro

    w1_macro = compact(read("macros/weather_v2_contract.sql"))
    assert "bounded_isolated_smoke" in w1_macro
    assert "weather_w2_shared_dev_build_allowed" in w1_macro
    assert "flags.full_refresh" in w1_macro


def test_repair_evidence_ranks_latest_state_then_checks_manifest_and_bronze():
    macro = compact(read("macros/weather_w2_contract.sql"))
    for token in (
        "macro weather_w2_assert_repair_evidence",
        "row_number() over",
        "event_at desc",
        "success",
        "is_publishable",
        "expected_rows",
        "actual_rows",
        "expected_raw_objects",
        "actual_raw_objects",
        "count(distinct raw_object_key)",
        "bronze_kma_vilage_fcst",
    ):
        assert token in macro
    ranked = macro.index("row_number() over")
    publishable_filter = macro.index("is_publishable", ranked)
    assert ranked < publishable_filter


def test_w1_keeps_normal_lookback_and_adds_bounded_repair_no_downgrade():
    observation = compact(read("models/silver/silver_kma_vilage_fcst_observation.sql"))
    grid = compact(read("models/silver/silver_kma_vilage_fcst_grid.sql"))

    assert "weather_w1_lookback_minutes()" in observation
    assert "weather_w2_is_repair" in observation
    assert "weather_w2_assert_repair_evidence" in observation
    assert "weather_w2_publishable_cutoff_at" in observation
    assert "manifest_event_at_utc" in observation

    assert "weather_w1_lookback_minutes()" in grid
    assert "weather_w2_is_repair" in grid
    assert "published_at" in grid
    assert "weather_w2_grid_winner_is_newer" in grid
    assert "not exists" in grid


def test_custom_strategy_is_one_atomic_merge_with_bounded_delete_and_no_downgrade():
    macro = compact(read("macros/weather_w2_contract.sql"))
    assert "macro get_incremental_weather_w2_reconcile_sql" in macro
    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]
    assert strategy.count("merge into") == 1
    assert "delete from" not in strategy
    assert "__w2_delete" in strategy
    assert "published_at" in strategy
    assert "weather_w2_repair_start_at" in strategy
    assert "weather_w2_publishable_cutoff_at" in strategy
    assert "is distinct from" in strategy
    assert "weather_w2_gold_winner_is_not_older" in strategy
    assert "count(*)" in strategy
    assert "group by admin_dong_code, forecast_at, category" in strategy
    assert "when matched" in strategy
    delete_clause = strategy.index("then delete")
    update_clause = strategy.index("then update")
    insert_clause = strategy.index("then insert")
    assert delete_clause < update_clause < insert_clause


def test_gold_sql_has_exact_refs_grain_winner_row_id_and_latest_restamp():
    sql = compact(read(f"models/gold/{MODEL_NAME}.sql"))
    for token in (
        "materialized='incremental'",
        "incremental_strategy='weather_w2_reconcile'",
        "unique_key=['admin_dong_code', 'forecast_at', 'category']",
        "on_schema_change='fail'",
        "views_enabled=false",
        "full_refresh=false",
        "ref('silver_kma_vilage_fcst_grid')",
        "ref('bridge_weather_admin_dong_grid')",
        "ref('asac_axes', 'dim_admin_dong')",
        BRIDGE_VERSION,
        "cast(canonical.revision_date as date)",
        "to_iso8601(cast(forecast_at as timestamp(6)))",
        "from {{ this }}",
        "is distinct from",
    ):
        assert token in sql
    required_prefix = (
        "issued_at desc, collected_at desc, raw_object_key desc, request_id desc"
    )
    assert required_prefix in sql
    for column in EXPECTED_COLUMNS:
        assert column in sql


def test_public_contract_declares_exact_schema_latest_axis_and_truthful_status():
    model = model_contract()
    columns = model["columns"]
    assert [column["name"] for column in columns] == EXPECTED_COLUMNS
    assert all(column.get("description") and column.get("data_type") for column in columns)
    assert all("meta" in column.get("config", {}) for column in columns)

    public = model["config"]["meta"]["public_gold"]
    assert public["primary_key"] == ["product_row_id"]
    assert public["column_order"] == EXPECTED_COLUMNS
    assert public["visibility"] == "published_producer"
    assert public["contract_status"] == "dev_pending"
    assert public["exposure_status"] == "none_no_live_consumer"
    assert public["metrics"] == {}
    assert public["time"]["canonical_timezone"] == "Asia/Seoul"
    assert set(public["time"]["roles"]) == {
        "forecast_at",
        "issued_at",
        "collected_at",
        "published_at",
    }
    space = public["space"]
    assert space["canonical_key"] == "admin_dong_code"
    assert space["revision_field"] == "admin_dong_revision_date"
    assert space["stamp_fields"] == [
        "admin_dong_code",
        "admin_dong",
        "gu_code",
        "gu",
        "admin_dong_revision_date",
    ]
    assert set(space["reconciliation_tests"]) == NAMED_TESTS - {
        "assert_gold_weather_forecast_by_admin_dong_admin_join_reconciles"
    }
    assert (
        public["joins"]["admin_dong_dimension"]["reconciliation_test"]
        == "assert_gold_weather_forecast_by_admin_dong_admin_join_reconciles"
    )
    assert set(public["quality"]["state_fields"]["value_representation"]["allowed_values"]) == {
        "explicit_none",
        "quantitative_exact",
        "quantitative_range",
        "bare_numeric",
        "qualitative_code",
        "missing",
        "unparseable",
    }


def test_named_and_data_tests_exist_with_direct_dependency_hints():
    for test_name in DATA_TESTS:
        sql = read(f"tests/{test_name}.sql")
        first_lines = "\n".join(sql.splitlines()[:5])
        assert "-- depends_on:" in first_lines
        assert f"ref('{MODEL_NAME}')" in first_lines
        assert sql.strip()


def test_contract_commands_and_operating_docs_target_new_public_gold():
    contract_doc = read("contracts/docs/public-gold-ai-contract-v1.md")
    operating_doc = read("docs/dbt_contracts.md")
    assert contract_doc.count(f"--resource {MODEL_NAME}") >= 3
    assert "latest canonical" in contract_doc.lower() or "최신 canonical" in contract_doc
    assert "425" in contract_doc
    for token in (
        "weather_w2_repair_mode",
        "weather_w2_repair_start_at",
        "weather_w2_publishable_cutoff_at",
        "weather_w2_bridge_version",
        "bounded_reconcile",
        MODEL_NAME,
        "A1",
    ):
        assert token in operating_doc

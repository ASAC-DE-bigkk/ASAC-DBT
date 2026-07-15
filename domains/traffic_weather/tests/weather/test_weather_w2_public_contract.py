from __future__ import annotations

from tests.weather.w2_contract_fixtures import (
    BRIDGE_VERSION,
    CANONICAL_REVISION_DATE,
    DATA_TESTS,
    EXPECTED_COLUMNS,
    MODEL_NAME,
    NAMED_TESTS,
    PROJECT_ROOT,
    WEATHER_OPERATING_DOC,
    W2_GOLD_MODEL,
    W2_GOLD_SCHEMA,
    W2_MACRO,
    W2_PUBLIC_CONTRACT_DOC,
    compact,
    data_test_path,
    model_contract,
    read,
)


def test_gold_sql_has_exact_refs_grain_winner_row_id_and_approved_revision_snapshot() -> (
    None
):
    sql = compact(read(W2_GOLD_MODEL))
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
        "date '{{ canonical_contract['revision_date'] }}'",
        "validated_canonical_contract",
        "canonical_retained_rows",
        "to_iso8601(cast(forecast_at as timestamp(6)))",
        "from {{ this }}",
    ):
        assert token in sql
    required_prefix = (
        "issued_at desc, collected_at desc, raw_object_key desc, request_id desc"
    )
    assert required_prefix in sql
    expected_row_id = (
        "concat(admin_dong_code, '|', "
        "to_iso8601(cast(forecast_at as timestamp(6))), '|', category)"
    )
    assert expected_row_id in sql
    assert "select *" not in sql
    projected_columns = f"select {', '.join(EXPECTED_COLUMNS)}"
    assert f"{projected_columns} from product_rows" in sql
    assert sql.endswith(f"{projected_columns} from canonical_contract_failure_rows")


def test_gold_repair_expected_set_is_correlated_to_latest_publishable_manifest_anchors() -> (
    None
):
    macro = compact(read(W2_MACRO))
    model = compact(read(W2_GOLD_MODEL))

    anchor_start = macro.index("macro weather_w2_latest_publishable_anchors_sql")
    anchor_macro = macro[anchor_start : macro.index("endmacro", anchor_start)]
    for token in (
        "collection_run_manifest",
        "event_at <= cutoff_at",
        "row_number() over",
        "partition by source_id, dag_run_id",
        "where manifest_row_num = 1",
        "manifest_status = 'success'",
        "is_publishable",
        "manifest_published_at >= start_at",
        "manifest_published_at <= cutoff_at",
    ):
        assert token in anchor_macro

    source_guard = macro[macro.index("macro weather_w2_assert_gold_source_contract") :]
    for sql in (model, source_guard):
        assert "weather_w2_latest_publishable_anchors_sql" in sql
        assert "eligible_manifest_anchors" in sql
        assert "anchor.anchor_source_id" in sql
        assert "anchor.anchor_dag_run_id" in sql
        assert "grid.selected_dag_run_id" in sql


def test_gold_source_guard_covers_latest_canonical_and_initial_ctas_contract() -> None:
    macro = compact(read(W2_MACRO))
    source_guard_start = macro.index("macro weather_w2_assert_gold_source_contract")
    source_guard = macro[
        source_guard_start : macro.index("endmacro", source_guard_start)
    ]

    for token in (
        "canonical_count",
        "bridge_canonical_count",
        "canonical_contract['bridge_count']",
        "canonical_contract['canonical_count']",
        "canonical_contract['mapped_canonical_count']",
        "canonical_contract['revision_date']",
        "canonical_orphan_count",
        "repair_expected_count",
        "repair_null_contract_count",
        "repair_duplicate_count",
        "row_number() over",
        "where product_row_num = 1",
        "admin_dong is null",
        "gu_code is null",
        "gu is null",
        "admin_dong_revision_date is null",
        "bridge_version is null",
        "value_representation is null",
        "forecast_lead_hours is null",
        "source_id is null",
    ):
        assert token in source_guard

    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]
    for token in (
        "__w2_force_replace",
        "from {{ temp_relation }} as dbt_internal_anchor_source",
        "dbt_internal_current_anchor.anchor_source_id is null",
        "dbt_internal_current.source_id = dbt_internal_current_anchor.anchor_source_id",
        "dbt_internal_current.dag_run_id = dbt_internal_current_anchor.anchor_dag_run_id",
        "admin_dong is null",
        "gu_code is null",
        "gu is null",
        "admin_dong_revision_date is null",
        "bridge_version is null",
        "value_representation is null",
        "forecast_lead_hours is null",
        "source_id is null",
    ):
        assert token in strategy
    assert "or dbt_internal_source.__w2_force_replace" in strategy


def test_public_contract_declares_exact_schema_approved_axis_and_truthful_status() -> (
    None
):
    model = model_contract()
    columns = model["columns"]
    assert [column["name"] for column in columns] == EXPECTED_COLUMNS
    assert all(
        column.get("description") and column.get("data_type") for column in columns
    )
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
    assert space["approved_revision_date"] == CANONICAL_REVISION_DATE
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
    assert set(
        public["quality"]["state_fields"]["value_representation"]["allowed_values"]
    ) == {
        "explicit_none",
        "quantitative_exact",
        "quantitative_range",
        "bare_numeric",
        "qualitative_code",
        "missing",
        "unparseable",
    }


def test_named_and_data_tests_exist_with_direct_dependency_hints() -> None:
    for test_name in DATA_TESTS:
        sql = read(data_test_path(test_name))
        first_lines = "\n".join(sql.splitlines()[:5])
        assert "-- depends_on:" in first_lines
        assert f"ref('{MODEL_NAME}')" in first_lines
        assert sql.strip()


def test_contract_commands_and_operating_docs_target_new_public_gold() -> None:
    contract_doc = read(W2_PUBLIC_CONTRACT_DOC)
    operating_doc = read(WEATHER_OPERATING_DOC)
    schema_doc = read(W2_GOLD_SCHEMA)
    assert contract_doc.count(f"--resource {MODEL_NAME}") >= 3
    for document in (contract_doc, operating_doc, schema_doc):
        assert CANONICAL_REVISION_DATE in document
        assert "427" in document
        assert "426" in document
        assert "425" in document
    for token in (
        "weather_w2_repair_mode",
        "weather_w2_repair_start_at",
        "weather_w2_publishable_cutoff_at",
        "weather_w2_bridge_version",
        "weather_w2_canonical_revision_date",
        "bounded_reconcile",
        MODEL_NAME,
        "A1",
    ):
        assert token in operating_doc
    for document in (contract_doc, operating_doc):
        assert "normal Gold" in document
        assert "weather_w2_canonical_revision_date=2025-04-01" in document
        assert "scoped shared DEV smoke" in document
        assert "formal approved-dev" in document
    assert "DAG run id" in operating_doc
    assert "NOT_RUN" in operating_doc
    assert not (
        PROJECT_ROOT / "docs/superpowers/plans/2026-07-13-weather-canonical-public-gold.md"
    ).exists()
    assert not (
        PROJECT_ROOT
        / "docs/superpowers/specs/2026-07-13-weather-canonical-public-gold-design.md"
    ).exists()
    assert "desired temp" in operating_doc.lower()
    assert "writer" in operating_doc.lower()

from __future__ import annotations

from tests.weather.w2_contract_fixtures import (
    BRIDGE_VERSION,
    CANONICAL_DATA_TESTS,
    CANONICAL_REVISION_DATE,
    EXPECTED_BRIDGE_V1_COUNT,
    EXPECTED_CANONICAL_COUNT,
    EXPECTED_MAPPED_CANONICAL_COUNT,
    W1_BRIDGE_MODEL,
    W1_GRID_MODEL,
    W1_GRID_RECONCILIATION_TEST,
    W1_MACRO,
    W1_OBSERVATION_MODEL,
    W1_OBSERVATION_RECONCILIATION_TEST,
    W2_DATA_TESTS,
    W2_GOLD_MODEL,
    W2_LINEAGE_WORKSET_MODEL,
    W2_MACRO,
    W2_REPAIR_RECONCILIATION_TEST,
    W2_REPAIR_WINDOW_EXTRA_TEST,
    W2_REPAIR_WINDOW_LINEAGE_TEST,
    compact,
    read,
)


def test_repair_inputs_and_shared_dev_guard_fail_closed() -> None:
    raw_macro = read(W2_MACRO)
    macro = compact(raw_macro)
    for token in (
        "weather_w2_repair_mode",
        "bounded_reconcile",
        "weather_w2_repair_start_at",
        "weather_w2_publishable_cutoff_at",
        "weather_w2_bridge_version",
        "weather_w2_canonical_revision_date",
        BRIDGE_VERSION,
        CANONICAL_REVISION_DATE,
        "timestamp(6)",
        "asia/seoul",
        "24",
        "flags.full_refresh",
        "target.name",
        "iceberg_dev",
        "weather",
        "exceptions.raise_compiler_error",
    ):
        assert token in macro
    assert "target.name != 'dev'" in macro or "target.name == 'dev'" in macro
    gold_guard = macro[
        macro.index("macro weather_w2_assert_gold_dev_target") : macro.index(
            "endmacro", macro.index("macro weather_w2_assert_gold_dev_target")
        )
    ]
    assert "if execute and (" in gold_guard
    for target_check in (
        "target.name != 'dev'",
        "target.database != 'iceberg_dev'",
        "weather_schema_name()",
    ):
        assert target_check in gold_guard
    assert "weather_w2_assert_gold_dev_target" in compact(read(W2_GOLD_MODEL))
    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]
    assert "weather_w2_assert_gold_dev_target" in strategy
    assert (
        "^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{6}$"
        in raw_macro
    )
    for condition in (
        "raw_start is none",
        "raw_cutoff is none",
        "raw_bridge_version is none",
        "raw_canonical_revision_date is none",
        "canonical_revision_date != approved_revision_date",
        "start_at > cutoff_at",
        "cutoff_at > start_at + interval '24' hour",
        "cast(current_timestamp at time zone 'asia/seoul' as timestamp(6)) as current_kst_at",
        "cutoff_at > current_kst_at",
        "target.database != 'iceberg_dev'",
        "weather_schema_name()",
    ):
        assert condition in macro
    assert "target.schema" not in raw_macro

    w1_macro = compact(read(W1_MACRO))
    assert "bounded_isolated_smoke" in w1_macro
    assert "weather_w2_shared_dev_build_allowed" in w1_macro
    assert "weather_w2_assert_repair_evidence" in w1_macro
    assert "flags.full_refresh" in w1_macro


def test_gold_repair_reconciliation_compacts_payload_before_winner_ranking() -> None:
    raw = read(W2_REPAIR_RECONCILIATION_TEST)
    compacted = compact(raw)
    ranked = raw[
        raw.index("ranked_grid_candidate_keys as") : raw.index(
            "winning_grid_candidate_keys as"
        )
    ]

    assert "ranked_grid_candidate_keys as" in raw
    assert "winning_grid_candidate_keys as" in raw
    assert "candidate_payload_hash" not in raw
    assert "sha256(" not in compacted
    assert "canonical_payload" in raw
    assert compacted.count("json_format(cast(row(") == 2
    assert "joined_candidates.*" not in ranked
    assert "from grid_candidates" in ranked
    assert "left join {{ ref('gold_weather_forecast_by_admin_dong') }} as actual" in raw
    assert "full outer join" not in compacted
    assert "weather_w2_gold_winner_is_not_older" in raw
    for field in (
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
    ):
        assert f"cast(candidate.{field} as" in compacted
        assert f"cast(actual.{field} as" in compacted

    extra_rows = compact(read(W2_REPAIR_WINDOW_EXTRA_TEST))
    assert "ranked_grid_candidate_keys as" in extra_rows
    assert "actual_window as" in extra_rows
    assert "unexpected_window_gold_row" in extra_rows
    assert "published_at as timestamp(6)) >= timestamp" in extra_rows

    lineage_raw = read(W2_REPAIR_WINDOW_LINEAGE_TEST)
    lineage = compact(lineage_raw)
    assert "weather_w2_lineage_run_bucket_count" in lineage
    assert "weather_w2_lineage_run_bucket_index" in lineage
    assert "weather_w2_observation_recovery_lineage_workset" in lineage
    assert "workset_for_window as" in lineage
    assert "selected_workset as" in lineage
    assert "run_query(" not in lineage
    assert "lineage_backed_products as" in lineage
    assert "repair_product_keys as" not in lineage
    assert "actual_repair_products as" not in lineage
    assert "forecast_lineage_not_backed_by_one_grid_row" in lineage
    assert "lineage_workset_window_missing" in lineage
    assert (
        "cast(lineage_run_bucket_ordinal as bigint) as lineage_run_bucket_ordinal"
        in lineage
    )
    assert "cast(nx as integer) as nx" in lineage
    assert "cast(raw_object_key as varchar) as raw_object_key" in lineage
    assert "mod(lineage_run_bucket_ordinal, {{ lineage_run_bucket_count }})" in lineage
    assert "lineage_payload" in lineage
    assert "json_format(cast(row(" in lineage
    assert "grid.source_id as varchar) = actual.source_id" in lineage
    assert "grid.selected_dag_run_id as varchar) = actual.dag_run_id" in lineage
    assert "grid.forecast_at as timestamp(6)) = actual.forecast_at" in lineage
    assert "grid.raw_object_key as varchar) = actual.raw_object_key" in lineage
    assert "is not distinct from actual." not in lineage
    assert "lineage_grid_payloads as" not in lineage
    assert "where cast(actual.published_at" not in lineage
    assert "actual.published_at >= timestamp" not in lineage
    assert "actual.published_at <= timestamp" not in lineage
    assert "all_grid_records as" not in lineage

    lineage_failure_query = lineage_raw[
        lineage_raw.rindex("select\n    actual.product_row_id,") : lineage_raw.rindex(
            "{% else %}"
        )
    ]
    assert "from selected_workset as actual" in lineage_failure_query
    assert "left join lineage_backed_products" in lineage_failure_query


def test_repair_lineage_workset_is_bounded_and_dev_only() -> None:
    workset = compact(read(W2_LINEAGE_WORKSET_MODEL))
    for token in (
        "materialized='table'",
        "alias='weather_w2_observation_recovery_lineage_workset'",
        "weather_w2_is_repair",
        "weather_w2_assert_gold_dev_target",
        "weather_w2_assert_repair_evidence",
        "weather_w2_bridge_version",
        "weather_w2_gold_winner_is_not_older",
        "repair_start_at",
        "repair_cutoff_at",
        "lineage_run_bucket_ordinal",
        "json_format(cast(row(",
    ):
        assert token in workset


def test_repair_evidence_ranks_latest_state_then_checks_manifest_and_bronze() -> None:
    macro = compact(read(W2_MACRO))
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
        "partition by cast(source_id as varchar), cast(dag_run_id as varchar)",
        "where manifest_row_num = 1",
        "manifest_published_at >= start_at",
        "manifest_published_at <= cutoff_at",
        "expected_rows = actual_rows",
        "expected_rows > 0",
        "expected_raw_objects = actual_raw_objects",
        "expected_raw_objects > 0",
        "anchor_count = 0",
        "bronze_row_count != actual_rows",
        "bronze_raw_object_count != actual_raw_objects",
        "manifest_ambiguous_ties",
        "having count(*) > 1",
        "ambiguous_state_count",
    ):
        assert token in macro
    cutoff_filter = macro.index("event_at <= cutoff_at")
    ranked = macro.index("row_number() over", cutoff_filter)
    latest_filter = macro.index("where manifest_row_num = 1", ranked)
    success_filter = macro.index("manifest_status = 'success'", latest_filter)
    publishable_filter = macro.index("is_publishable", latest_filter)
    assert cutoff_filter < ranked < latest_filter < success_filter
    assert latest_filter < publishable_filter


def test_observation_reconciliation_uses_explicit_trino_join_aliases() -> None:
    reconciliation = compact(read(W1_OBSERVATION_RECONCILIATION_TEST))

    for clause in (
        "from manifest as manifest_run",
        "left join source_actual as source_actual_run",
        "left join actual as actual_run",
        "on manifest_run.source_id = source_actual_run.source_id",
        "and manifest_run.dag_run_id = source_actual_run.dag_run_id",
        "on manifest_run.source_id = actual_run.source_id",
        "and manifest_run.dag_run_id = actual_run.dag_run_id",
        "manifest_run.dag_run_id",
    ):
        assert clause in reconciliation
    assert "using (source_id, dag_run_id)" not in reconciliation


def test_w1_keeps_normal_lookback_and_adds_bounded_repair_no_downgrade() -> None:
    observation = compact(read(W1_OBSERVATION_MODEL))
    grid_raw = read(W1_GRID_MODEL)
    grid = compact(grid_raw)
    grid_hints = "\n".join(grid_raw.splitlines()[:5])
    bridge_raw = read(W1_BRIDGE_MODEL)
    bridge_hints = "\n".join(bridge_raw.splitlines()[:5])

    assert (
        "-- depends_on: {{ ref('silver_kma_vilage_fcst_observation') }}" in grid_hints
    )
    assert (
        "-- depends_on: {{ ref('weather_admin_dong_grid_bridge_history') }}"
        in bridge_hints
    )
    assert "-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}" in bridge_hints
    assert "weather_w1_lookback_minutes()" in observation
    assert "weather_w2_is_repair" in observation
    assert "weather_w2_assert_repair_evidence" in observation
    assert "weather_w2_publishable_cutoff_at" in observation
    assert "manifest_event_at_utc" in observation
    assert "weather_w1_lookback_minutes()" in grid
    assert "weather_w2_is_repair" in grid
    assert "published_at" in grid
    assert "weather_w2_grid_winner_is_newer" in grid
    assert "weather_w2_assert_repair_evidence" in grid
    assert "not exists" in grid
    assert "weather_w2_latest_publishable_anchors_sql" in grid
    assert "eligible_manifest_anchors" in grid
    assert "observation.source_id = anchor.anchor_source_id" in grid
    assert "observation.dag_run_id = anchor.anchor_dag_run_id" in grid
    assert "current.published_at >= timestamp" in grid
    assert "current.selected_dag_run_id = current_anchor.anchor_dag_run_id" in grid
    assert "current_anchor.anchor_source_id is null" in grid

    reconciliation = compact(read(W1_GRID_RECONCILIATION_TEST))
    assert "weather_w2_latest_publishable_anchors_sql" in reconciliation
    assert "observation.source_id = anchor.anchor_source_id" in reconciliation
    assert "observation.dag_run_id = anchor.anchor_dag_run_id" in reconciliation
    assert "actual.selected_dag_run_id" in reconciliation

    repair_macro = compact(read(W2_MACRO))
    comparator = repair_macro[
        repair_macro.index("macro weather_w2_grid_winner_is_newer") :
    ]
    assert "is not distinct from" in comparator
    assert "is not null" in comparator
    assert "is null" in comparator


def test_gold_execute_time_contract_dependencies_are_explicit() -> None:
    gold_hints = "\n".join(read(W2_GOLD_MODEL).splitlines()[:6])

    assert "-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}" in gold_hints
    assert "-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}" in gold_hints
    assert "-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}" in gold_hints


def test_canonical_revision_is_pinned_and_validated_temp_drives_all_deletes() -> None:
    model = compact(read(W2_GOLD_MODEL))
    macro = compact(read(W2_MACRO))
    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]

    for token in (
        CANONICAL_REVISION_DATE,
        f"'canonical_count': {EXPECTED_CANONICAL_COUNT}",
        f"'bridge_count': {EXPECTED_BRIDGE_V1_COUNT}",
        f"'mapped_canonical_count': {EXPECTED_MAPPED_CANONICAL_COUNT}",
        "validated_canonical_contract",
        "canonical_retained_rows",
        "cross join validated_canonical_contract",
    ):
        assert token in model or token in macro
    assert (
        "cast(canonical.revision_date as date) = "
        "date '{{ canonical_contract['revision_date'] }}'" in model
    )
    assert "temp_mapped_canonical_code_count" in strategy
    assert "temp_canonical_revision_count" in strategy
    assert "temp_min_canonical_revision" in strategy
    assert "temp_max_canonical_revision" in strategy
    assert "ref('asac_axes', 'dim_admin_dong')" not in strategy
    assert "from {{ temp_relation }} as dbt_internal_validated" in strategy
    for key in ("admin_dong_code", "forecast_at", "category"):
        assert f"dbt_internal_validated.{key} = dbt_internal_dest.{key}" in strategy

    retained = model[
        model.index("canonical_retained_rows as") : model.index("product_rows as")
    ]
    assert "inner join canonical" in retained
    assert "cross join validated_canonical_contract" in retained
    assert "not ( target.published_at >= timestamp" in retained
    assert "not exists" in retained
    assert "target.admin_dong is distinct from canonical.admin_dong" not in retained


def test_dimension_backed_data_tests_use_the_approved_canonical_revision() -> None:
    for test_name in CANONICAL_DATA_TESTS:
        sql = compact(read(W2_DATA_TESTS / f"{test_name}.sql"))
        assert "set canonical_contract = weather_w2_canonical_contract()" in sql
        assert (
            "revision_date as date) = date '{{ canonical_contract['revision_date'] }}'"
            in sql
        )


def test_initial_ctas_evaluates_canonical_contract_when_product_rows_are_empty() -> (
    None
):
    model = compact(read(W2_GOLD_MODEL))

    assert "canonical_contract_failure_rows as" in model
    failure_rows = model[
        model.index("canonical_contract_failure_rows as") : model.index(
            "grid_candidates as"
        )
    ]
    assert "from validated_canonical_contract" in failure_rows
    assert "if( canonical_contract_guard" in failure_rows
    assert "where not canonical_contract_guard" in failure_rows
    assert "union all select" in model[model.index("from product_rows") :]
    assert (
        "from canonical_contract_failure_rows"
        in model[model.index("from product_rows") :]
    )


def test_custom_strategy_is_one_atomic_merge_with_bounded_delete_and_no_downgrade() -> (
    None
):
    macro = compact(read(W2_MACRO))
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
    for preflight in (
        "in_window_expected_count = 0",
        "target_null_contract_count",
        "admin_dong_code is null",
        "forecast_at is null",
        "category is null",
        "group by admin_dong_code, forecast_at, category",
        "having count(*) > 1",
        "target_duplicate_count > 0",
        "temp_mapped_canonical_code_count",
        "temp_canonical_revision_count",
    ):
        assert preflight in strategy
    assert "set repair_mode = weather_w2_is_repair()" in strategy
    assert "{% if repair_mode %}" in strategy
    assert "not exists ( select 1 from" in strategy
    for key in ("admin_dong_code", "forecast_at", "category"):
        assert f"dbt_internal_validated.{key} = dbt_internal_dest.{key}" in strategy
    assert "when matched and dbt_internal_source.__w2_delete then delete" in strategy
    assert "case when" in strategy
    assert "dbt_internal_source.admin_dong_revision_date" in strategy
    assert "dbt_internal_dest.raw_object_key" in strategy
    assert "dbt_internal_dest.request_id" in strategy
    assert (
        "raw_object_key = case when" in strategy
        and "then dbt_internal_source.raw_object_key else dbt_internal_dest.raw_object_key end"
        in strategy
    )
    assert (
        "request_id = case when" in strategy
        and "then dbt_internal_source.request_id else dbt_internal_dest.request_id end"
        in strategy
    )
    assert "when matched" in strategy
    assert (
        strategy.index("then delete")
        < strategy.index("then update")
        < strategy.index("then insert")
    )


def test_custom_strategy_evaluates_winner_order_once_per_source_row() -> None:
    macro = compact(read(W2_MACRO))
    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]

    assert strategy.count("weather_w2_gold_winner_is_not_older") == 1
    assert "__w2_source_is_not_older" in strategy
    assert "{{ source_is_not_older }}" not in strategy

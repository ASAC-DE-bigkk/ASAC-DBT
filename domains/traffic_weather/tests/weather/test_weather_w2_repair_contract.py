from __future__ import annotations

from pathlib import Path

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
    WEATHER_OBSERVATION_RECONCILIATION_TEST,
    W2_GOLD_MODEL,
    W2_LINEAGE_WORKSET_MODEL,
    W2_MACRO,
    W2_REPAIR_NO_DOWNGRADE_TEST,
    W2_REPAIR_RECONCILIATION_TEST,
    W2_REPAIR_WINDOW_EXTRA_TEST,
    W2_REPAIR_WINDOW_LINEAGE_TEST,
    compact,
    data_test_path,
    read,
)

W2_RECOVERY_STAGE_MACRO = Path(
    "macros/weather/weather_w2_recovery_stage.sql"
)
W2_RECOVERY_STAGE_MODEL = Path(
    "models/weather/special/recovery/weather_w2_observation_recovery_stage.sql"
)
W2_RECOVERY_MODELS_YAML = Path(
    "models/weather/special/recovery/_recovery.yml"
)
W2_RECOVERY_STAGE_WINDOW_TEST = Path(
    "tests/weather/special/recovery/stage/"
    "assert_weather_w2_recovery_stage_window.sql"
)
W2_RECOVERY_STAGE_FINAL_TEST = Path(
    "tests/weather/special/recovery/stage/"
    "assert_weather_w2_recovery_stage_final_reconciles.sql"
)
W2_RECOVERY_STAGE_WINNER_TEST = Path(
    "tests/weather/special/recovery/stage/"
    "assert_weather_w2_recovery_stage_no_downgrade.sql"
)
W2_RECOVERY_STAGE_LINEAGE_TEST = Path(
    "tests/weather/special/recovery/stage/"
    "assert_weather_w2_recovery_stage_lineage.sql"
)
W2_LATEST_GRID_RECORD_TEST = Path(
    "tests/weather/special/"
    "assert_gold_weather_forecast_by_admin_dong_latest_grid_record.sql"
)
W2_LATEST_GRID_RECORD_FULL_TEST = Path(
    "tests/weather/special/"
    "assert_gold_weather_forecast_by_admin_dong_latest_grid_record_full.sql"
)


def test_repair_inputs_and_canonical_gold_target_guard_fail_closed() -> None:
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
        macro.index("macro weather_w2_assert_gold_target") : macro.index(
            "endmacro", macro.index("macro weather_w2_assert_gold_target")
        )
    ]
    for target_check in (
        "target.name == 'dev'",
        "target.database == 'iceberg_dev'",
        "weather_schema_name()",
        "weather_w1_prod_snapshot_bootstrap_allowed()",
        "weather_w1_assert_prod_snapshot_bootstrap_evidence()",
        "not approved_dev_target and not approved_prod_snapshot",
    ):
        assert target_check in gold_guard
    initial_guard = macro[
        macro.index("macro weather_w2_gold_initial_build_guard") : macro.index(
            "endmacro", macro.index("macro weather_w2_gold_initial_build_guard")
        )
    ]
    assert "weather_w1_prod_snapshot_bootstrap_allowed()" in initial_guard
    assert "not weather_w2_is_repair()" in initial_guard
    assert "weather_w2_assert_gold_target" in compact(read(W2_GOLD_MODEL))
    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]
    assert "weather_w2_assert_gold_target" in strategy
    assert "weather_w2_assert_gold_dev_target" not in macro
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
    assert (
        "set is_test_node = model is defined and model.resource_type == 'test'"
        in raw_macro
    )
    assert (
        "execute and not is_test_node and this.schema != weather_schema_name()"
        in macro
    )

    w1_macro = compact(read(W1_MACRO))
    assert "bounded_isolated_smoke" in w1_macro
    assert "weather_w2_shared_dev_build_allowed" in w1_macro
    assert "weather_w2_assert_repair_evidence" in w1_macro
    assert "flags.full_refresh" in w1_macro


def test_recovery_stage_is_snapshot_pinned_target_only_and_downgrade_safe() -> None:
    model = compact(read(W2_RECOVERY_STAGE_MODEL))
    macro = compact(read(W2_RECOVERY_STAGE_MACRO))

    assert "modules.re.fullmatch" in macro
    assert "^[a-za-z0-9][a-za-z0-9_.-]{0,79}$" in macro

    for token in (
        "materialized='incremental'",
        "incremental_strategy='weather_w2_recovery_stage'",
        "weather_w2_recovery_checkpoint_id()",
        "weather_w2_recovery_target_admin_dong_code()",
        "weather_w2_silver_grid_at_snapshot()",
        "weather_w2_bridge_at_snapshot()",
        "source_admin_code",
        "1123053600",
        "nx = 61",
        "ny = 127",
        "weather_w2_repair_start_at()",
        "weather_w2_publishable_cutoff_at()",
    ):
        assert token in model

    strategy_start = macro.index(
        "macro get_incremental_weather_w2_recovery_stage_sql"
    )
    strategy = macro[
        strategy_start : macro.index("endmacro", strategy_start)
    ]
    assert strategy.count("merge into") == 1
    assert "delete from" not in strategy
    assert "then delete" not in strategy
    assert "dbt_internal_source.checkpoint_id = dbt_internal_dest.checkpoint_id" in strategy
    for key in ("admin_dong_code", "forecast_at", "category"):
        assert f"dbt_internal_source.{key} = dbt_internal_dest.{key}" in strategy
    assert "weather_w2_gold_winner_is_not_older" in strategy
    assert "when not matched then insert" in strategy


def test_recovery_stage_is_parse_safe_and_runtime_fail_closed() -> None:
    raw_model = read(W2_RECOVERY_STAGE_MODEL)
    model = compact(raw_model)

    assert "{% set repair_mode = weather_w2_is_repair() %}" in raw_model
    assert "{% if execute and not repair_mode %}" in raw_model
    assert "{% if repair_mode %}" in raw_model
    assert "{% else %}" in raw_model
    assert "where false" in model


def test_recovery_stage_singular_tests_are_normal_mode_parse_safe() -> None:
    for test_path in (
        W2_RECOVERY_STAGE_WINDOW_TEST,
        W2_RECOVERY_STAGE_FINAL_TEST,
        W2_RECOVERY_STAGE_WINNER_TEST,
        W2_RECOVERY_STAGE_LINEAGE_TEST,
    ):
        raw_contract = read(test_path)
        assert "{% set repair_mode = weather_w2_is_repair() %}" in raw_contract
        assert "{% if repair_mode %}" in raw_contract
        assert "{% else %}" in raw_contract
        assert "where false" in compact(raw_contract)


def test_recovery_stage_window_contract_combines_all_lightweight_failures() -> None:
    contract = compact(read(W2_RECOVERY_STAGE_WINDOW_TEST))

    for token in (
        "weather_w2_recovery_checkpoint_id()",
        "weather_w2_recovery_target_admin_dong_code()",
        "weather_w2_silver_grid_at_snapshot()",
        "weather_w2_bridge_at_snapshot()",
        "wrong_checkpoint_id",
        "wrong_target_admin_dong",
        "wrong_target_grid",
        "null_grain_or_lineage",
        "duplicate_stage_grain",
        "missing_expected_stage_row",
        "stage_payload_differs_from_pinned_winner",
        "unexpected_stage_window_row",
    ):
        assert token in contract
    assert "union all" in contract
    assert "winner.*" not in contract
    assert "weather_w2_gold_candidate_row('actual')" in contract
    assert "is distinct from expected.expected_payload" in contract


def test_recovery_stage_final_contracts_are_checkpoint_scoped_and_bucketed() -> None:
    final_contract = compact(read(W2_RECOVERY_STAGE_FINAL_TEST))
    winner_contract = compact(read(W2_RECOVERY_STAGE_WINNER_TEST))
    lineage_contract = compact(read(W2_RECOVERY_STAGE_LINEAGE_TEST))

    for contract in (final_contract, winner_contract, lineage_contract):
        assert "weather_w2_recovery_checkpoint_id()" in contract
        assert "weather_w2_observation_recovery_stage" in contract
        assert "checkpoint_id = '{{ checkpoint_id }}'" in contract
        assert "1123053600" in contract

    assert "missing_expected_stage_row" in final_contract
    assert "unexpected_stage_row" in final_contract
    assert "weather_w2_winner_bucket_count" in winner_contract
    assert "weather_w2_winner_bucket_index" in winner_contract
    assert "weather_w2_gold_winner_is_not_older" in winner_contract
    assert "weather_w2_lineage_run_bucket_count" in lineage_contract
    assert "weather_w2_lineage_run_bucket_index" in lineage_contract
    assert "forecast_lineage_not_backed_by_pinned_grid_row" in lineage_contract


def test_recovery_stage_publish_operation_is_one_target_only_atomic_merge() -> None:
    contract = compact(read(W2_MACRO))
    macro = compact(read(W2_RECOVERY_STAGE_MACRO))
    publish = macro[macro.index("macro weather_w2_publish_recovery_stage") :]
    stage_contract = compact(read(W2_RECOVERY_MODELS_YAML))

    assert "macro weather_w2_assert_gold_target(relation=none)" in contract
    assert "weather_w2_assert_gold_target(gold_relation)" in publish
    assert (
        "name: weather_w2_observation_recovery_stage"
        " description:" in stage_contract
    )
    assert "access: protected" in stage_contract
    assert publish.count("merge into") == 1
    assert "ref('gold_weather_forecast_by_admin_dong')" in publish
    assert "ref('weather_w2_observation_recovery_stage')" in publish
    assert "checkpoint_id = '{{ checkpoint_id }}'" in publish
    assert "admin_dong_code = '1123053600'" in publish
    assert "weather_w2_gold_winner_is_not_older" in publish
    assert "when not matched then insert" in publish
    assert "then delete" not in publish
    assert "delete from" not in publish


def test_gold_repair_reconciliation_uses_grouped_winner_without_topn_or_join_back() -> (
    None
):
    raw = read(W2_REPAIR_RECONCILIATION_TEST)
    compacted = compact(raw)
    winner = raw[
        raw.index("winning_candidates as") : raw.index("boundary_expected as")
    ]

    assert "winning_candidates as" in raw
    assert "max_by(" in winner
    assert "weather_w2_gold_candidate_row('joined_candidates')" in winner
    assert "weather_w2_grid_winner_order_key('joined_candidates')" in winner
    assert "group by admin_dong_code, forecast_at, category" in winner
    assert "candidate_payload_hash" not in raw
    assert "sha256(" not in compacted
    assert "json_format(" not in compacted
    assert "row_number() over" not in compacted
    assert "winning_grid_candidate_keys" not in raw
    assert "left join {{ ref('gold_weather_forecast_by_admin_dong') }} as actual" in raw
    assert "full outer join" not in compacted
    assert "weather_w2_gold_winner_is_not_older" in raw
    assert "weather_w2_gold_candidate_row('actual')" in raw
    assert "is distinct from expected.expected_payload" in compacted

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


def test_latest_grid_record_contract_reuses_grouped_gold_winner_without_topn() -> None:
    raw = read(W2_LATEST_GRID_RECORD_TEST)
    compacted = compact(raw)
    assert "winning_candidates as" in raw
    winner = raw[raw.index("winning_candidates as") : raw.index("expected as")]

    assert "max_by(" in winner
    assert "weather_w2_gold_candidate_row('joined_candidates')" in winner
    assert "weather_w2_grid_winner_order_key('joined_candidates')" in winner
    assert "group by admin_dong_code, forecast_at, category" in winner
    assert "row_number() over" not in compacted


def test_latest_grid_record_contract_excludes_retracted_manifest_runs() -> None:
    raw = read(W2_LATEST_GRID_RECORD_TEST)
    compacted = compact(raw)

    assert "latest_manifest_run_state(" in raw
    assert "eligible_manifest_anchors as" in compacted
    assert "manifest_status = 'success'" in compacted
    assert "is_publishable" in compacted
    assert "inner join eligible_manifest_anchors as anchor" in compacted
    assert "grid.selected_dag_run_id" in compacted
    assert "anchor.anchor_dag_run_id" in compacted


def test_latest_grid_record_routine_contract_scopes_to_snapshot_affected_keys() -> None:
    compacted = compact(read(W2_LATEST_GRID_RECORD_TEST))

    assert "var('weather_snapshot_dag_run_id'" in compacted
    assert "affected_product_keys as" in compacted
    assert "inner join affected_product_keys" in compacted


def test_latest_grid_record_full_contract_keeps_global_publishable_winner() -> None:
    raw = read(W2_LATEST_GRID_RECORD_FULL_TEST)
    compacted = compact(raw)

    assert "weather_snapshot_dag_run_id" not in compacted
    assert "affected_product_keys as" not in compacted
    assert "latest_manifest_run_state(" in compacted
    assert "inner join eligible_manifest_anchors as anchor" in compacted
    assert "weather_w2_grid_winner_order_key('joined_candidates')" in compacted


def test_repair_no_downgrade_is_bucketed_before_narrow_winner_aggregation() -> None:
    raw = read(W2_REPAIR_NO_DOWNGRADE_TEST)
    compacted = compact(raw)
    dependency_preamble = raw[: raw.index("{% if repair_mode %}")]
    assert "{% set repair_mode = weather_w2_is_repair() %}" in dependency_preamble

    for relation_binding in (
        "{% set gold_relation = ref('gold_weather_forecast_by_admin_dong') %}",
        "{% set bridge_relation = ref('bridge_weather_admin_dong_grid') %}",
        "{% set canonical_relation = ref('asac_axes', 'dim_admin_dong') %}",
        "{% set grid_relation = ref('silver_kma_vilage_fcst_grid') %}",
    ):
        assert relation_binding in dependency_preamble

    for token in (
        "weather_w2_winner_bucket_count",
        "weather_w2_winner_bucket_index",
        "weather_w2_canonical_grain_bucket",
        "exceptions.raise_compiler_error",
        "grid_candidates as",
        "joined_candidates as",
        "bucketed_candidates as",
        "winning_candidates as",
        "max_by(",
        "weather_w2_grid_winner_order_key('bucketed_candidates')",
        "group by admin_dong_code, forecast_at, category",
        "weather_w2_gold_winner_is_not_older",
    ):
        assert token in compacted
    assert "var('weather_w2_winner_bucket_count', 8)" in compacted
    assert "repair_mode and winner_bucket_count != 8" not in compacted

    assert compacted.index("grid_candidates as") < compacted.index(
        "joined_candidates as"
    )
    assert compacted.index("joined_candidates as") < compacted.index(
        "bucketed_candidates as"
    )
    assert compacted.index("bucketed_candidates as") < compacted.index(
        "winning_candidates as"
    )
    assert "published_at as timestamp(6)) >= timestamp" in compacted
    assert "all_grid_records as" not in compacted
    assert "row_number() over" not in compacted
    assert "mixed_or_unbacked_lineage as" not in compacted
    assert "forecast_lineage_not_backed_by_one_grid_row" not in compacted
    assert "fcst_value_raw" not in compacted
    assert "weather_w2_gold_candidate_row" not in compacted
    for relation_name in (
        "gold_relation",
        "bridge_relation",
        "canonical_relation",
        "grid_relation",
    ):
        assert f"from {{{{ {relation_name} }}}}" in raw

    macro = compact(read(W2_MACRO))
    bucket_macro = macro[
        macro.index("macro weather_w2_canonical_grain_bucket") : macro.index(
            "endmacro", macro.index("macro weather_w2_canonical_grain_bucket")
        )
    ]
    assert "xxhash64" in bucket_macro
    assert "json_format(cast(row(" in bucket_macro
    assert "admin_dong_code" in bucket_macro
    assert "forecast_at" in bucket_macro
    assert "category" in bucket_macro
    assert bucket_macro.count("mod(") >= 2


def test_repair_lineage_workset_is_parse_safe_and_runtime_fail_closed() -> None:
    raw_workset = read(W2_LINEAGE_WORKSET_MODEL)
    workset = compact(raw_workset)
    dependency_hints = "\n".join(raw_workset.splitlines()[:8])
    for dependency in (
        "bridge_weather_admin_dong_grid",
        "asac_axes', 'dim_admin_dong",
        "silver_kma_vilage_fcst_grid",
        "gold_weather_forecast_by_admin_dong",
    ):
        assert "-- depends_on:" in dependency_hints
        assert dependency in dependency_hints
    assert "{% set repair_mode = weather_w2_is_repair() %}" in raw_workset
    assert "{% if execute and not repair_mode %}" in raw_workset
    assert "{% if repair_mode %}" in raw_workset
    assert "{% else %}" in raw_workset
    assert "where false" in workset
    for token in (
        "materialized='table'",
        "alias='weather_w2_observation_recovery_lineage_workset'",
        "weather_w2_is_repair",
        "weather_w2_assert_gold_target",
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
    reconciliation = compact(read(WEATHER_OBSERVATION_RECONCILIATION_TEST))

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
    gold_hints = "\n".join(read(W2_GOLD_MODEL).splitlines()[:12])

    assert "-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}" in gold_hints
    # weather_w2_assert_gold_source_contract() 가 조건부 블록 안에서 live dim_admin_dong 을
    # run_query 로 검증하므로 이 hint 는 유지되어야 한다(#480 에서 제거했다가 복원).
    assert "-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}" in gold_hints
    assert (
        "-- depends_on: {{ ref('asac_axes', 'seoul_admin_dong_crosswalk') }}"
        in gold_hints
    )
    assert (
        "-- depends_on: {{ source('axes_bronze', 'admin_dong_master') }}"
        in gold_hints
    )
    assert "-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}" in gold_hints


def test_canonical_revision_is_pinned_and_affected_keys_fail_closed_without_restamp() -> (
    None
):
    model = compact(read(W2_GOLD_MODEL))
    macro = compact(read(W2_MACRO))
    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]

    for token in (
        CANONICAL_REVISION_DATE,
        f"'canonical_count': {EXPECTED_CANONICAL_COUNT}",
        f"'bridge_count': {EXPECTED_BRIDGE_V1_COUNT}",
        f"'mapped_canonical_count': {EXPECTED_MAPPED_CANONICAL_COUNT}",
        "validated_canonical_contract",
        "cross join validated_canonical_contract",
    ):
        assert token in model or token in macro
    assert (
        "cast(canonical.revision_date as date) = "
        "date '{{ canonical_contract['revision_date'] }}'" in model
    )
    for token in (
        "dbt_internal_affected_keys as",
        "affected_target_grain as",
        "affected_target_summary as",
        "affected_target_canonical_mismatch_count",
        "keyed canonical migration",
    ):
        assert token in strategy
    for key in ("admin_dong_code", "forecast_at", "category"):
        assert f"dbt_internal_key.{key} = target.{key}" in strategy

    assert "canonical_retained_rows" not in model
    assert "cross join target_summary" not in strategy
    assert "target_duplicate_grain as" not in strategy
    assert "target_summary.target_canonical_mismatch_count" not in strategy


def test_dimension_backed_data_tests_use_the_approved_canonical_revision() -> None:
    for test_name in CANONICAL_DATA_TESTS:
        sql = compact(read(data_test_path(test_name)))
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
    assert "union all select" in model[model.index("from expected_rows") :]
    assert (
        "from canonical_contract_failure_rows"
        in model[model.index("from expected_rows") :]
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
        "in_window_expected_count == 0",
        "affected_target_null_contract_count",
        "affected_target_canonical_mismatch_count",
        "affected_target_duplicate_count > 0",
        "temp_canonical_mismatch_count",
        "admin_dong_code is null",
        "forecast_at is null",
        "category is null",
        "group by admin_dong_code, forecast_at, category",
        "having count(*) > 1",
    ):
        assert preflight in strategy
    assert "set repair_mode = weather_w2_is_repair()" in strategy
    assert "{% if repair_mode %}" in strategy
    assert "dbt_internal_desired_keys as" in strategy
    assert "not exists ( select 1 from dbt_internal_desired_keys" in strategy
    for key in ("admin_dong_code", "forecast_at", "category"):
        assert f"dbt_internal_desired.{key} = dbt_internal_dest.{key}" in strategy
    assert "when matched and dbt_internal_source.__w2_delete then delete" in strategy
    assert "dbt_internal_source.admin_dong_revision_date" in strategy
    assert "raw_object_key = dbt_internal_source.raw_object_key" in strategy
    assert "request_id = dbt_internal_source.request_id" in strategy
    assert "__w2_source_is_not_older" not in strategy
    assert "when matched" in strategy
    assert (
        strategy.index("then delete")
        < strategy.index("then update")
        < strategy.index("then insert")
    )


def test_atomic_merge_delete_markers_are_unique_by_canonical_grain() -> None:
    strategy = compact(read(W2_MACRO))
    strategy = strategy[strategy.index("macro get_incremental_weather_w2_reconcile_sql") :]

    assert "dbt_internal_delete_keys as" in strategy
    delete_keys = strategy[
        strategy.index("dbt_internal_delete_keys as") : strategy.index(
            "select dbt_internal_upsert.product_row_id"
        )
    ]
    assert "select distinct" in delete_keys
    for grain_column in ("admin_dong_code", "forecast_at", "category"):
        assert f"dbt_internal_dest.{grain_column}" in delete_keys
    assert "not exists" in delete_keys

    delete_markers = strategy[
        strategy.index("union all", strategy.index("dbt_internal_delete_keys as")) :
        strategy.index(") as dbt_internal_source")
    ]
    assert "from dbt_internal_delete_keys as dbt_internal_delete" in delete_markers
    assert "from {{ target_relation }} as dbt_internal_dest" not in delete_markers


def test_normal_merge_compares_winner_at_match_time_without_source_target_self_join() -> (
    None
):
    macro = compact(read(W2_MACRO))
    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]
    classified = strategy[
        strategy.index("dbt_internal_upsert_classified as") : strategy.index(
            "dbt_internal_upsert_rows as"
        )
    ]
    normal_branch = classified[
        classified.index("{% else %}") : classified.index("{% endif %}")
    ]

    assert strategy.count("weather_w2_gold_winner_is_not_older") == 1
    assert "from {{ temp_relation }} as dbt_internal_upsert" in normal_branch
    assert "false as __w2_force_replace" in normal_branch
    assert "join {{ target_relation }}" not in normal_branch
    assert "__w2_source_is_not_older" not in strategy
    assert "dbt_internal_source.__w2_force_replace" in strategy

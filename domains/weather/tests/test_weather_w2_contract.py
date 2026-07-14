import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

import yaml


WEATHER_DIR = Path(__file__).parents[1]
REPO_DIR = WEATHER_DIR.parents[1]
BASE_COMMIT = "4e67f0ab9f6e276cfcf8bae77eb460b75d43ca7e"

MODEL_NAME = "gold_weather_forecast_by_admin_dong"
BRIDGE_VERSION = "weather_admin_dong_grid_bridge_v1"
CANONICAL_REVISION_DATE = "2025-04-01"
EXPECTED_BRIDGE_V1_COUNT = 427
EXPECTED_CANONICAL_COUNT = 426
EXPECTED_MAPPED_CANONICAL_COUNT = 425
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
    "assert_gold_weather_forecast_by_admin_dong_canonical_source_contract",
    "assert_gold_weather_forecast_by_admin_dong_latest_grid_record",
    "assert_gold_weather_forecast_by_admin_dong_bridge_exclusions_reconcile",
    "assert_gold_weather_forecast_by_admin_dong_repair_reconciles",
    "assert_gold_weather_forecast_by_admin_dong_repair_window_no_extra_rows",
    "assert_gold_weather_forecast_by_admin_dong_repair_no_downgrade",
}
CANONICAL_DATA_TESTS = DATA_TESTS - {
    "assert_gold_weather_forecast_by_admin_dong_grain_unique",
    "assert_gold_weather_forecast_by_admin_dong_product_row_id_reproducible",
}


def read(relative_path: str) -> str:
    return (WEATHER_DIR / relative_path).read_text(encoding="utf-8")


def compact(text: str) -> str:
    return " ".join(text.lower().split())


def model_contract() -> dict:
    schema = yaml.safe_load(read("models/schema.yml"))
    return next(model for model in schema["models"] if model["name"] == MODEL_NAME)


def git_blob_bytes(revision: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative_path}"],
        cwd=REPO_DIR,
        check=True,
        capture_output=True,
    )
    return result.stdout


def git_index_blob_bytes(relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f":{relative_path}"],
        cwd=REPO_DIR,
        check=True,
        capture_output=True,
    )
    return result.stdout


def bridge_version_digest(blob: bytes, bridge_version: str) -> tuple[int, str]:
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig"), newline=""))
    fieldnames = tuple(reader.fieldnames or ())
    assert "bridge_version" in fieldnames
    rows = sorted(
        tuple(row[name] for name in fieldnames)
        for row in reader
        if row["bridge_version"] == bridge_version
    )
    canonical = json.dumps(
        {"fieldnames": fieldnames, "rows": rows},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return len(rows), hashlib.sha256(canonical).hexdigest()


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
    for weather_relative_path, expected_sha256 in expected.items():
        repo_relative_path = f"domains/weather/{weather_relative_path}"
        assert hashlib.sha256(git_blob_bytes(BASE_COMMIT, repo_relative_path)).hexdigest() == expected_sha256
        assert hashlib.sha256(git_blob_bytes("HEAD", repo_relative_path)).hexdigest() == expected_sha256
        assert hashlib.sha256(git_index_blob_bytes(repo_relative_path)).hexdigest() == expected_sha256
        unchanged = subprocess.run(
            ["git", "diff", "--quiet", BASE_COMMIT, "--", repo_relative_path],
            cwd=REPO_DIR,
            check=False,
        )
        assert unchanged.returncode == 0


def test_active_bridge_v1_seed_is_immutable():
    relative_path = "domains/weather/seeds/weather_admin_dong_grid_bridge_history.csv"
    expected = (
        EXPECTED_BRIDGE_V1_COUNT,
        "ead91675f13465a1d9211780b20246f755e9df372c5dee4795ce815bc9468767",
    )
    for blob in (
        git_blob_bytes(BASE_COMMIT, relative_path),
        git_blob_bytes("HEAD", relative_path),
        git_index_blob_bytes(relative_path),
        (REPO_DIR / relative_path).read_bytes(),
    ):
        assert bridge_version_digest(blob, BRIDGE_VERSION) == expected


def test_repair_inputs_and_shared_dev_guard_fail_closed():
    raw_macro = read("macros/weather_w2_contract.sql")
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
        macro.index("macro weather_w2_assert_gold_dev_target") :
        macro.index("endmacro", macro.index("macro weather_w2_assert_gold_dev_target"))
    ]
    assert "if execute and (" in gold_guard
    for target_check in (
        "target.name != 'dev'",
        "target.database != 'iceberg_dev'",
        "target.schema != 'weather'",
    ):
        assert target_check in gold_guard
    assert "weather_w2_assert_gold_dev_target" in compact(
        read(f"models/gold/{MODEL_NAME}.sql")
    )
    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]
    assert "weather_w2_assert_gold_dev_target" in strategy
    assert "^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{6}$" in raw_macro
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
        "target.schema != 'weather'",
    ):
        assert condition in macro

    w1_macro = compact(read("macros/weather_v2_contract.sql"))
    assert "bounded_isolated_smoke" in w1_macro
    assert "weather_w2_shared_dev_build_allowed" in w1_macro
    assert "weather_w2_assert_repair_evidence" in w1_macro
    assert "flags.full_refresh" in w1_macro


def test_gold_repair_reconciliation_compacts_payload_before_winner_ranking():
    raw = read("tests/assert_gold_weather_forecast_by_admin_dong_repair_reconciles.sql")
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

    extra_rows = compact(
        read("tests/assert_gold_weather_forecast_by_admin_dong_repair_window_no_extra_rows.sql")
    )
    assert "ranked_grid_candidate_keys as" in extra_rows
    assert "actual_window as" in extra_rows
    assert "unexpected_window_gold_row" in extra_rows
    assert "published_at as timestamp(6)) >= timestamp" in extra_rows


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


def test_observation_reconciliation_uses_explicit_trino_join_aliases():
    reconciliation = compact(
        read("tests/assert_weather_observation_publishable_and_counts_reconcile.sql")
    )

    assert "from manifest as manifest_run" in reconciliation
    assert "left join source_actual as source_actual_run" in reconciliation
    assert "left join actual as actual_run" in reconciliation
    assert "on manifest_run.source_id = source_actual_run.source_id" in reconciliation
    assert "and manifest_run.dag_run_id = source_actual_run.dag_run_id" in reconciliation
    assert "on manifest_run.source_id = actual_run.source_id" in reconciliation
    assert "and manifest_run.dag_run_id = actual_run.dag_run_id" in reconciliation
    assert "manifest_run.dag_run_id" in reconciliation
    assert "using (source_id, dag_run_id)" not in reconciliation


def test_w1_keeps_normal_lookback_and_adds_bounded_repair_no_downgrade():
    observation = compact(read("models/silver/silver_kma_vilage_fcst_observation.sql"))
    grid_raw = read("models/silver/silver_kma_vilage_fcst_grid.sql")
    grid = compact(grid_raw)
    grid_hints = "\n".join(grid_raw.splitlines()[:5])
    bridge_raw = read("models/silver/bridge_weather_admin_dong_grid.sql")
    bridge_hints = "\n".join(bridge_raw.splitlines()[:5])

    assert "-- depends_on: {{ ref('silver_kma_vilage_fcst_observation') }}" in grid_hints
    assert "-- depends_on: {{ ref('weather_admin_dong_grid_bridge_history') }}" in bridge_hints
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

    grid_reconciliation = compact(read("tests/assert_weather_grid_selection_reconciles.sql"))
    assert "weather_w2_latest_publishable_anchors_sql" in grid_reconciliation
    assert "observation.source_id = anchor.anchor_source_id" in grid_reconciliation
    assert "observation.dag_run_id = anchor.anchor_dag_run_id" in grid_reconciliation
    assert "actual.selected_dag_run_id" in grid_reconciliation

    repair_macro = compact(read("macros/weather_w2_contract.sql"))
    comparator = repair_macro[repair_macro.index("macro weather_w2_grid_winner_is_newer") :]
    assert "is not distinct from" in comparator
    assert "is not null" in comparator
    assert "is null" in comparator


def test_gold_execute_time_contract_dependencies_are_explicit():
    gold_raw = read("models/gold/gold_weather_forecast_by_admin_dong.sql")
    gold_hints = "\n".join(gold_raw.splitlines()[:6])

    assert "-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}" in gold_hints
    assert "-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}" in gold_hints
    assert "-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}" in gold_hints


def test_canonical_revision_is_pinned_and_validated_temp_drives_all_deletes():
    model = compact(read(f"models/gold/{MODEL_NAME}.sql"))
    macro = compact(read("macros/weather_w2_contract.sql"))
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
        "date '{{ canonical_contract['revision_date'] }}'"
        in model
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


def test_dimension_backed_data_tests_use_the_approved_canonical_revision():
    for test_name in CANONICAL_DATA_TESTS:
        sql = compact(read(f"tests/{test_name}.sql"))

        assert "set canonical_contract = weather_w2_canonical_contract()" in sql
        assert "revision_date as date) = date '{{ canonical_contract['revision_date'] }}'" in sql


def test_initial_ctas_evaluates_canonical_contract_when_product_rows_are_empty():
    model = compact(read(f"models/gold/{MODEL_NAME}.sql"))

    assert "canonical_contract_failure_rows as" in model
    failure_rows = model[
        model.index("canonical_contract_failure_rows as") :
        model.index("grid_candidates as")
    ]
    assert "from validated_canonical_contract" in failure_rows
    assert "if( canonical_contract_guard" in failure_rows
    assert "where not canonical_contract_guard" in failure_rows
    assert "union all select" in model[model.index("from product_rows") :]
    assert "from canonical_contract_failure_rows" in model[model.index("from product_rows") :]


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
    delete_clause = strategy.index("then delete")
    update_clause = strategy.index("then update")
    insert_clause = strategy.index("then insert")
    assert delete_clause < update_clause < insert_clause


def test_custom_strategy_evaluates_winner_order_once_per_source_row():
    macro = compact(read("macros/weather_w2_contract.sql"))
    strategy = macro[macro.index("macro get_incremental_weather_w2_reconcile_sql") :]

    assert strategy.count("weather_w2_gold_winner_is_not_older") == 1
    assert "__w2_source_is_not_older" in strategy
    assert "{{ source_is_not_older }}" not in strategy


def test_gold_sql_has_exact_refs_grain_winner_row_id_and_approved_revision_snapshot():
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


def test_gold_repair_expected_set_is_correlated_to_latest_publishable_manifest_anchors():
    macro = compact(read("macros/weather_w2_contract.sql"))
    model = compact(read(f"models/gold/{MODEL_NAME}.sql"))

    anchor_macro = macro[
        macro.index("macro weather_w2_latest_publishable_anchors_sql") :
        macro.index("endmacro", macro.index("macro weather_w2_latest_publishable_anchors_sql"))
    ]
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

    for sql in (model, macro[macro.index("macro weather_w2_assert_gold_source_contract") :]):
        assert "weather_w2_latest_publishable_anchors_sql" in sql
        assert "eligible_manifest_anchors" in sql
        assert "anchor.anchor_source_id" in sql
        assert "anchor.anchor_dag_run_id" in sql
        assert "grid.selected_dag_run_id" in sql


def test_gold_source_guard_covers_latest_canonical_and_initial_ctas_contract():
    macro = compact(read("macros/weather_w2_contract.sql"))
    source_guard = macro[
        macro.index("macro weather_w2_assert_gold_source_contract") :
        macro.index("endmacro", macro.index("macro weather_w2_assert_gold_source_contract"))
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


def test_public_contract_declares_exact_schema_approved_axis_and_truthful_status():
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
    schema_doc = read("models/schema.yml")
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
    for document in (contract_doc, operating_doc):
        assert "scoped shared DEV smoke" in document
        assert "formal approved-dev" in document
    assert "DAG run id" in operating_doc
    assert "NOT_RUN" in operating_doc
    assert not (
        REPO_DIR
        / "docs/superpowers/plans/2026-07-13-weather-canonical-public-gold.md"
    ).exists()
    assert not (
        REPO_DIR
        / "docs/superpowers/specs/2026-07-13-weather-canonical-public-gold-design.md"
    ).exists()
    assert "desired temp" in operating_doc.lower()
    assert "writer" in operating_doc.lower()

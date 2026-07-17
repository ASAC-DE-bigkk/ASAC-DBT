"""Contracts for Traffic history Silver publishability reconciliation."""

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL = PROJECT_ROOT / "models/traffic/transform/silver/silver_seoul_traffic_incident.sql"
MACRO = PROJECT_ROOT / "macros/traffic/traffic_publishability_reconcile.sql"
LEGACY_MACRO = PROJECT_ROOT / "macros/traffic/traffic_snapshot_reconcile.sql"


def compact(value: str) -> str:
    return " ".join(value.lower().split())


def test_history_model_uses_publishability_reconcile_strategy():
    sql = MODEL.read_text(encoding="utf-8")

    assert "incremental_strategy='traffic_publishability_reconcile'" in sql
    assert "views_enabled=false" in sql
    assert "unique_key=['source_record_id']" in sql
    assert "traffic_snapshot_reconcile" not in sql
    assert not LEGACY_MACRO.exists()


def test_strategy_retracts_and_upserts_in_one_merge():
    assert MACRO.is_file(), f"missing Traffic reconcile macro: {MACRO}"
    raw_sql = MACRO.read_text(encoding="utf-8")
    sql = compact(raw_sql)

    assert "get_incremental_traffic_publishability_reconcile_sql" in sql
    assert sql.count("merge into") == 1
    assert re.search(r"(?im)^\s*delete\s+from\b", raw_sql) is None
    assert "dbt_internal_publishable_upsert_rows" in sql
    assert "dbt_internal_stale_keys" in sql
    assert "when matched and dbt_internal_source.__traffic_delete then delete" in sql
    assert "when not matched and not dbt_internal_source.__traffic_delete then insert" in sql
    assert "is distinct from" in sql


def test_strategy_retracts_only_latest_nonpublishable_target_lineage():
    assert MACRO.is_file(), f"missing Traffic reconcile macro: {MACRO}"
    sql = compact(MACRO.read_text(encoding="utf-8"))
    stale_keys = sql[
        sql.index("dbt_internal_stale_keys as (") : sql.index(
            "dbt_internal_upsert_source as ("
        )
    ]

    assert "from {{ target_relation }} as dbt_internal_dest" in stale_keys
    assert "left join dbt_internal_latest_manifest_state as dbt_internal_manifest" in stale_keys
    assert (
        "cast(dbt_internal_dest.dag_run_id as varchar) "
        "= cast(dbt_internal_manifest.dag_run_id as varchar)" in stale_keys
    )
    manifest_nonpublishability_then_replacement_guard = (
        "where ( dbt_internal_manifest.dag_run_id is null "
        "or dbt_internal_manifest.manifest_status <> 'success' "
        "or not coalesce(dbt_internal_manifest.is_publishable, false) ) "
        "and not exists ( select 1 from dbt_internal_publishable_upsert_rows "
        "as dbt_internal_upsert where dbt_internal_upsert.source_record_id "
        "= dbt_internal_dest.source_record_id )"
    )
    assert manifest_nonpublishability_then_replacement_guard in stale_keys
    assert "where not exists" not in stale_keys


def test_strategy_guards_dev_iceberg_dev_traffic_schema_before_merge():
    assert MACRO.is_file(), f"missing Traffic reconcile macro: {MACRO}"
    sql = compact(MACRO.read_text(encoding="utf-8"))
    guard = sql[
        sql.index("macro traffic_publishability_assert_dev_target") : sql.index(
            "endmacro",
            sql.index("macro traffic_publishability_assert_dev_target"),
        )
    ]
    strategy = sql[sql.index("macro get_incremental_traffic_publishability_reconcile_sql") :]

    assert "if execute and (" in guard
    for target_check in (
        "target.name != 'dev'",
        "target.database != 'iceberg_dev'",
        "target_relation.schema != env_var('traffic_schema', 'traffic')",
        "exceptions.raise_compiler_error",
    ):
        assert target_check in guard

    guard_call = "traffic_publishability_assert_dev_target(target_relation)"
    assert guard_call in strategy
    assert strategy.index(guard_call) < strategy.index("merge into")

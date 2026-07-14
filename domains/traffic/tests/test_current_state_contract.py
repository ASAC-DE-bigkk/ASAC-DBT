from pathlib import Path

from domains.traffic.contracts.scripts.validate_singular_test_dependency_manifest import (
    REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES,
)


TRAFFIC_DIR = Path(__file__).parents[1]


def test_dbt_project_disables_static_parser_for_deterministic_dependency_edges():
    project = (TRAFFIC_DIR / "dbt_project.yml").read_text(encoding="utf-8")

    assert "static_parser: false" in project


def test_current_model_requires_transform_pinned_publishable_manifest_run():
    sql = (TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident_current.sql").read_text()
    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "silver_seoul_traffic_incident" in sql


def test_history_model_uses_transform_pinned_publishable_manifest_run():
    sql = (TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident.sql").read_text(encoding="utf-8")

    assert "var('traffic_snapshot_dag_run_id')" in sql


def test_silver_models_declare_conditional_model_dependencies():
    history_sql = (
        TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident.sql"
    ).read_text(encoding="utf-8")
    current_sql = (
        TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident_current.sql"
    ).read_text(encoding="utf-8")

    assert "-- depends_on: {{ ref('asac_axes', 'seoul_admin_dong_boundary') }}" in history_sql
    assert "-- depends_on: {{ ref('silver_seoul_traffic_incident') }}" in current_sql


def test_history_latest_record_contract_uses_the_same_transform_pinned_run():
    sql = (
        TRAFFIC_DIR / "tests/assert_silver_traffic_latest_publishable_record.sql"
    ).read_text(encoding="utf-8")
    compact_sql = " ".join(sql.split())

    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "requested_run" in sql
    assert "configured_run" in sql
    assert "cast(bronze.dag_run_id as varchar) = configured_run.dag_run_id" in compact_sql
    assert "missing_pinned_run" in sql
    assert "silver_watermark" not in sql


def test_current_snapshot_contract_test_uses_transform_pinned_run():
    sql = (TRAFFIC_DIR / "tests/assert_traffic_current_pinned_publishable_run.sql").read_text()

    assert "var('traffic_snapshot_dag_run_id')" in sql


def test_current_snapshot_contract_keeps_pinned_correctness_and_grace_freshness_separate():
    sql = (
        TRAFFIC_DIR / "tests/assert_traffic_current_pinned_publishable_run.sql"
    ).read_text(encoding="utf-8").lower()
    compact_sql = " ".join(sql.split())

    assert "group by cast(dag_run_id as varchar)" in sql
    assert "publishable_rank" in sql
    assert "publishable_rank > 3" in sql
    assert "missing_pinned_run" in sql
    assert "stale_rows" in sql
    assert "missing_rows" in sql
    assert "extra_rows" in sql
    assert "is distinct from pinned_run.dag_run_id" in sql
    assert "select * from expected_current except select * from actual_current" in compact_sql
    assert "select * from actual_current except select * from expected_current" in compact_sql


def test_current_snapshot_contract_does_not_reanchor_correctness_to_live_latest():
    sql = (
        TRAFFIC_DIR / "tests/assert_traffic_current_pinned_publishable_run.sql"
    ).read_text(encoding="utf-8").lower()

    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "limit 1" not in sql


def test_current_snapshot_contract_uses_the_dag_publishable_predicate_without_terminal_rewrite():
    sql = (
        TRAFFIC_DIR / "tests/assert_traffic_current_pinned_publishable_run.sql"
    ).read_text(encoding="utf-8").lower()
    compact_sql = " ".join(sql.split())

    assert "manifest_event_rank" not in sql
    assert "max(cast(event_at as timestamp(6))) as event_at" in compact_sql
    assert "and status = 'success'" in compact_sql
    assert "and is_publishable" in compact_sql


def test_current_snapshot_contract_allows_continued_zero_incident_runs_inside_freshness_check():
    sql = (
        TRAFFIC_DIR / "tests/assert_traffic_current_pinned_publishable_run.sql"
    ).read_text(encoding="utf-8").lower()
    compact_sql = " ".join(sql.split())

    assert "newer_valid_bronze" in sql
    assert "exists (select 1 from actual_current)" in compact_sql
    assert "exists (select 1 from newer_valid_bronze)" in compact_sql


def test_gold_summary_reads_current_incidents_not_history():
    sql = (TRAFFIC_DIR / "models/gold/gold_traffic_incident_summary.sql").read_text()
    assert "silver_seoul_traffic_incident_current" in sql


def test_snapshot_recovery_models_are_isolated_from_current_relations():
    metadata_sql = (
        TRAFFIC_DIR / "models/recovery/recovery_traffic_snapshot_metadata.sql"
    ).read_text(encoding="utf-8")
    silver_sql = (
        TRAFFIC_DIR / "models/recovery/recovery_silver_seoul_traffic_incident.sql"
    ).read_text(encoding="utf-8")
    gold_sql = (
        TRAFFIC_DIR / "models/recovery/recovery_gold_traffic_incident_summary.sql"
    ).read_text(encoding="utf-8")

    assert "ref('recovery_silver_seoul_traffic_incident')" in metadata_sql
    assert "cast(dag_run_id as varchar) as snapshot_dag_run_id" in metadata_sql
    assert "where is_snapshot_marker" in metadata_sql
    assert "var('traffic_snapshot_dag_run_id')" in silver_sql
    assert "snapshot_marker as" in silver_sql
    assert "true as is_snapshot_marker" in silver_sql
    assert "false as is_snapshot_marker" in silver_sql
    assert "source('traffic_bronze', 'seoul_traffic_incident')" in silver_sql
    assert "silver_seoul_traffic_incident_current" not in silver_sql
    assert "ref('recovery_traffic_snapshot_metadata')" in gold_sql
    assert "ref('recovery_silver_seoul_traffic_incident')" in gold_sql
    assert "where not is_snapshot_marker" in gold_sql
    assert "silver_seoul_traffic_incident_current" not in gold_sql


def test_snapshot_recovery_contract_validates_the_requested_publishable_run():
    sql = (
        TRAFFIC_DIR / "tests/assert_recovery_silver_traffic_snapshot_matches_bronze.sql"
    ).read_text(encoding="utf-8")
    compact_sql = " ".join(sql.split())

    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "requested_run" in sql
    assert "configured_run" in sql
    assert "metadata_run" in sql
    assert "missing_pinned_run" in sql
    assert "metadata_run_mismatch" in sql
    assert "silver_marker_run" in sql
    assert "silver_marker_run_mismatch" in sql
    assert "{{ target.database }}.{{ target.schema }}.recovery_traffic_snapshot_metadata" in sql
    assert "{{ target.database }}.{{ target.schema }}.recovery_silver_seoul_traffic_incident" in sql
    assert "where exists (select 1 from configured_run)" in compact_sql
    assert "select * from expected_deduped except select * from actual_current" in compact_sql
    assert "select * from actual_current except select * from expected_deduped" in compact_sql
    assert "where not is_snapshot_marker" in sql


def test_singular_tests_declare_required_model_dependencies():
    for filename, model_names in REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES.items():
        sql = (TRAFFIC_DIR / "tests" / filename).read_text(encoding="utf-8")
        sql_body = "\n".join(
            line for line in sql.splitlines() if not line.strip().startswith("--")
        )

        for model_name in model_names:
            assert f"-- depends_on: {{{{ ref('{model_name}') }}}}" in sql
            assert f"ref('{model_name}')" in sql_body

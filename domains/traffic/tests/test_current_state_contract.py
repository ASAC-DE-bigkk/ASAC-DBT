from pathlib import Path


TRAFFIC_DIR = Path(__file__).parents[1]


def test_current_model_requires_transform_pinned_publishable_manifest_run():
    sql = (TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident_current.sql").read_text()
    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "silver_seoul_traffic_incident" in sql


def test_history_model_uses_transform_pinned_publishable_manifest_run():
    sql = (TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident.sql").read_text(encoding="utf-8")

    assert "var('traffic_snapshot_dag_run_id')" in sql


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

from pathlib import Path


TRAFFIC_DIR = Path(__file__).parents[1]


def test_current_model_requires_transform_pinned_publishable_manifest_run():
    sql = (TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident_current.sql").read_text()
    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "silver_seoul_traffic_incident" in sql


def test_history_model_uses_transform_pinned_publishable_manifest_run():
    sql = (TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident.sql").read_text(encoding="utf-8")

    assert "var('traffic_snapshot_dag_run_id')" in sql


def test_current_snapshot_contract_test_uses_transform_pinned_run():
    sql = (TRAFFIC_DIR / "tests/assert_traffic_current_pinned_publishable_run.sql").read_text()

    assert "var('traffic_snapshot_dag_run_id')" in sql


def test_current_snapshot_contract_keeps_pinned_correctness_and_grace_freshness_separate():
    sql = (
        TRAFFIC_DIR / "tests/assert_traffic_current_pinned_publishable_run.sql"
    ).read_text(encoding="utf-8").lower()
    compact_sql = " ".join(sql.split())

    assert "partition by dag_run_id" in sql
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


def test_gold_summary_reads_current_incidents_not_history():
    sql = (TRAFFIC_DIR / "models/gold/gold_traffic_incident_summary.sql").read_text()
    assert "silver_seoul_traffic_incident_current" in sql

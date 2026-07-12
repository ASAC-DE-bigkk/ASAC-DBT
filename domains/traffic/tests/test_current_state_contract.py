from pathlib import Path


TRAFFIC_DIR = Path(__file__).parents[1]


def test_current_model_requires_transform_pinned_publishable_manifest_run():
    sql = (TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident_current.sql").read_text()
    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "silver_seoul_traffic_incident" in sql


def test_current_snapshot_contract_test_uses_transform_pinned_run():
    sql = (TRAFFIC_DIR / "tests/assert_traffic_current_pinned_publishable_run.sql").read_text()

    assert "var('traffic_snapshot_dag_run_id')" in sql


def test_gold_summary_reads_current_incidents_not_history():
    sql = (TRAFFIC_DIR / "models/gold/gold_traffic_incident_summary.sql").read_text()
    assert "silver_seoul_traffic_incident_current" in sql

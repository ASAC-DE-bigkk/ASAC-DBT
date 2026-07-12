from pathlib import Path


TRAFFIC_DIR = Path(__file__).parents[1]


def test_current_model_uses_latest_publishable_manifest_run():
    sql = (TRAFFIC_DIR / "models/silver/silver_seoul_traffic_incident_current.sql").read_text()
    assert "collection_run_manifest" in sql
    assert "status = 'SUCCESS'" in sql
    assert "is_publishable" in sql
    assert "order by cast(event_at as timestamp(6)) desc" in sql
    assert "silver_seoul_traffic_incident" in sql


def test_gold_summary_reads_current_incidents_not_history():
    sql = (TRAFFIC_DIR / "models/gold/gold_traffic_incident_summary.sql").read_text()
    assert "silver_seoul_traffic_incident_current" in sql

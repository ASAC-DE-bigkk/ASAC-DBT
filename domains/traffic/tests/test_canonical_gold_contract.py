from pathlib import Path


TRAFFIC_DIR = Path(__file__).resolve().parents[1]
MODEL_PATH = (
    TRAFFIC_DIR
    / "models"
    / "gold"
    / "gold_traffic_incident_current_by_admin_dong_hourly.sql"
)


def test_canonical_gold_declares_snapshot_and_graph_dependencies():
    assert MODEL_PATH.exists(), f"missing canonical Gold model: {MODEL_PATH}"

    sql = MODEL_PATH.read_text(encoding="utf-8")

    assert "var('traffic_snapshot_dag_run_id')" in sql
    assert "ref('silver_seoul_traffic_incident_current')" in sql
    assert "ref('asac_axes', 'dim_admin_dong')" in sql
    assert "source('traffic_bronze', 'collection_run_manifest')" in sql
    assert "source('traffic_bronze', 'seoul_traffic_incident_request_audit')" in sql
    assert "source('traffic_bronze', 'seoul_traffic_incident')" in sql

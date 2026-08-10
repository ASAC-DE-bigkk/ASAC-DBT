from __future__ import annotations

from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCES = PROJECT_ROOT / "models" / "traffic" / "sources.yml"
LINK_SCOPE = (
    PROJECT_ROOT
    / "macros"
    / "traffic"
    / "traffic_link_reference_scope.sql"
)


def compact(value: str) -> str:
    return " ".join(value.lower().split())


def _traffic_source_tables() -> dict[str, dict]:
    document = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    source = next(
        item for item in document["sources"] if item["name"] == "traffic_bronze"
    )
    return {table["name"]: table for table in source["tables"]}


def _column_names(table: dict) -> set[str]:
    return {column["name"] for column in table.get("columns", [])}


def test_link_reference_sources_declare_three_bronze_relations():
    tables = _traffic_source_tables()

    expected_identifiers = {
        "seoul_traffic_link_info": "bronze_seoul_traffic_link_info",
        "seoul_traffic_link_vertex": "bronze_seoul_traffic_link_vertex",
        "seoul_traffic_link_request_audit": (
            "bronze_seoul_traffic_link_request_audit"
        ),
    }
    for table_name, identifier in expected_identifiers.items():
        assert tables[table_name]["identifier"] == identifier


def test_link_reference_sources_keep_native_fields_and_flow_parent_lineage():
    tables = _traffic_source_tables()
    common = {
        "request_id",
        "source_id",
        "service_name",
        "request_params_json",
        "link_id",
        "raw_object_key",
        "payload_hash",
        "http_status",
        "result_code",
        "result_msg",
        "list_total_count",
        "row_count",
        "collected_at",
        "load_date",
        "dag_run_id",
    }
    assert common | {
        "road_name",
        "start_node_name",
        "end_node_name",
        "map_distance",
        "region_code",
    } <= _column_names(tables["seoul_traffic_link_info"])
    assert common | {
        "vertex_sequence",
        "grs80tm_x",
        "grs80tm_y",
    } <= _column_names(tables["seoul_traffic_link_vertex"])
    assert common <= _column_names(
        tables["seoul_traffic_link_request_audit"]
    )
    assert "parent_incident_run_id" in _column_names(
        tables["seoul_traffic_flow"]
    )
    assert "parent_incident_run_id" in _column_names(
        tables["seoul_traffic_flow_request_audit"]
    )


def test_complete_pair_macro_checks_same_run_and_actual_counts():
    sql = compact(LINK_SCOPE.read_text(encoding="utf-8"))

    assert "group by link_id, dag_run_id" in sql
    assert "service_name" in sql and "'linkinfo'" in sql
    assert "service_name" in sql and "'linkverinfo'" in sql
    assert "info_success_count = 1" in sql
    assert "vertex_success_count = 1" in sql
    assert "info_actual_count = 1" in sql
    assert "info_audit_total_count = 1" in sql
    assert "vertex_audit_row_count = vertex_audit_total_count" in sql
    assert "vertex_actual_count = vertex_audit_row_count" in sql
    assert "vertex_sequence_distinct_count = vertex_actual_count" in sql
    assert "then true else false end as is_complete" in sql

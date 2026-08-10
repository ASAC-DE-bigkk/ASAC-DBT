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
SILVER_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "silver"
INFO_SQL = SILVER_DIR / "silver_seoul_traffic_link_info.sql"
VERTEX_SQL = SILVER_DIR / "silver_seoul_traffic_link_vertex.sql"
SILVER_YAML = SILVER_DIR / "_silver.yml"
SILVER_TEST_DIR = (
    PROJECT_ROOT / "tests" / "traffic" / "transform" / "silver"
)
VERTEX_GRAIN_TEST = (
    SILVER_TEST_DIR
    / "assert_silver_seoul_traffic_link_vertex_grain_unique.sql"
)
COMPLETE_PAIR_TEST = (
    SILVER_TEST_DIR
    / "assert_silver_seoul_traffic_link_reference_complete_pair.sql"
)
REFERENCE_SQL = SILVER_DIR / "silver_seoul_traffic_link_reference.sql"
REFERENCE_GRAIN_TEST = (
    SILVER_TEST_DIR
    / "assert_silver_seoul_traffic_link_reference_grain_unique.sql"
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


def test_info_and_vertex_models_share_latest_complete_run():
    info = compact(INFO_SQL.read_text(encoding="utf-8"))
    vertex = compact(VERTEX_SQL.read_text(encoding="utf-8"))

    for sql in (info, vertex):
        assert "traffic_link_reference_attempts()" in sql
        assert "where is_complete" in sql
        assert "partition by link_id" in sql
        assert "order by attempt_collected_at desc, dag_run_id desc" in sql
        assert "winner.dag_run_id" in sql
    assert "try_cast(info.map_distance as double)" in info
    assert "nullif(trim(cast(info.road_name as varchar)), '')" in info
    assert "try_cast(vertex.vertex_sequence as integer)" in vertex
    assert "try_cast(vertex.grs80tm_x as double)" in vertex
    assert "try_cast(vertex.grs80tm_y as double)" in vertex


def test_link_reference_silver_schema_and_singular_tests_fix_the_grains():
    document = yaml.safe_load(SILVER_YAML.read_text(encoding="utf-8"))
    models = {model["name"]: model for model in document["models"]}

    assert {"silver_seoul_traffic_link_info", "silver_seoul_traffic_link_vertex"} <= (
        set(models)
    )
    info_columns = _column_names(models["silver_seoul_traffic_link_info"])
    vertex_columns = _column_names(models["silver_seoul_traffic_link_vertex"])
    assert {"link_id", "road_name", "dag_run_id", "reference_collected_at"} <= (
        info_columns
    )
    assert {
        "link_id",
        "vertex_sequence",
        "grs80tm_x",
        "grs80tm_y",
        "dag_run_id",
    } <= vertex_columns

    grain = compact(VERTEX_GRAIN_TEST.read_text(encoding="utf-8"))
    assert "group by link_id, vertex_sequence" in grain
    assert "having count(*) <> 1" in grain

    complete = compact(COMPLETE_PAIR_TEST.read_text(encoding="utf-8"))
    assert "traffic_link_reference_attempts()" in complete
    assert "silver_seoul_traffic_link_info" in complete
    assert "silver_seoul_traffic_link_vertex" in complete
    assert "vertex_actual_count <> vertex_audit_row_count" in complete


def test_reference_uses_ordered_middle_vertex_and_existing_axis_macros():
    sql = compact(REFERENCE_SQL.read_text(encoding="utf-8"))

    assert "row_number() over ( partition by link_id order by vertex_sequence )" in sql
    assert "floor((vertex_count + 1) / 2" in sql
    assert "asac_axes.tm_to_wgs84_relation" in sql
    assert "ref('asac_axes', 'seoul_admin_dong_boundary')" in sql
    assert "asac_axes.admin_dong_contains" in sql
    assert "left join" in sql
    assert "latest_attempt_dag_run_id" in sql
    assert "reference_dag_run_id" in sql


def test_reference_schema_exposes_road_location_quality_and_lineage():
    document = yaml.safe_load(SILVER_YAML.read_text(encoding="utf-8"))
    models = {model["name"]: model for model in document["models"]}
    reference = models["silver_seoul_traffic_link_reference"]
    columns = _column_names(reference)

    assert {
        "link_id",
        "road_name",
        "longitude",
        "latitude",
        "admin_dong_code",
        "admin_dong",
        "gu_code",
        "gu",
        "link_reference_quality",
        "reference_collected_at",
        "reference_dag_run_id",
        "latest_attempt_dag_run_id",
    } <= columns
    quality = next(
        column for column in reference["columns"]
        if column["name"] == "link_reference_quality"
    )
    accepted = next(
        test["accepted_values"]["arguments"]["values"]
        for test in quality["tests"]
        if isinstance(test, dict) and "accepted_values" in test
    )
    assert set(accepted) == {
        "complete",
        "missing_info",
        "missing_vertex",
        "coordinate_conversion_or_bbox_miss",
        "admin_boundary_miss",
    }

    grain = compact(REFERENCE_GRAIN_TEST.read_text(encoding="utf-8"))
    assert "group by link_id" in grain
    assert "having count(*) <> 1" in grain

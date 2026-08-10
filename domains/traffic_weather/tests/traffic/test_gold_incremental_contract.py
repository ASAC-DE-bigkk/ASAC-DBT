from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACRO_PATH = PROJECT_ROOT / "macros" / "traffic" / "traffic_flow_incremental_scope.sql"
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"
SILVER_FLOW = (
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "silver"
    / "silver_seoul_traffic_flow.sql"
)
FLOW_SCOPE = PROJECT_ROOT / "macros" / "traffic" / "traffic_flow_incremental_scope.sql"
FLOW_LATEST = GOLD_DIR / "gold_traffic_flow_link_latest.sql"
HOTSPOTS = GOLD_DIR / "gold_traffic_flow_congestion_hotspots_hourly.sql"
FLOW_LATEST_YAML = GOLD_DIR / "gold_traffic_flow_link_latest.yml"
HOTSPOTS_YAML = GOLD_DIR / "gold_traffic_flow_congestion_hotspots_hourly.yml"
GOLD_TEST_DIR = PROJECT_ROOT / "tests" / "traffic" / "transform" / "gold"
FLOW_LATEST_ANCHOR_TEST = (
    GOLD_TEST_DIR / "assert_gold_traffic_flow_link_latest_anchor_preserved.sql"
)
HOTSPOTS_ANCHOR_TEST = (
    GOLD_TEST_DIR / "assert_gold_traffic_hotspots_anchor_preserved.sql"
)

ROAD_COLUMNS = {
    "road_name": "varchar",
    "start_node_name": "varchar",
    "end_node_name": "varchar",
    "map_distance": "double",
    "representative_vertex_sequence": "integer",
    "longitude": "double",
    "latitude": "double",
    "admin_dong_code": "varchar",
    "admin_dong": "varchar",
    "gu_code": "varchar",
    "gu": "varchar",
    "link_reference_quality": "varchar",
    "link_reference_collected_at_kst": "timestamp(6)",
    "parent_incident_run_id": "varchar",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_flow_incremental_scope_macros_exist_and_use_pinned_run() -> None:
    sql = _read(MACRO_PATH)

    for macro_name in (
        "traffic_flow_snapshot_dag_run_id_sql_literal",
        "traffic_flow_changed_rows",
        "traffic_flow_changed_links",
        "traffic_flow_changed_hours",
        "traffic_flow_changed_profile_keys",
        "traffic_flow_assert_pinned_incremental_rows",
    ):
        assert f"macro {macro_name}(" in sql

    assert "var('traffic_flow_snapshot_dag_run_id', '')" in sql
    assert "ref('silver_seoul_traffic_flow')" in sql
    assert "where 1 = 0" in sql
    assert "exceptions.raise_compiler_error" in sql
    assert "no silver_seoul_traffic_flow rows for pinned traffic_flow_snapshot_dag_run_id" in sql


def test_flow_gold_models_use_required_incremental_safety_config() -> None:
    expected_unique_keys = {
        "gold_traffic_flow_link_latest.sql": "unique_key='link_id'",
        "gold_traffic_flow_change_latest.sql": "unique_key='link_id'",
        "gold_traffic_flow_congestion_hotspots_hourly.sql": "unique_key=['hour_at', 'link_id']",
        "gold_traffic_flow_link_time_profile.sql": "unique_key=['link_id', 'kst_day_of_week', 'kst_hour']",
    }

    for filename, unique_key_fragment in expected_unique_keys.items():
        sql = _read(GOLD_DIR / filename).replace('"', "'")
        assert "materialized='incremental'" in sql
        assert "incremental_strategy='merge'" in sql
        assert unique_key_fragment in sql
        assert "on_table_exists='drop'" in sql
        assert "views_enabled=false" in sql
        assert "traffic_flow_assert_pinned_incremental_rows()" in sql


def test_flow_gold_models_use_their_exact_changed_scope_macro() -> None:
    expected = {
        "gold_traffic_flow_link_latest.sql": "traffic_flow_changed_rows()",
        "gold_traffic_flow_change_latest.sql": "traffic_flow_changed_links()",
        "gold_traffic_flow_congestion_hotspots_hourly.sql": "traffic_flow_changed_hours()",
        "gold_traffic_flow_link_time_profile.sql": "traffic_flow_changed_profile_keys()",
    }

    for filename, macro_call in expected.items():
        sql = _read(GOLD_DIR / filename)
        assert macro_call in sql


def test_flow_hourly_uses_request_id_as_final_latest_tie_break() -> None:
    sql = _read(GOLD_DIR / "gold_traffic_flow_congestion_hotspots_hourly.sql")

    assert "cast(request_id as varchar) as request_id" in sql
    assert "order by observed_at_utc desc, raw_object_key desc, request_id desc" in sql


def test_flow_lineage_survives_silver_macro_and_gold() -> None:
    assert "parent_incident_run_id" in _read(SILVER_FLOW)
    assert "parent_incident_run_id" in _read(FLOW_SCOPE)

    for model, anchor_alias in (
        (FLOW_LATEST, "ranked.link_id"),
        (HOTSPOTS, "ranked_hotspots.link_id"),
    ):
        sql = _read(model)
        assert "ref('silver_seoul_traffic_link_reference')" in sql
        assert "left join" in sql.lower()
        assert "parent_incident_run_id" in sql
        assert anchor_alias in sql
        for column in ROAD_COLUMNS:
            assert column in sql


def test_flow_gold_contracts_declare_additive_road_columns_with_exact_types() -> None:
    for path in (FLOW_LATEST_YAML, HOTSPOTS_YAML):
        document = yaml.safe_load(_read(path))
        model = document["models"][0]
        columns = {
            column["name"]: column.get("data_type")
            for column in model["columns"]
        }
        for name, data_type in ROAD_COLUMNS.items():
            assert columns[name] == data_type


def test_flow_road_enrichment_keeps_existing_product_key_anchors() -> None:
    latest = _read(FLOW_LATEST_ANCHOR_TEST).lower()
    hotspots = _read(HOTSPOTS_ANCHOR_TEST).lower()

    assert "ref('silver_seoul_traffic_flow')" in latest
    assert "ref('gold_traffic_flow_link_latest')" in latest
    assert latest.count("except") >= 2
    assert "partition by link_id" in latest

    assert "ref('silver_seoul_traffic_flow')" in hotspots
    assert "ref('gold_traffic_flow_congestion_hotspots_hourly')" in hotspots
    assert hotspots.count("except") >= 2
    assert "partition by link_id, hour_at" in hotspots


def test_primary_usage_patterns_expose_human_readable_road_context() -> None:
    expected_projection = {
        "road_name",
        "start_node_name",
        "end_node_name",
        "admin_dong",
        "gu",
        "longitude",
        "latitude",
        "link_reference_quality",
    }
    for path, pattern_ids in (
        (FLOW_LATEST_YAML, {"latest_snapshot_for_link", "slowest_available_links"}),
        (HOTSPOTS_YAML, {"hotspots_for_hour"}),
    ):
        document = yaml.safe_load(_read(path))
        patterns = document["models"][0]["config"]["meta"]["serving"][
            "usage_patterns"
        ]
        by_id = {pattern["pattern_id"]: pattern for pattern in patterns}
        for pattern_id in pattern_ids:
            sql = by_id[pattern_id]["sql"].lower()
            assert all(column in sql for column in expected_projection)

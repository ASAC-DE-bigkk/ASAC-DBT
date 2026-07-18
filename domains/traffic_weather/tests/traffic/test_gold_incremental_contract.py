from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MACRO_PATH = PROJECT_ROOT / "macros" / "traffic" / "traffic_flow_incremental_scope.sql"
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"


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

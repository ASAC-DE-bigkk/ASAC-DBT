from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"
GOLD_TEST_DIR = PROJECT_ROOT / "tests" / "traffic" / "transform" / "gold"
MODEL = GOLD_DIR / "gold_traffic_road_congestion_context_current.sql"

REQUIRED_COLUMNS = (
    "product_row_id",
    "link_id",
    "road_name",
    "start_node_name",
    "end_node_name",
    "map_distance",
    "representative_vertex_sequence",
    "longitude",
    "latitude",
    "admin_dong_code",
    "admin_dong",
    "gu_code",
    "gu",
    "link_reference_quality",
    "flow_speed",
    "flow_travel_time",
    "flow_value_quality",
    "observed_at_kst",
    "collected_at_kst",
    "parent_incident_run_id",
    "congestion_rank",
    "observed_link_count",
    "hotspot_state",
    "incident_count",
    "latest_incident_type",
    "latest_incident_detail_type",
    "latest_incident_description",
    "latest_incident_occurred_at_kst",
    "latest_incident_expected_clear_at_kst",
    "incident_context_state",
    "weather_category_coverage_count",
    "weather_latest_issued_at",
    "weather_latest_collected_at",
    "tmp_value_num",
    "pop_value_num",
    "reh_value_num",
    "wsd_value_num",
    "sky_qualitative_code",
    "pty_qualitative_code",
    "is_precipitating",
    "weather_context_state",
    "flow_dag_run_id",
)


def _compact(text: str) -> str:
    return " ".join(text.lower().split())


def test_road_context_is_flow_anchored_and_context_is_left_joined() -> None:
    sql = MODEL.read_text(encoding="utf-8")
    compact = _compact(sql)

    assert "from {{ ref('gold_traffic_flow_link_latest') }}" in sql
    assert "left join hotspot" in compact
    assert "left join incident_hourly" in compact
    assert "left join weather_hourly" in compact
    assert "incident.dag_run_id = flow.parent_incident_run_id" in compact
    assert "weather.issued_at <= flow.observed_at_kst" in compact
    assert "weather_w2_grid_winner_order_key('weather')" in sql


def test_road_context_uses_exact_parent_incident_and_no_hindsight_weather() -> None:
    compact = _compact(MODEL.read_text(encoding="utf-8"))

    assert "ref('silver_seoul_traffic_incident_current')" in compact
    assert "ref('bridge_weather_admin_dong_grid')" in compact
    assert "ref('silver_kma_vilage_fcst_grid')" in compact
    assert "cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'" in compact
    assert "lower(weather.category) in ('tmp', 'pop', 'reh', 'wsd', 'sky', 'pty')" in compact
    assert "partition by flow.product_row_id, lower(weather.category)" in compact


def test_road_context_projection_is_fixed_to_the_42_product_columns() -> None:
    sql = MODEL.read_text(encoding="utf-8")
    final_projection = sql.rsplit("\nselect\n", maxsplit=1)[1].split("\nfrom flow", maxsplit=1)[0]

    for column in REQUIRED_COLUMNS:
        assert column in final_projection
    assert len(REQUIRED_COLUMNS) == 42


def test_road_context_singular_guards_cover_anchor_lineage_and_states() -> None:
    expected = {
        "assert_gold_traffic_road_context_grain_unique.sql": ("group by link_id",),
        "assert_gold_traffic_road_context_flow_anchor_preserved.sql": ("except", "except"),
        "assert_gold_traffic_road_context_incident_exact_parent.sql": (
            "matched_exact_parent",
            "parent_incident_run_id",
        ),
        "assert_gold_traffic_road_context_weather_no_hindsight.sql": (
            "weather_latest_issued_at",
            "weather_w2_grid_winner_order_key('weather')",
        ),
        "assert_gold_traffic_road_context_state_consistent.sql": (
            "incident_context_state",
            "weather_context_state",
        ),
    }

    for filename, fragments in expected.items():
        sql = (GOLD_TEST_DIR / filename).read_text(encoding="utf-8").lower()
        for fragment in fragments:
            assert fragment in sql

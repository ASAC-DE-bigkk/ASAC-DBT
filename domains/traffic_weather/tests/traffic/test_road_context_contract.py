from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = PROJECT_ROOT / "models" / "traffic" / "transform" / "gold"
GOLD_TEST_DIR = PROJECT_ROOT / "tests" / "traffic" / "transform" / "gold"
MODEL = GOLD_DIR / "gold_traffic_road_congestion_context_current.sql"
MODEL_YAML = GOLD_DIR / "gold_traffic_road_congestion_context_current.yml"
FLOW_LATEST_MODEL = GOLD_DIR / "gold_traffic_flow_link_latest.sql"
FLOW_HOTSPOT_MODEL = GOLD_DIR / "gold_traffic_flow_congestion_hotspots_hourly.sql"
PORTFOLIO_CATALOG = PROJECT_ROOT / "contracts" / "serving_gold_catalog.yml"

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


def test_flow_products_keep_speed_rows_when_link_reference_is_missing() -> None:
    for model_path in (FLOW_LATEST_MODEL, FLOW_HOTSPOT_MODEL):
        compact = _compact(model_path.read_text(encoding="utf-8"))

        assert "left join {{ ref('silver_seoul_traffic_link_reference') }} as road" in compact
        assert "coalesce(road.link_reference_quality, 'missing_info')" in compact


def test_road_context_exposes_missing_reference_as_quality_not_a_blocker() -> None:
    model = yaml.safe_load(MODEL_YAML.read_text(encoding="utf-8"))["models"][0]
    state_fields = model["config"]["meta"]["public_gold"]["quality"]["state_fields"]

    assert "missing_info" in state_fields["link_reference_quality"]["allowed_values"]
    assert "missing_info" in state_fields["link_reference_quality"]["state_explanations"]


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


def test_road_context_is_a_unique_public_serving_product() -> None:
    document = yaml.safe_load(MODEL_YAML.read_text(encoding="utf-8"))
    model = document["models"][0]

    assert model["name"] == "gold_traffic_road_congestion_context_current"
    assert model["access"] == "public"
    assert model["config"]["contract"]["enforced"] is True
    assert model["config"]["meta"]["cross_domain_gold"] is True

    serving = model["config"]["meta"]["serving"]
    assert serving["enabled"] is True
    assert serving["external"] is True
    assert serving["product_id"] == "traffic_road_congestion_context_current"
    assert serving["primary_key"] == ["product_row_id"]
    assert serving["publication_mode"] == "upsert"
    assert serving["upsert_strategy"] == "exact_set"
    assert serving["zero_policy"] == "retain_last_good"
    assert serving["event_time"] == "observed_at_kst"
    assert serving["freshness_slo_minutes"] == 90
    assert serving["shape"] == "wide"

    columns = {column["name"]: column for column in model["columns"]}
    assert list(columns) == list(REQUIRED_COLUMNS)
    assert all(column.get("data_type") for column in columns.values())
    assert all(
        isinstance(column.get("config", {}).get("meta", {}).get("nullable"), bool)
        for column in columns.values()
    )

    products = yaml.safe_load(PORTFOLIO_CATALOG.read_text(encoding="utf-8"))
    traffic_models = products["domains"]["traffic"]["serving_models"]
    assert traffic_models.count("gold_traffic_road_congestion_context_current") == 1


def test_road_context_documents_sources_and_unverified_usage_patterns() -> None:
    model = yaml.safe_load(MODEL_YAML.read_text(encoding="utf-8"))["models"][0]
    serving = model["config"]["meta"]["serving"]
    evidence = {item["source_id"]: item for item in serving["source_evidence"]}

    assert evidence["seoul_topis_traffic_info"]["source_url"].endswith(
        "/OA-13291/A/1/datasetView.do"
    )
    assert evidence["seoul_topis_link_info"]["source_url"].endswith(
        "/OA-13310/A/1/datasetView.do"
    )
    assert evidence["seoul_topis_link_vertex"]["source_url"].endswith(
        "/OA-13311/A/1/datasetView.do"
    )
    assert evidence["kma_vilage_fcst"]["source_url"] == (
        "https://www.data.go.kr/data/15084084/openapi.do"
    )
    assert {item["rights_checked_at"] for item in evidence.values()} == {
        "2026-08-10"
    }

    patterns = serving["usage_patterns"]
    assert {pattern["pattern_id"] for pattern in patterns} == {
        "road_context_for_link",
        "slowest_named_roads",
        "congested_roads_with_incident_context",
        "congested_roads_with_precipitation_context",
        "slowest_roads_in_admin_dong",
        "current_links_for_road_name",
        "slow_roads_without_incident_or_precipitation",
        "context_quality_summary",
    }
    assert all(pattern["verified_rows"] == 0 for pattern in patterns)
    assert all(
        "verified_at" not in pattern and "verified_publication_id" not in pattern
        for pattern in patterns
    )

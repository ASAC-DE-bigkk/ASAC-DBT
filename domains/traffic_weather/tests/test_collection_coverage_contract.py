from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "models" / "traffic" / "collection_state_sources.yml"
MACRO = PROJECT_ROOT / "macros" / "collection_state.sql"
TRAFFIC_MODEL = (
    PROJECT_ROOT
    / "models"
    / "traffic"
    / "transform"
    / "gold"
    / "gold_traffic_incident_expected_slot_coverage_5m.sql"
)
TRAFFIC_SCHEMA = TRAFFIC_MODEL.with_suffix(".yml")
WEATHER_MODEL = (
    PROJECT_ROOT
    / "models"
    / "weather"
    / "transform"
    / "gold"
    / "gold_weather_collection_coverage_by_issue_cycle.sql"
)
WEATHER_SCHEMA = WEATHER_MODEL.with_suffix(".yml")


def compact(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_collection_state_projects_nullable_recovery_evidence_without_schedule_generation():
    source = compact(SOURCE)
    macro = compact(MACRO)

    assert "- name: recovery_evidence_code" in source
    assert "cast(recovery_evidence_code as varchar) as recovery_evidence_code" in macro
    assert "latest.recovery_evidence_code" in macro
    assert "generate_series" not in macro
    assert "current_timestamp" not in macro


def _assert_state_only_coverage_model(path: Path, state_model: str) -> str:
    sql = compact(path)

    assert sql.count("{{ ref(") == 1
    assert f"{{{{ ref('{state_model}') }}}}" in sql
    assert "source(" not in sql
    assert "raw/" not in sql
    assert "manifest" not in sql
    assert "generate_series" not in sql
    assert "current_timestamp" not in sql
    assert "count_if(is_eligible) as eligible_expected" in sql
    assert "observed_count + source_empty_valid_count + recovered_count as covered" in sql
    assert "case when eligible_expected = 0 then cast(0.0 as double)" in sql
    assert "when eligible_expected = 0 then 'not_scheduled'" in sql
    assert "when unrecoverable > 0 then 'unrecoverable'" in sql
    assert "when pending > 0 then 'pending'" in sql
    assert "when covered = eligible_expected then 'covered'" in sql
    assert "else 'partial'" in sql

    for state_count in (
        "observed_count",
        "source_empty_valid_count",
        "collection_failed_count",
        "missing_unknown_count",
        "not_scheduled_count",
    ):
        assert f"as {state_count}" in sql

    return sql


def test_traffic_expected_slot_coverage_uses_only_traffic_state_gold_at_source_slot_grain():
    sql = _assert_state_only_coverage_model(
        TRAFFIC_MODEL,
        "gold_traffic_collection_slot_state",
    )

    assert "group by source_id, collection_slot_at" in sql


def test_weather_expected_slot_coverage_uses_kst_issue_cycle_not_naive_utc():
    sql = _assert_state_only_coverage_model(
        WEATHER_MODEL,
        "gold_weather_collection_slot_state",
    )

    assert "{{ asac_axes.utc_to_kst('collection_slot_at') }}" in sql
    assert "as issued_at_kst" in sql
    assert "group by source_id, issued_at_kst" in sql


def test_coverage_models_are_support_only_control_plane_products():
    for schema in (TRAFFIC_SCHEMA, WEATHER_SCHEMA):
        document = compact(schema)
        assert "collection_coverage_product: true" in document
        assert "support_only: true" in document
        assert "serving_publication: false" in document

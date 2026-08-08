from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MACRO = PROJECT_ROOT / "macros" / "collection_state.sql"


def compact(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_common_projection_macro_has_deterministic_latest_event_contract():
    assert MACRO.is_file(), f"missing collection state macro: {MACRO}"
    sql = compact(MACRO)
    assert "macro collection_slot_latest_state(expected_relation, event_relation)" in sql
    assert "partition by cast(expected_slot_id as varchar)" in sql
    assert "order by cast(event_at as timestamp(6)) desc, cast(event_id as varchar) desc" in sql
    assert "row_number() over" in sql
    assert "event_state_tie_count" in sql
    assert "event_state_tie_count = 1" not in sql.split("macro collection_slot_state_assertions", 1)[0]


def test_projection_distinguishes_unscheduled_and_missing_slots_without_making_up_rows():
    sql = compact(MACRO)
    assert "not_scheduled" in sql
    assert "missing_unknown" in sql
    assert "missing_event" in sql
    assert "from {{ expected_relation }}" in sql
    assert "from {{ event_relation }}" in sql
    assert "generate_series" not in sql
    assert "current_timestamp" not in sql


def test_projection_preserves_collection_and_recovery_state_separately():
    sql = compact(MACRO)
    assert "collection_state" in sql
    assert "recovery_state" in sql
    assert "recovery_class" in sql
    assert "gap_reason_code" in sql
    assert "collection_state in ('observed', 'source_empty_valid')" in sql
    assert "recovery_state = 'recovered'" in sql


def test_state_assertion_macro_is_fail_closed_for_enums_combinations_and_ties():
    sql = compact(MACRO)
    assertion = sql.split("macro collection_slot_state_assertions", 1)[1]
    assert "macro collection_slot_state_assertions(relation, expected_domain)" in sql
    assert "count(*) over ( partition by expected_slot_id ) as expected_slot_id_count" in assertion
    assert "expected_slot_id_count <> 1" in assertion
    assert "domain is null" in assertion
    assert "domain <> '{{ expected_domain }}'" in assertion
    assert "source_id is null" in assertion
    assert "collection_state not in" in assertion
    assert "recovery_state not in" in assertion
    assert "recovery_class not in" in assertion
    assert "gap_reason_code" in assertion
    assert "event_state_tie_count <> 1" in assertion
    assert "recovery_state = 'recovered'" in assertion
    assert "recovery_class = 'none'" in assertion


def test_projection_macro_has_no_environment_or_serving_side_effects():
    sql = compact(MACRO)
    assert "env_var(" not in sql
    assert "target." not in sql
    assert "insert into" not in sql
    assert "delete from" not in sql
    assert "merge into" not in sql

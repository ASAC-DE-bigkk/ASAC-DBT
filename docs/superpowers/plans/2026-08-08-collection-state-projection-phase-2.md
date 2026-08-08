# Collection State Projection Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a common dbt macro that projects the latest collection state for each `expected_slot_id` from materialized expected-slot and append-only event relations.

**Architecture:** The macro accepts two already-materialized Iceberg relations and never creates a schedule or reads Airflow/R2 directly. It ranks events deterministically, exposes tie evidence instead of silently hiding conflicts, fills an expected slot with `missing_unknown/pending/none` when no event exists, and keeps `collection_state` separate from recovery state. A second assertion macro validates the closed state sets and allowed state combinations; domain coverage models and D1 serving remain out of scope.

**Tech Stack:** dbt Core 1.10, Trino SQL, Jinja macros, pytest static contract tests.

## Global Constraints

- Do not replace `bronze_collection_run_manifest`, Traffic snapshot receipts, raw manifests, D1 Publisher, or existing domain models.
- Do not generate schedule/date spines in dbt; the expected-slot relation is the source of truth.
- Use `expected_slot_id` as the projection key and `event_at DESC, event_id DESC` as the deterministic ordering.
- Preserve `collection_state` and `gap_reason_code` when recovery reaches `recovered`.
- Invalid enum values, invalid state combinations, missing required gap reasons, and event timestamp ties must be returned by the assertion query.
- Do not add dependencies, network calls, or target-specific database/schema guards.

---

### Task 1: Contract tests for the common projection macro

**Files:**

- Create: `domains/traffic_weather/tests/test_collection_state_projection_contract.py`
- Test target: `domains/traffic_weather/macros/collection_state.sql`

**Interfaces:**

- The test names the required public macros `collection_slot_latest_state(expected_relation, event_relation)` and `collection_slot_state_assertions(relation)` before those macros exist.

- [x] **Step 1: Write the failing tests**

```python
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
    assert "macro collection_slot_state_assertions(relation)" in sql
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
```

- [x] **Step 2: Run the tests to verify RED**

Run: `pytest -q domains/traffic_weather/tests/test_collection_state_projection_contract.py`

Expected: FAIL because `domains/traffic_weather/macros/collection_state.sql` does not exist.

### Task 2: Implement deterministic state projection and assertion SQL

**Files:**

- Create: `domains/traffic_weather/macros/collection_state.sql`

**Interfaces:**

- Produces `collection_slot_latest_state(expected_relation, event_relation)`, a SELECT statement with one projected row per expected slot.
- Produces `collection_slot_state_assertions(relation)`, a zero-row-on-validity SELECT suitable for a dbt singular test.

- [x] **Step 1: Add the minimum projection macro**

```sql
{% macro collection_slot_latest_state(expected_relation, event_relation) -%}
with expected_slots as (
    select
        cast(expected_slot_id as varchar) as expected_slot_id,
        cast(contract_version as varchar) as contract_version,
        cast(domain as varchar) as domain,
        cast(collection_contract_id as varchar) as collection_contract_id,
        cast(source_id as varchar) as source_id,
        cast(collection_slot_at as timestamp(6)) as collection_slot_at,
        cast(grain_key as varchar) as grain_key,
        cast(grain_json as varchar) as grain_json,
        cast(schedule_version as varchar) as schedule_version,
        cast(scheduled_at as timestamp(6)) as scheduled_at,
        cast(deadline_at as timestamp(6)) as deadline_at,
        cast(is_scheduled as boolean) as is_scheduled,
        cast(recovery_boundary_type as varchar) as recovery_boundary_type,
        cast(recovery_boundary as varchar) as recovery_boundary,
        cast(declared_at as timestamp(6)) as declared_at,
        cast(declared_by as varchar) as declared_by
    from {{ expected_relation }}
), ranked_events as (
    select
        cast(event_id as varchar) as event_id,
        cast(expected_slot_id as varchar) as expected_slot_id,
        cast(event_type as varchar) as event_type,
        cast(collection_state as varchar) as event_collection_state,
        cast(recovery_state as varchar) as event_recovery_state,
        cast(recovery_class as varchar) as event_recovery_class,
        cast(gap_reason_code as varchar) as event_gap_reason_code,
        cast(dag_id as varchar) as dag_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(task_id as varchar) as task_id,
        cast(raw_manifest_key as varchar) as raw_manifest_key,
        cast(raw_object_count as bigint) as raw_object_count,
        cast(row_count as bigint) as row_count,
        cast(source_result_code as varchar) as source_result_code,
        cast(recovery_run_id as varchar) as recovery_run_id,
        cast(recovered_at as timestamp(6)) as recovered_at,
        cast(event_at as timestamp(6)) as event_at,
        count(*) over (
            partition by cast(expected_slot_id as varchar), cast(event_at as timestamp(6))
        ) as event_state_tie_count,
        row_number() over (
            partition by cast(expected_slot_id as varchar)
            order by cast(event_at as timestamp(6)) desc, cast(event_id as varchar) desc
        ) as event_rank
    from {{ event_relation }}
), latest_events as (
    select * from ranked_events where event_rank = 1
), projected as (
    select
        expected.*,
        latest.event_id,
        latest.event_type,
        latest.dag_id,
        latest.dag_run_id,
        latest.task_id,
        latest.raw_manifest_key,
        latest.raw_object_count,
        latest.row_count,
        latest.source_result_code,
        latest.recovery_run_id,
        latest.recovered_at,
        latest.event_at,
        coalesce(latest.event_state_tie_count, 1) as event_state_tie_count,
        case
            when not coalesce(expected.is_scheduled, false) then 'not_scheduled'
            when latest.event_id is null then 'missing_unknown'
            else latest.event_collection_state
        end as collection_state,
        case
            when not coalesce(expected.is_scheduled, false) then 'not_required'
            when latest.event_id is null then 'pending'
            else coalesce(latest.event_recovery_state, 'pending')
        end as recovery_state,
        case
            when not coalesce(expected.is_scheduled, false) then 'none'
            when latest.event_id is null then 'none'
            else coalesce(latest.event_recovery_class, 'none')
        end as recovery_class,
        case
            when not coalesce(expected.is_scheduled, false) then cast(null as varchar)
            when latest.event_id is null then 'missing_event'
            else latest.event_gap_reason_code
        end as gap_reason_code
    from expected_slots as expected
    left join latest_events as latest
      on expected.expected_slot_id = latest.expected_slot_id
)
select * from projected
{%- endmacro %}
```

- [x] **Step 2: Add the fail-closed assertion macro**

```sql
{% macro collection_slot_state_assertions(relation) -%}
select *
from {{ relation }}
where collection_state not in (
          'observed', 'source_empty_valid', 'collection_failed',
          'not_scheduled', 'missing_unknown'
      )
   or recovery_state not in ('not_required', 'pending', 'recovered', 'unrecoverable')
   or recovery_class not in (
          'raw_replay', 'historical_query', 'rolling_window',
          'full_refresh', 'next_snapshot_diff', 'none'
      )
   or event_state_tie_count <> 1
   or (
          collection_state in ('collection_failed', 'missing_unknown')
          and nullif(trim(cast(gap_reason_code as varchar)), '') is null
      )
   or (
          collection_state in ('observed', 'source_empty_valid', 'not_scheduled')
          and (recovery_state <> 'not_required' or recovery_class <> 'none')
      )
   or (
          recovery_state = 'recovered'
          and (
              collection_state not in ('collection_failed', 'missing_unknown')
              or recovery_class = 'none'
          )
      )
   or (
          recovery_state = 'unrecoverable'
          and (
              collection_state not in ('collection_failed', 'missing_unknown')
              or recovery_class <> 'none'
          )
      )
{%- endmacro %}
```

- [x] **Step 3: Run the focused contract tests**

Run: `pytest -q domains/traffic_weather/tests/test_collection_state_projection_contract.py`

Expected: PASS.

### Task 3: Parse and regression verification

**Files:**

- No additional production files.

- [x] **Step 1: Parse the combined Traffic/Weather dbt project**

Run: `dbt parse --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev`

Expected: exit code 0; macro Jinja syntax loads without a warehouse connection.

- [x] **Step 2: Run the complete existing Python contract suite**

Run: `pytest -q domains/traffic_weather/tests`

Expected: all pre-existing and new static contracts pass; any environment-only failures are recorded with their exact reason.

- [x] **Step 3: Run whitespace and diff checks**

Run: `git diff --check`

Expected: exit code 0.

- [ ] **Step 4: Commit only Phase 2 paths**

```bash
git add domains/traffic_weather/macros/collection_state.sql domains/traffic_weather/tests/test_collection_state_projection_contract.py docs/superpowers/plans/2026-08-08-collection-state-projection-phase-2.md
git commit -m "feat(dbt): collection slot state projection macro 추가"
```

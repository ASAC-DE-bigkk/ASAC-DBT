# COALESCED Snapshot Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Traffic·Weather DBT가 `COALESCED`로 전이된 Bronze snapshot을 이전 `SUCCESS` history 때문에 다시 소비하지 않고, Weather도 Airflow가 전달한 exact snapshot만 변환하도록 만든다.

**Architecture:** append-only manifest에서 source/run별 최신 상태를 결정하는 공용 macro를 만든다. 모든 normal transform consumer는 이 macro의 결과에만 `SUCCESS + is_publishable` gate와 exact snapshot var를 적용한다. Weather W2 repair는 cutoff-as-of 계약을 갖고 있으므로 변경하지 않는다.

**Tech Stack:** dbt Core/Trino SQL, Jinja macros, pytest static contract tests, Docker `elt-infra-airflow:local`

## Global Constraints

- 기준 브랜치는 `origin/dev`이며 ASAC-DBT #210에 연결한다.
- `COALESCED`는 Bronze manifest 상태 이벤트이며 Bronze payload, raw path, dedup grain을 변경하지 않는다.
- Traffic pinned snapshot/recovery isolation과 Weather W2 cutoff-as-of semantics를 변경하지 않는다.
- Weather normal transform은 `weather_snapshot_dag_run_id` 없이는 fallback하지 않는다.
- prod catalog/schema, external API, R2 object write는 사용하지 않는다.

---

### Task 1: 최신 manifest 상태 macro를 RED-GREEN으로 고정

**Files:**

- Create: `domains/traffic_weather/macros/manifest_state.sql`
- Create: `domains/traffic_weather/tests/test_manifest_latest_state_contract.py`

**Interfaces:**

- Produces: `latest_manifest_run_state(source_name, table_name, source_id)` SQL relation.
- Guarantees: source/run별 최신 state만 반환하며 exact latest state tie는 반환하지 않는다.

- [ ] **Step 1: failing static test를 작성한다.**

```python
def test_latest_manifest_macro_resolves_state_before_publishable_gate() -> None:
    macro = read(MACRO_PATH)
    assert "partition by cast(source_id as varchar), cast(dag_run_id as varchar)" in macro
    assert "order by manifest_event_at_utc desc, collection_dag_id desc" in macro
    assert "manifest_state_tie_count = 1" in macro
    assert "manifest_status = 'SUCCESS'" not in macro
```

- [ ] **Step 2: RED를 확인한다.**

Run: `python -m pytest domains/traffic_weather/tests/test_manifest_latest_state_contract.py -q`

Expected: `manifest_state.sql`가 없어 실패.

- [ ] **Step 3: 최소 macro를 작성한다.**

```sql
{% macro latest_manifest_run_state(source_name, table_name, expected_source_id) -%}
select *
from (
    select
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(dag_id as varchar) as collection_dag_id,
        cast(status as varchar) as manifest_status,
        cast(is_publishable as boolean) as is_publishable,
        cast(event_at as timestamp(6)) as manifest_event_at_utc,
        count(*) over (
            partition by
                cast(source_id as varchar),
                cast(dag_run_id as varchar),
                cast(event_at as timestamp(6)),
                cast(dag_id as varchar)
        ) as manifest_state_tie_count,
        row_number() over (
            partition by cast(source_id as varchar), cast(dag_run_id as varchar)
            order by cast(event_at as timestamp(6)) desc, cast(dag_id as varchar) desc
        ) as manifest_row_num
    from {{ source(source_name, table_name) }}
    where cast(source_id as varchar) = '{{ expected_source_id }}'
) as manifest_state
where manifest_row_num = 1
  and manifest_state_tie_count = 1
{%- endmacro %}
```

- [ ] **Step 4: GREEN을 확인한다.**

Run: `python -m pytest domains/traffic_weather/tests/test_manifest_latest_state_contract.py -q`

Expected: PASS.

### Task 2: Traffic·Weather transform consumer를 macro와 exact var에 연결

**Files:**

- Modify: `models/weather/special/silver/silver_kma_vilage_fcst_observation.sql`
- Modify: `models/weather/transform/silver/silver_kma_vilage_fcst.sql`
- Modify: `models/traffic/transform/silver/silver_seoul_traffic_incident.sql`
- Modify: `models/traffic/transform/silver/silver_seoul_traffic_incident_current.sql`
- Modify: `models/traffic/transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.sql`
- Modify: `models/traffic/transform/gold/gold_traffic_incident_summary.sql`
- Modify: `models/traffic/recovery/silver/recovery_silver_seoul_traffic_incident.sql`
- Modify: `tests/traffic/transform/silver/assert_silver_traffic_uses_publishable_runs.sql`
- Modify: `tests/weather/transform/silver/assert_silver_kma_uses_publishable_runs.sql`
- Modify: `tests/traffic/transform/silver/assert_traffic_current_pinned_publishable_run.sql`
- Modify: `tests/traffic/transform/silver/assert_silver_traffic_latest_publishable_record.sql`
- Modify: `tests/traffic/test_current_state_contract.py`
- Modify: `tests/test_manifest_latest_state_contract.py`

**Interfaces:**

- Consumes: `latest_manifest_run_state(source_name, table_name, expected_source_id)`, `traffic_snapshot_dag_run_id`, `weather_snapshot_dag_run_id`.
- Produces: only latest `SUCCESS + is_publishable` exact snapshot rows for normal transforms.

- [ ] **Step 1: all normal consumer가 macro와 Weather var를 요구한다는 failing test를 추가한다.**

```python
for path in NORMAL_CONSUMER_PATHS:
    assert "latest_manifest_run_state" in read(path)

weather_sql = read(WEATHER_OBSERVATION)
assert "var('weather_snapshot_dag_run_id')" in weather_sql
assert "cast(dag_run_id as varchar) = '{{ snapshot_dag_run_id" in weather_sql
```

- [ ] **Step 2: RED를 확인한다.**

Run: `python -m pytest domains/traffic_weather/tests/test_manifest_latest_state_contract.py -q`

Expected: normal consumer의 raw `SUCCESS` prefilter와 Weather var 미소비 때문에 FAIL.

- [ ] **Step 3: CTE를 latest-state → publishable → exact-snapshot 순서로 바꾼다.**

```sql
with latest_manifest_state as (
    {{ latest_manifest_run_state('weather_bronze', 'collection_run_manifest', 'kma_vilage_fcst') }}
),
publishable_runs as (
    select dag_run_id
    from latest_manifest_state
    where manifest_status = 'SUCCESS'
      and is_publishable
      and dag_run_id = '{{ snapshot_dag_run_id | replace("'", "''") }}'
)
```

- [ ] **Step 4: singular tests도 동일 macro의 effective state를 join하게 바꾼다.**

```sql
with latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident') }}
),
publishable_runs as (
    select dag_run_id
    from latest_manifest_state
    where manifest_status = 'SUCCESS' and is_publishable
)
```

- [ ] **Step 5: GREEN을 확인한다.**

Run: `python -m pytest domains/traffic_weather/tests -q`

Expected: `50 passed, 4 skipped` 이상이며 새 contract test 포함 PASS.

### Task 3: dbt parse/compile과 DAG 통합 contract를 검증

**Files:**

- Modify: `docs/superpowers/specs/2026-07-15-coalesced-snapshot-contract-design.md`
- Modify: `docs/superpowers/plans/2026-07-15-coalesced-snapshot-contract.md`

- [ ] **Step 1: latest DBT worktree에서 dependencies를 설치한다.**

Run: `docker run --rm -v "C:/Users/Dell3571/Desktop/Projects/ask-seoul-worktrees/dbt-210-coalesced-snapshot-contract:/workspace" -w /workspace/domains/traffic_weather elt-infra-airflow:local /home/airflow/dbt-venv/bin/dbt deps --profiles-dir .`

Expected: local `asac_axes` package resolution success.

- [ ] **Step 2: both vars를 포함한 parse/compile을 실행한다.**

Run: `docker run --rm -v "C:/Users/Dell3571/Desktop/Projects/ask-seoul-worktrees/dbt-210-coalesced-snapshot-contract:/workspace" -w /workspace/domains/traffic_weather elt-infra-airflow:local /home/airflow/dbt-venv/bin/dbt parse --target dev --profiles-dir . --vars '{"traffic_snapshot_dag_run_id":"contract-snapshot","weather_snapshot_dag_run_id":"contract-snapshot"}'`

Expected: compile error 없이 manifest 생성.

- [ ] **Step 3: selected static/Python tests와 target-image DAG import test를 실행한다.**

Run: `python -m pytest domains/traffic_weather/tests -q` 및 ASAC-DAG Traffic/Weather tests.

Expected: all selected tests PASS.

- [ ] **Step 4: 결과를 spec/PR 본문에 기록하고 review를 요청한다.**

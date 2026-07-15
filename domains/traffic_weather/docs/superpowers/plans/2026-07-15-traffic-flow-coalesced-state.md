# Traffic Flow COALESCED 최신 상태 보강 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Traffic Flow Silver가 append-only manifest의 과거 `SUCCESS`를 부활시키지 않게 하고, Flow Gold가 current incident 행을 누락하거나 증식하지 않음을 계약으로 고정한다.

**Architecture:** 기존 `latest_manifest_run_state` macro를 Flow Silver의 manifest 입력에도 적용한 뒤 exact `traffic_flow_snapshot_dag_run_id`를 gate한다. `gold_traffic_incident_x_flow`의 incident-left-join 구조는 변경하지 않고 singular dbt test로 입력 incident와 결과의 cardinality를 비교한다.

**Tech Stack:** dbt Core 1.10, Trino SQL, Jinja macro, pytest static contract tests

## Global Constraints

- 기준은 ASAC-DBT `origin/dev@1fd765188d79aedab798e5f3e8734ef3f1e4b724`이며 Issue #214에 연결한다.
- `traffic_flow_snapshot_dag_run_id` pinning, `['link_id', 'dag_run_id']` incremental grain, 30분 lookback을 변경하지 않는다.
- Flow snapshot이 없는 transform의 기존 optional 동작을 유지한다.
- `gold_traffic_incident_x_flow`는 incident를 driving relation으로 유지하고 unmatched row를 `missing_flow`로 보존한다.
- prod catalog/schema, R2 object, 외부 API는 수정하지 않는다.

---

### Task 1: Flow Silver를 latest manifest state 계약에 포함

**Files:**

- Modify: `domains/traffic_weather/tests/test_manifest_latest_state_contract.py`
- Modify: `domains/traffic_weather/models/traffic/transform/silver/silver_seoul_traffic_flow.sql`

**Interfaces:**

- Consumes: `latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_flow')`와 `traffic_flow_snapshot_dag_run_id`.
- Produces: pin된 run의 최신 상태가 `SUCCESS AND is_publishable`인 경우에만 Flow Bronze rows를 선택하는 Silver relation.

- [ ] **Step 1: Flow Silver를 `PUBLISHABLE_INPUT_CONSUMERS`에 추가한다.**

```python
PROJECT_ROOT
/ "models"
/ "traffic"
/ "transform"
/ "silver"
/ "silver_seoul_traffic_flow.sql"
```

- [ ] **Step 2: RED를 확인한다.**

Run: `python -m pytest domains/traffic_weather/tests/test_manifest_latest_state_contract.py::test_publishable_input_consumers_gate_the_latest_manifest_state -q`

Expected: `silver_seoul_traffic_flow.sql`에 `latest_manifest_run_state(`가 없어 FAIL.

- [ ] **Step 3: raw manifest query를 latest-state macro gate로 교체한다.**

```sql
with latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_flow') }}
),

publishable_run as (
    select distinct dag_run_id
    from latest_manifest_state
    where manifest_status = 'SUCCESS'
      and is_publishable
      and dag_run_id = '{{ flow_snapshot_dag_run_id | replace("'", "''") }}'
)
```

- [ ] **Step 4: GREEN과 Traffic/Weather static 회귀를 확인한다.**

Run: `python -m pytest domains/traffic_weather/tests/test_manifest_latest_state_contract.py domains/traffic_weather/tests/traffic domains/traffic_weather/tests/weather -q`

Expected: 새 소비자 계약과 기존 Traffic/Weather contract가 모두 PASS.

### Task 2: Flow Gold incident cardinality를 singular test로 고정

**Files:**

- Create: `domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_incident_x_flow_preserves_incidents.sql`
- Modify: `domains/traffic_weather/tests/traffic/test_canonical_gold_contract.py`

**Interfaces:**

- Consumes: `ref('gold_traffic_incident_x_flow')`, `ref('silver_seoul_traffic_incident_current')`.
- Produces: 두 relation의 전체 행 수와 distinct `source_record_id` 수가 다르면 행을 반환하는 singular data test.

- [ ] **Step 1: 새 singular test 파일 존재와 두 ref를 요구하는 static test를 작성한다.**

```python
assert "ref('gold_traffic_incident_x_flow')" in sql
assert "ref('silver_seoul_traffic_incident_current')" in sql
assert "gold_row_count <> incident_row_count" in sql
assert "gold_incident_count <> incident_incident_count" in sql
```

- [ ] **Step 2: RED를 확인한다.**

Run: `python -m pytest domains/traffic_weather/tests/traffic/test_canonical_gold_contract.py -q`

Expected: singular test 파일이 없어 FAIL.

- [ ] **Step 3: cardinality mismatch만 반환하는 최소 SQL을 작성한다.**

```sql
with incident_counts as (
    select count(*) as incident_row_count,
           count(distinct source_record_id) as incident_incident_count
    from {{ ref('silver_seoul_traffic_incident_current') }}
),
gold_counts as (
    select count(*) as gold_row_count,
           count(distinct source_record_id) as gold_incident_count
    from {{ ref('gold_traffic_incident_x_flow') }}
)
select *
from incident_counts cross join gold_counts
where gold_row_count <> incident_row_count
   or gold_incident_count <> incident_incident_count
```

- [ ] **Step 4: GREEN과 parse를 확인한다.**

Run: `python -m pytest domains/traffic_weather/tests/traffic/test_canonical_gold_contract.py -q`

Run: `dbt parse --no-partial-parse --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather --target dev --vars '{traffic_snapshot_dag_run_id: contract, traffic_flow_snapshot_dag_run_id: contract, weather_snapshot_dag_run_id: contract}'`

Expected: static test와 dbt parse가 PASS.

### Task 3: dev 데이터 계약과 통합 배포 검증

**Files:**

- No production file changes.

**Interfaces:**

- Consumes: 최신 publishable Traffic incident/flow와 Weather snapshot run IDs.
- Produces: selector별 run/test 결과와 Traffic/Weather Gold consistency evidence.

- [ ] **Step 1: Traffic/Weather selector run/test를 exact snapshot vars로 실행한다.**
- [ ] **Step 2: Flow Gold cardinality singular test와 기존 Traffic/Weather count tests를 실행한다.**
- [ ] **Step 3: PR을 `dev`에 merge한 뒤 clean detached runtime을 최신 `origin/dev`로 갱신한다.**
- [ ] **Step 4: DAG+DBT를 함께 재배포하고 Asset smoke, COALESCED 제외, Gold consistency, schedule을 확인한다.**

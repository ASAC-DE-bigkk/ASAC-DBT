# Weather W2 Canonical Contract Cadence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Weather canonical의 매 실행 검증을 영향 grain으로 제한하고, 매일 09:15 KST에 전체 10개 계약을 별도 audit하여 D1 배포 전 stale winner가 없는 상태를 보장한다.

**Architecture:** 기존 latest-grid-record 테스트는 snapshot run이 영향을 준 product grain만 검사하는 routine 계약으로 바꾼다. 동일 winner·manifest 의미를 사용하는 full-history 테스트와 read-only Airflow audit DAG를 추가한다. 7/9 용신동 stale winner 144건은 기존 staged recovery로 정합화한 뒤 routine/full 계약을 모두 통과시킨다.

**Tech Stack:** dbt 1.10, Trino 482, Iceberg, Airflow 3.2, Python 3.11, pytest

## Global Constraints

- dev 대상은 `iceberg_dev.weather`이며 canonical revision은 `2025-04-01`이다.
- canonical grain은 `(admin_dong_code, forecast_at, category)`이다.
- 최신 manifest 상태가 `SUCCESS`이고 `is_publishable=true`인 run만 winner 후보가 된다.
- `COALESCED` run은 winner 후보에서 제외한다.
- routine 검증은 `weather_snapshot_dag_run_id`가 없으면 fail-closed 한다.
- full audit DAG는 매일 `09:15 Asia/Seoul`, `max_active_runs=1`, `trino_weather_heavy` pool 1 slot로 실행한다.
- root `.airflowignore`은 수정하지 않는다.
- D1 실제 write, Traffic serving, 비담당 도메인 파일은 수정하지 않는다.
- 커밋은 경로를 명시하며 개인 기록 MD와 생성된 `target/`, `logs/`, `dbt_packages/`를 포함하지 않는다.

---

### Task 1: Routine 영향 grain 계약과 Full-history 계약 분리

**Files:**
- Modify: `domains/traffic_weather/tests/weather/special/assert_gold_weather_forecast_by_admin_dong_latest_grid_record.sql`
- Create: `domains/traffic_weather/tests/weather/special/assert_gold_weather_forecast_by_admin_dong_latest_grid_record_full.sql`
- Modify: `domains/traffic_weather/selectors.yml`
- Modify: `domains/traffic_weather/tests/weather/test_weather_w2_canonical_selectors.py`
- Modify: `domains/traffic_weather/tests/weather/test_weather_w2_repair_contract.py`

**Interfaces:**
- Consumes: dbt var `weather_snapshot_dag_run_id: str`, `latest_manifest_run_state`, `weather_w2_gold_candidate_row`, `weather_w2_grid_winner_order_key`.
- Produces: selectors `ask_seoul_weather_w2_canonical_contracts`와 `ask_seoul_weather_w2_canonical_full_contracts`.

- [ ] **Step 1: selector와 SQL 구조의 실패 테스트 작성**

`test_weather_w2_canonical_selectors.py`에 routine selector가 fast SQL을, full selector가 기존 9개 계약과 full SQL을 소유하는지 검사한다.

```python
LATEST_GRID_FAST_PATH = (
    "tests/weather/special/"
    "assert_gold_weather_forecast_by_admin_dong_latest_grid_record.sql"
)
LATEST_GRID_FULL_PATH = (
    "tests/weather/special/"
    "assert_gold_weather_forecast_by_admin_dong_latest_grid_record_full.sql"
)

def test_canonical_full_contract_selector_replaces_fast_latest_record():
    selectors = _selectors_by_name()
    routine = _path_criteria(selectors["ask_seoul_weather_w2_canonical_contracts"])
    full = _path_criteria(selectors["ask_seoul_weather_w2_canonical_full_contracts"])
    assert LATEST_GRID_FAST_PATH in routine
    assert LATEST_GRID_FULL_PATH not in routine
    assert LATEST_GRID_FAST_PATH not in full
    assert LATEST_GRID_FULL_PATH in full
    assert len(routine) == len(full) == 10
```

`test_weather_w2_repair_contract.py`에는 fast SQL이 snapshot var와 affected key CTE를 요구하고, full SQL이 snapshot var 없이 전체 publishable 후보를 집계하는지 검사한다.

```python
def test_latest_grid_record_routine_contract_scopes_to_snapshot_affected_keys():
    compacted = compact(read(W2_LATEST_GRID_RECORD_TEST))
    assert "var('weather_snapshot_dag_run_id'" in compacted
    assert "affected_product_keys as" in compacted
    assert "inner join affected_product_keys" in compacted
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest domains/traffic_weather/tests/weather/test_weather_w2_canonical_selectors.py domains/traffic_weather/tests/weather/test_weather_w2_repair_contract.py -q
```

Expected: full selector와 affected-key CTE 부재로 FAIL.

- [ ] **Step 3: full SQL 분리와 routine 영향 grain 구현**

full SQL은 현재 grouped `max_by` 구현과 최신 publishable manifest join을 유지한다. routine SQL은 다음 순서로 좁힌다.

```sql
snapshot_grid_keys as (
    select distinct nx, ny, forecast_at, category
    from {{ ref('silver_kma_vilage_fcst_grid') }}
    where selected_dag_run_id = '{{ var("weather_snapshot_dag_run_id") }}'
),
affected_product_keys as (
    select distinct
        bridge.admin_dong_code,
        snapshot.forecast_at,
        snapshot.category
    from snapshot_grid_keys as snapshot
    inner join active_bridge as bridge
        on snapshot.nx = bridge.nx
       and snapshot.ny = bridge.ny
)
```

routine `joined_candidates`와 `actual`은 `affected_product_keys`에 inner join하고, expected winner는 기존 shared winner macro로 계산한다. normal mode에서도 최신 manifest state가 publishable한 run만 후보로 사용한다.

- [ ] **Step 4: selector 구현**

`ask_seoul_weather_w2_canonical_contracts`는 fast 경로를 유지한다. `ask_seoul_weather_w2_canonical_full_contracts`는 동일한 나머지 9개 경로와 full 경로를 명시한다.

- [ ] **Step 5: 정적 테스트와 dbt parse 실행**

Run:

```powershell
python -m pytest domains/traffic_weather/tests/weather/test_weather_w2_canonical_selectors.py domains/traffic_weather/tests/weather/test_weather_w2_repair_contract.py -q
docker compose exec -T airflow-scheduler /home/airflow/dbt-venv/bin/dbt parse --project-dir /opt/airflow/dbt/domains/traffic_weather --profiles-dir /opt/airflow/dbt/domains/traffic_weather --target dev --no-partial-parse
```

Expected: pytest PASS, parse exit 0.

### Task 2: 09:15 Read-only Full Contract Audit DAG

**Files:**
- Create: `domains/weather/weather_ingest/w2_canonical_runtime.py`
- Modify: `domains/weather/weather_w2_canonical_transform.py`
- Create: `domains/weather/weather_w2_canonical_contract_audit.py`
- Create: `domains/weather/tests/test_weather_w2_canonical_contract_audit.py`
- Modify: `domains/weather/tests/test_weather_w2_canonical_transform_dag.py`

**Interfaces:**
- Consumes: selector `ask_seoul_weather_w2_canonical_full_contracts`, `weather_dbt_execution.execute_dbt_phase`, `validate_dev_runtime`, Trino common runtime.
- Produces: DAG `weather_w2_canonical_contract_audit`, shared `resolve_admin_dong_crosswalk_snapshot_id() -> int`.

- [ ] **Step 1: shared snapshot resolver와 audit DAG 실패 테스트 작성**

Audit DAG 테스트는 다음 계약을 고정한다.

```python
def test_full_contract_audit_is_daily_read_only_and_fail_closed():
    module = load_audit_module()
    assert module.DAG_ID == "weather_w2_canonical_contract_audit"
    assert module.dag.kwargs["schedule"] == "15 9 * * *"
    assert module.dag.kwargs["max_active_runs"] == 1
    assert module.dag.kwargs["is_paused_upon_creation"] is True
    assert "dbt_run_w2_canonical_models" not in module.dag.task_dict
    assert (
        module.dag.task_dict["dbt_test_w2_canonical_full_contracts"]
        .kwargs["pool"]
        == "trino_weather_heavy"
    )
```

Execution 테스트는 dbt vars가 canonical revision과 positive crosswalk snapshot ID만 포함하고, selector가 full selector인지 확인한다.

- [ ] **Step 2: 실패 확인**

Run:

```powershell
python -m pytest domains/weather/tests/test_weather_w2_canonical_contract_audit.py domains/weather/tests/test_weather_w2_canonical_transform_dag.py -q
```

Expected: audit 모듈 부재로 FAIL.

- [ ] **Step 3: crosswalk snapshot resolver 추출**

`w2_canonical_runtime.py`에 `AdminDongCrosswalkSnapshotUnavailableError`와 `resolve_admin_dong_crosswalk_snapshot_id()`를 이동한다. canonical transform은 이 심볼을 import하여 기존 동작과 monkeypatch seam을 유지한다.

- [ ] **Step 4: audit DAG 최소 구현**

DAG task chain:

```text
validate_dev_runtime
  -> resolve_admin_dong_crosswalk_snapshot
  -> dbt_deps
  -> dbt_test_w2_canonical_full_contracts
  -> publish_dbt_run_metrics
```

`dbt_test_w2_canonical_full_contracts`는 `threads=1`, `pool=trino_weather_heavy`로 실행하고 다음 vars를 전달한다.

```python
{
    "weather_w2_canonical_revision_date": "2025-04-01",
    "admin_dong_crosswalk_pin_snapshot_id": crosswalk_snapshot_id,
}
```

API 수집, dbt model run, D1 export task는 포함하지 않는다. dbt non-zero exit 또는 artifact 부재는 Airflow task 실패로 전달한다.

- [ ] **Step 5: DAG 테스트·compile 실행**

Run:

```powershell
python -m pytest domains/weather/tests/test_weather_w2_canonical_contract_audit.py domains/weather/tests/test_weather_w2_canonical_transform_dag.py domains/weather/tests/test_weather_w2_canonical_transform_execution.py -q
python -m compileall -q domains/weather/weather_ingest/w2_canonical_runtime.py domains/weather/weather_w2_canonical_contract_audit.py domains/weather/weather_w2_canonical_transform.py
```

Expected: PASS.

### Task 3: 7/9 용신동 Stale Winner 144건 정합화

**Files:**
- No code files.
- Runtime state: Airflow recovery checkpoint와 `iceberg_dev.weather.gold_weather_forecast_by_admin_dong`.

**Interfaces:**
- Consumes: `weather_w2_observation_recovery` staged mode, existing safe-trigger guard.
- Produces: 7/9 용신동 Gold winner가 최신 publishable Silver winner와 일치.

- [ ] **Step 1: 실행 전 family idle·pause 확인**

Run:

```powershell
bash scripts/safe-trigger-dag.sh weather_w2_observation_recovery --check-only
```

Expected: Weather family queued/running run 0. canonical과 audit는 idle/paused.

- [ ] **Step 2: 7/9 하루 checkpoint를 safe-trigger로 실행**

Run:

```powershell
docker compose exec -T airflow-scheduler airflow dags pause weather_w2_canonical_transform
bash scripts/safe-trigger-dag.sh weather_w2_observation_recovery --conf '{"recovery_mode":"staged_gold_only","repair_start_at":"2026-07-09 00:00:00.000000","repair_cutoff_at":"2026-07-09 23:59:59.999999","checkpoint_id":"yongsin-0709-light-v3-20260727"}'
```

Expected: direct `airflow dags trigger` 없이 recovery run 생성.

- [ ] **Step 3: checkpoint와 데이터 정합성 확인**

checkpoint state가 `verified`이고, targeted latest-record mismatch query가 `0`인지 확인한다. FULL bridge reconciliation도 `missing=0`, `extra=0`, `invalid_actual_bridge=0`이어야 한다.

### Task 4: Routine 및 Full Canonical GREEN 검증

**Files:**
- Runtime only.

**Interfaces:**
- Consumes: Task 1 selectors, Task 3 repaired Gold.
- Produces: routine/full selector `0 failures`, 실행 시간 증거.

- [ ] **Step 1: 영향 grain routine selector 실행**

현재 publishable Bronze run ID와 crosswalk snapshot ID를 명시해 routine selector를 실행한다. Expected: 10/10 PASS.

- [ ] **Step 2: Trino idle에서 full selector 한 번 실행**

Expected: 10/10 PASS. longest test duration과 query peak memory를 기록한다.

- [ ] **Step 3: 성능 기준 확인**

routine selector는 full latest-record test보다 짧아야 한다. full audit가 OOM 또는 timeout이면 성공으로 처리하지 않고 query plan을 다시 축소한다.

### Task 5: 도메인 검증·리뷰·커밋·PR·Merge

**Files:**
- DAG: `domains/weather/**`의 이번 작업 파일만.
- DBT: `domains/traffic_weather/**`의 이번 작업 파일만.

**Interfaces:**
- Produces: ASAC-DBT #349 및 ASAC-DAG #524의 dev 대상 PR과 merge commit.

- [ ] **Step 1: 최종 도메인 테스트**

Run focused pytest, Weather domain pytest, ruff, dbt parse와 selector tests. generated directories는 제외한다.

- [ ] **Step 2: diff와 secret·scope 검사**

`git diff --check`, `git status --short`, `.env`/secret 문자열, root `.airflowignore` 무변경을 확인한다.

- [ ] **Step 3: 코드 리뷰**

recovery staged write, serving export, routine/full contract, audit DAG를 대상으로 correctness·idempotency·manifest semantics·pool contention을 리뷰한다.

- [ ] **Step 4: 경로 지정 커밋**

개인 MD와 생성물을 제외하고 DAG/DBT repo에서 정확한 파일 경로만 커밋한다.

- [ ] **Step 5: PR 생성 및 merge**

공용 템플릿 body file을 사용해 dev 대상 PR을 만들고 인코딩·CI를 확인한다. 다른 도메인 영향이 없고 필수 check가 GREEN이면 DBT PR을 먼저 merge한 뒤 DAG PR을 merge한다.

### Task 6: 최신 dev 재배포와 DAG 운영 복구

**Files:**
- Runtime only. root submodule pointer와 `.airflowignore`는 변경하지 않는다.

**Interfaces:**
- Consumes: merged ASAC-DBT/ASAC-DAG `origin/dev`.
- Produces: local dev Airflow가 exact merged revision을 mount한 상태.

- [ ] **Step 1: clean deploy worktree에서 merged dev checkout**

두 submodule repo의 `origin/dev` exact commit을 clean worktree에 checkout한다. 기존 dirty root checkout은 보존한다.

- [ ] **Step 2: dev compose 재배포**

`scripts/deploy.sh`는 사용하지 않고 `docker compose up -d --build`로 재배포한다.

- [ ] **Step 3: import와 revision 확인**

컨테이너 health, DAG import error 0, DBT parse, mounted git revision을 확인한다.

- [ ] **Step 4: DAG pause 정책 적용**

정기 운영 Weather·Traffic DAG와 `weather_w2_canonical_contract_audit`만 unpause한다. recovery, recollect/backfill, `weather_serving_export` 같은 manual-only DAG는 paused 상태로 둔다.

### Task 7: 24시간 운영 감시

**Files:**
- Runtime monitor output only. 개인 운영 기록은 커밋하지 않는다.

**Interfaces:**
- Produces: 활성 도메인 DAG의 24시간 정상 재가동 증거.

- [ ] **Step 1: monitor 재가동**

기존 `watch_all.sh`와 progress/findings 파일을 재사용해 Weather·Traffic 활성 DAG의 queued/running/failed/success 상태를 추적한다.

- [ ] **Step 2: 첫 scheduled canonical·audit 확인**

다음 Bronze asset-trigger canonical과 다음 09:15 full audit의 run ID, 성공 task, duration을 기록한다.

- [ ] **Step 3: 24시간 종료 판정**

예정된 run 누락, 반복 실패, Trino 잔존 query, pool starvation이 없으면 운영 복구 완료로 보고한다. incident가 발생하면 해당 run/task/log와 사용자 조치 필요 여부를 분리해 남긴다.

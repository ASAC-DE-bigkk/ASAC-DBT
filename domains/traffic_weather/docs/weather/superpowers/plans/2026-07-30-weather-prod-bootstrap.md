# Weather/Traffic prod bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** publishable Weather Bronze snapshot으로 prod W1/W2를 최초 생성하고 Weather/Traffic의 prod cross-domain source를 현재 물리 계약과 정렬한다.

**Architecture:** 기존 snapshot pin과 fail-closed 계약은 유지하면서 canonical prod 조합만 W1 최초 생성을 허용한다. source 이름은 유지하고 target별 Citydata 물리 스키마만 선택하며, 임시 Commerce 제외 selector를 정규 Gold selector로 복구한다.

**Tech Stack:** dbt/Jinja, YAML selectors/sources, pytest, Airflow DAG Python

## Global Constraints

- Weather/Traffic 소유 파일만 수정한다.
- `--full-refresh`, snapshot pin, merge grain, repair evidence 보호를 유지한다.
- 다른 도메인 DAG·코드·테이블은 변경하거나 실행하지 않는다.
- 코드 변경 전 실패 테스트를 실행해 RED를 확인한다.
- commit·push·PR은 별도 사용자 승인 전 수행하지 않는다.

---

### Task 1: W1 canonical prod snapshot bootstrap

**Files:**
- Modify: `tests/weather/test_weather_v2_contract.py`
- Modify: `macros/weather/weather_v2_contract.sql`

**Interfaces:**
- Consumes: `target.name`, `target.database`, `ASK_SEOUL_SCHEMA`, `weather_schema_name()`, `weather_snapshot_dag_run_id`
- Produces: canonical prod 최초 W1 observation/grid와 static seed/bridge 생성 허용 여부

- [ ] **Step 1: prod canonical 조합과 snapshot pin을 요구하는 실패 테스트를 추가한다.**
- [ ] **Step 2: 해당 pytest만 실행해 기존 macro가 prod 경로를 표현하지 않아 실패하는지 확인한다.**
- [ ] **Step 3: 기존 isolated smoke/repair 분기 옆에 공통 `prod_snapshot_bootstrap` 조건을 추가하고 initial/candidate guard에서 함께 사용한다.**
- [ ] **Step 4: 동일 pytest를 다시 실행해 통과를 확인한다.**

### Task 2: target별 Citydata source

**Files:**
- Modify: `tests/weather/test_weather_cross_domain_source_contract.py`
- Modify: `tests/traffic/test_cross_domain_gold_contract.py`
- Modify: `models/weather/sources.yml`
- Modify: `models/traffic/sources.yml`

**Interfaces:**
- Consumes: `target.name`, optional `SEOUL_CITYDATA_SCHEMA`
- Produces: dev=`seoul_citydata`, prod=`citydata` source relation

- [ ] **Step 1: Weather와 Traffic source의 target별 기본값을 요구하는 실패 테스트를 추가한다.**
- [ ] **Step 2: 두 테스트를 실행해 고정 `seoul_citydata` 기본값 때문에 실패하는지 확인한다.**
- [ ] **Step 3: 두 source YAML을 동일한 target-aware Jinja 표현식으로 변경한다.**
- [ ] **Step 4: 두 테스트를 다시 실행해 통과를 확인한다.**

### Task 3: Commerce cross-domain leaf 복구

**Files:**
- Modify: `tests/weather/test_weather_gold_selector.py`
- Modify: `selectors.yml`
- Modify: `ASAC-DAG domains/weather/tests/weather_transform_test_support.py`
- Modify: `ASAC-DAG domains/weather/tests/test_weather_transform_dag.py`
- Modify: `ASAC-DAG domains/weather/weather_vilage_fcst_transform.py`

**Interfaces:**
- Consumes: `ask_seoul_weather_transform_gold`
- Produces: 전체 Weather Gold run/test phase

- [ ] **Step 1: DAG가 정규 Gold selector를 사용하고 임시 Commerce 제외 selector가 없음을 요구하는 테스트를 작성한다.**
- [ ] **Step 2: DBT와 DAG 테스트를 실행해 기존 `without_commerce` 선택 때문에 실패하는지 확인한다.**
- [ ] **Step 3: DAG phase selector를 정규 Gold로 교체하고 미사용 임시 selector를 제거한다.**
- [ ] **Step 4: DBT와 DAG 테스트를 다시 실행해 통과를 확인한다.**

### Task 4: 회귀 검증

**Files:**
- Verify only

**Interfaces:**
- Consumes: Tasks 1–3 결과
- Produces: feature revision 배포 전 검증 증거

- [ ] **Step 1: 관련 Weather/Traffic DBT pytest와 Weather DAG pytest를 실행한다.**
- [ ] **Step 2: prod target으로 `dbt parse`와 관련 selector `dbt ls`를 실행한다.**
- [ ] **Step 3: pinned snapshot으로 W1 seed/bridge/observation compile 성공과 snapshot 미제공 실패를 확인한다.**
- [ ] **Step 4: 변경 Python compile과 `git diff --check`를 실행한다.**
- [ ] **Step 5: 다른 도메인 파일 변경이 없고 prod canary 전 runtime이 pause 상태인지 확인한다.**

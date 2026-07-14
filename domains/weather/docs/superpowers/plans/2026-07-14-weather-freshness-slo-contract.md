# Weather freshness SLO 환경 계약 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Weather source freshness의 4시간·6시간 SLO를 DAG와 같은 minute 기반 환경 계약으로 해석하고 resolved dbt manifest에서 검증한다.

**Architecture:** `sources.yml`의 source-level freshness count를 Jinja `env_var(... ) | int`로 바꾸고 period는 minute로 고정한다. Weather 소유 Python 테스트는 먼저 YAML 계약을 확인하고, dbt가 있으면 임시 복사본에서 기본값과 override manifest를 parse해 resolved count를 검증한다.

**Tech Stack:** dbt-core, dbt-trino, PyYAML, pytest

## Global Constraints

- 변경·생성 파일은 `domains/weather/**`만 허용한다.
- 기본값은 warn 240분, error 360분이며 환경변수 이름은 `ASK_SEOUL_REPORT_WEATHER_FRESHNESS_WARN_MINUTES`, `ASK_SEOUL_REPORT_WEATHER_FRESHNESS_ERROR_MINUTES`다.
- source freshness만 바꾸며 Weather SQL, incremental lookback, repair, table schema·row는 변경하지 않는다.
- resolved-manifest 검증은 `dbt deps`와 `dbt parse --target dev --no-partial-parse`만 사용하고 DML을 실행하지 않는다.
- API key·token·password·`.env`는 읽거나 기록하지 않는다.

---

### Task 1: Weather source freshness 환경 계약

**Files:**
- Modify: `domains/weather/models/sources.yml:9-11`
- Modify: `domains/weather/tests/test_source_freshness_slo.py:1-27`
- Modify: `domains/weather/docs/dbt_contracts.md`의 `Coverage and freshness` 절

**Interfaces:**
- Consumes: DAG 환경변수 `ASK_SEOUL_REPORT_WEATHER_FRESHNESS_WARN_MINUTES`, `ASK_SEOUL_REPORT_WEATHER_FRESHNESS_ERROR_MINUTES`.
- Produces: dbt manifest source `source.weather.weather_bronze.kma_vilage_fcst`의 `freshness.warn_after/error_after` minute count.

- [ ] **Step 1: Write the failing tests**

`test_source_freshness_slo.py`에 다음 계약을 추가한다.

```python
WARN_ENV = "ASK_SEOUL_REPORT_WEATHER_FRESHNESS_WARN_MINUTES"
ERROR_ENV = "ASK_SEOUL_REPORT_WEATHER_FRESHNESS_ERROR_MINUTES"

def test_weather_freshness_declares_airflow_watchdog_environment_contract():
    source_text = SOURCES_PATH.read_text(encoding="utf-8")
    assert f"env_var('{WARN_ENV}', '240') | int" in source_text
    assert f"env_var('{ERROR_ENV}', '360') | int" in source_text
```

같은 파일에서 isolated dbt project를 복사해 기본 `(240, 360)`과 override `(241, 361)`의 `source.weather.weather_bronze.kma_vilage_fcst` resolved manifest freshness를 검증한다.

- [ ] **Step 2: Run tests to verify RED**

Run: `python -m pytest -q domains/weather/tests/test_source_freshness_slo.py`

Expected: YAML 계약 test가 기존 literal `count: 4/6, period: hour` 때문에 FAIL.

- [ ] **Step 3: Implement the minimal source configuration**

`domains/weather/models/sources.yml`의 freshness를 다음으로 교체한다.

```yaml
freshness:
  warn_after:
    count: "{{ env_var('ASK_SEOUL_REPORT_WEATHER_FRESHNESS_WARN_MINUTES', '240') | int }}"
    period: minute
  error_after:
    count: "{{ env_var('ASK_SEOUL_REPORT_WEATHER_FRESHNESS_ERROR_MINUTES', '360') | int }}"
    period: minute
```

`dbt_contracts.md`에는 warn 240분(4시간), error 360분(6시간), 두 환경변수, `warn < error` 조건만 기록한다.

- [ ] **Step 4: Run GREEN verification**

Run: `python -m pytest -q domains/weather/tests/test_source_freshness_slo.py`

Expected: YAML 계약 PASS; dbt가 설치돼 있으면 기본·override manifest 2개도 PASS, 없으면 그 테스트만 명시적으로 SKIP.

- [ ] **Step 5: Run parse validation and commit**

Run: `git diff --check` then dev Airflow/dbt runtime에서 `dbt deps --project-dir /opt/airflow/dbt/domains/weather --profiles-dir /opt/airflow/dbt/domains/weather` 및 `dbt parse --target dev --no-partial-parse`.

Expected: parse PASS; `dbt run`과 prod write는 실행하지 않는다.

Commit:

```bash
git add domains/weather/models/sources.yml domains/weather/tests/test_source_freshness_slo.py domains/weather/docs
git commit -m "fix(weather): freshness SLO 환경 계약을 정렬한다 (#171)"
```

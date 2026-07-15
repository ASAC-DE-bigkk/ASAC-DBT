# Traffic freshness SLO 환경 계약 구현 계획

> 경로 주의(2026-07-15): 이 문서는 구현 당시 경로를 보존한 이력이다. 현재 dbt project root는 `domains/traffic_weather`이며 실행 가능한 최신 경로는 이 project의 `README.md`와 `docs/{traffic,weather}/dbt_contracts.md`를 따른다.

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Traffic Bronze freshness를 `collection_run_manifest`에만 적용하면서 기본 `15분/30분`과 Airflow watchdog이 사용하는 환경 변수 override를 dbt가 실제로 해석하도록 만들고, 이 계약의 테스트 소유권을 Traffic 도메인으로 옮긴다.

**Architecture:** `sources.yml`은 두 환경 변수의 문자열 입력을 dbt Jinja `int` 필터로 정수화한다. 도메인 테스트는 임시 target에 `dbt parse --no-partial-parse`를 실행해 생성된 `manifest.json`의 resolved source freshness를 검증하고, incident/audit source에 freshness가 생기지 않았는지도 함께 확인한다. dbt 실행 파일이 없는 가벼운 Python 환경에서는 정적 경계 테스트를 계속 실행하고 resolved 테스트만 명시적으로 skip하며, 최종 검증은 프로젝트의 Airflow dbt 1.10.22 런타임에서 반드시 수행한다.

**Tech Stack:** dbt-core 1.10.22, dbt-trino 1.10.2, YAML/Jinja `env_var`, Python 3.11, pytest, Docker.

---

## 보호할 기존 의도

- `b26cc63d`는 정상 zero-row 응답을 stale incident로 오판하지 않도록 source freshness를 incident/audit에서 제거하고 publish manifest로 옮겼다.
- `2d725901`, `53b57f32`는 pinned snapshot correctness와 freshness를 분리했다. 이번 변경은 threshold의 주입 방식만 바꾸며 이 선택·zero-row 계약에는 손대지 않는다.
- `60e50581`가 정한 Traffic 기본값 `warn=15분`, `error=30분`은 그대로 유지한다.

### Task 1: Traffic 소유의 실패 계약을 먼저 만든다

**Files:**
- Create: `domains/traffic/tests/test_source_freshness_slo.py`

**Step 1: RED 테스트 작성**

- source 파일이 `ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_WARN_MINUTES`와 `ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_ERROR_MINUTES`를 사용하도록 요구한다.
- dbt parse 결과에서 기본값이 각각 `15 minute`, `30 minute`로 resolve되는지 요구한다.
- override `21/42`가 같은 단위의 정수로 resolve되는지 요구한다.
- `collection_run_manifest`만 freshness를 가지며 incident와 request audit는 계속 `null`인지 요구한다.
- `warn < error`를 기본값과 override 모두에서 요구한다.

**Step 2: RED 실행**

Run: `python -m pytest domains/traffic/tests/test_source_freshness_slo.py -q`

Expected: 환경 변수 계약이 아직 없어 env-key 또는 resolved override assertion이 실패한다.

### Task 2: manifest-only 환경 계약을 최소 구현한다

**Files:**
- Modify: `domains/traffic/models/sources.yml:108-140`

**Step 1: 최소 구현**

- `collection_run_manifest.freshness.warn_after.count`를 `ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_WARN_MINUTES`의 정수화된 값으로 바꾸고 default를 `15`로 둔다.
- `error_after.count`를 대응하는 `ERROR_MINUTES`의 정수화된 값으로 바꾸고 default를 `30`으로 둔다.
- period는 둘 다 `minute`으로 유지한다.
- incident/audit의 `freshness: null`은 변경하지 않는다.

**Step 2: GREEN 실행**

Run: `python -m pytest domains/traffic/tests/test_source_freshness_slo.py domains/traffic/tests/test_current_state_contract.py -q`

Expected: host 정적 계약과 zero-row/pinned 보호 테스트 통과. dbt가 없으면 resolved 사례는 skip 사유가 표시된다.

Run in dbt runtime: `/home/airflow/dbt-venv/bin/dbt parse --project-dir /workspace/domains/traffic --profiles-dir /workspace/domains/traffic --target dev --no-partial-parse --target-path <temporary-target>`

Expected: 기본 및 override 각각 parse 성공, manifest 검증 테스트 통과.

### Task 3: SLO 근거와 운영 계약을 기록한다

**Files:**
- Create: `domains/traffic/docs/freshness_slo.md`

**Step 1: 문서 작성**

- 기본값, env key, 단위, 대상 source, Airflow watchdog과의 정렬 관계를 표로 기록한다.
- 저장소의 추적된 dev 자료에서 threshold false-positive 이력을 찾지 못한 경우 이를 “측정 자료 없음”으로 명시하고 임의 재조정을 금지한다.
- incident/audit zero-row 및 pinned correctness 보호 경계를 기록한다.

### Task 4: 전체 회귀·경계 검증과 커밋

**Files:**
- Verify only: `domains/traffic/**`

**Step 1: 관련 회귀 테스트**

Run: `python -m pytest domains/traffic/tests/test_source_freshness_slo.py domains/traffic/tests/test_current_state_contract.py -q`

Run: `python -m compileall -q domains/traffic/tests`

**Step 2: dbt resolved 검증**

- dbt 1.10.22 런타임에서 기본 env와 `21/42` override로 각각 fresh target에 parse한다.
- 두 manifest의 source node를 읽어 `15/30`, `21/42`, `minute`, manifest-only를 확인한다.

**Step 3: 저장소 경계 검사**

Run: `git diff --check`

Run: `git status --short`

Expected: 변경 경로가 `domains/traffic/**`뿐이다.

**Step 4: 커밋**

Run: `git add domains/traffic && git commit -m "fix(traffic): manifest freshness 환경 계약을 분리한다 (#172)"`

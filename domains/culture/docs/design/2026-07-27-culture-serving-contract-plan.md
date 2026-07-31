# culture meta.serving 계약 선언 (#346) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** culture 외부 gold 7종에 Serving Contract v1.1 `meta.serving` 블록을 선언하고 validator·dbt 게이트를 통과시킨다 (v1 계약 첫 도메인 채택).

**Architecture:** 편집 대상은 사실상 yml 2파일 — `_culture_gold__models.yml`(계약 선언 + PK 근거 테스트)과 `packages.yml`(dbt_utils). 검증은 3중: ① `serving_contract/` validator(구조·의미) ② `dbt parse`(문법) ③ 컨테이너 `dbt test`(PK 고유성 실데이터). 모델 SQL 은 건드리지 않는다.

**Tech Stack:** dbt-core 1.10.22(trino) · dbt_utils 1.3.1 · serving_contract validator(레포 루트) · 컨테이너 dbt = `/home/airflow/dbt-venv/bin/dbt`, 프로젝트 `/opt/airflow/dbt/domains/culture`

## Global Constraints

- 계약 정본: ASAC-DAG `docs/contracts/serving-contract-v1.md` (v1.1). 필수 9필드 전부, §3.3 금지 필드(`estimated_*`·`api_path`류) 선언 금지.
- 공통값(7종 동일): `enabled: true` · `external: true` · `contract_version: v1` · `publication_mode: snapshot` · `zero_policy: retain_last_good` · `publication_trigger: {schedule_cron: "30 4 * * *"}`
- `event_time` 선언 모델은 `freshness_slo_minutes: 1800` 동반(v1.1 §3.1 조건부 필수).
- 기존 `meta.external`·`display`·`refresh` **삭제 금지**(계약 §9 — 대시보드 소비자 정본).
- `domains/culture/` 밖 수정 금지. 이 레포는 컨테이너에 마운트됨(`sample/dbt`) — 검증 후 양쪽 체크아웃 `dev` 복귀.
- 커밋 마지막 줄: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

### 계약 값 결정표 (설계 문서 실측 기반)

| 모델 | product_id | primary_key | event_time / slo | 근거 테스트 현황 |
|---|---|---|---|---|
| gold_culture_event_schedule | culture_event_schedule | [event_ref] | event_start_date / 1800 | 완비(not_null+unique) |
| gold_culture_activity_by_dong | culture_activity_by_dong | [admin_dong_code, event_date] | event_date / 1800 | not_null ✓ · **unique_combination 추가** |
| gold_culture_calendar_density | culture_calendar_density | [gu_code, event_date] | event_date / 1800 | not_null ✓ · **unique_combination 추가** |
| gold_culture_event_crowd | culture_event_crowd | [gu_code, day_of_week, hour_of_day] | 없음(명부성) | not_null ✓ · **unique_combination 추가** |
| gold_culture_boxoffice_daily | culture_boxoffice_daily | [performance_id, snapshot_date] | snapshot_date / 1800 | **not_null 2개 + unique_combination 추가** |
| gold_culture_dine_around | culture_dine_around | [admin_dong_code] | 없음(명부성) | 완비 |
| gold_culture_booking_curve | culture_booking_curve | [performance_id] | 없음(스냅샷 요약) | 완비 |

`snapshot_date`는 varchar(ISO `YYYY-MM-DD`) 유지 결정 — 계약은 "모델의 실제 컬럼"만 요구하고, snapshot 모드에서 event_time 은 freshness 측정용이며 ISO 문자열은 사전순=시간순. 모델 SQL 캐스팅 변경은 YAGNI.

## 실행 중 확정된 이탈 2건 (7/27)

1. **boxoffice PK = (snapshot_date, rank_no)** — 계획의 (performance_id, snapshot_date)를
   버림. 모델 description·rank_no 주석이 그레인을 snapshot_date×rank_no 로 선언하고
   있고(둘 다 실측 유일·null 0), 계약 PK 는 그레인의 표현이어야 한다.
2. **legacy `external`·`refresh` 는 유지가 아니라 제거** — 계획은 §9 표의 "소비자" 열을
   근거로 유지로 읽었으나, validator 가 `legacy_double_declaration` 을 **FAIL**(exit 1)로
   강제한다(§9 규칙 2 즉시 적용). §9 규칙 1대로 소비자(대시보드 extract)를 같은 사이클에
   변경: ASK-Seoul-Dashboard `feat/serving-meta-fallback` — `resolved_external`(serving 우선
   → legacy 폴백)·`resolved_refresh`(legacy → cron 유도 '1일'). **머지 순서 = 대시보드 먼저**
   (폴백은 양방향 호환이라 먼저 나가도 무해, DBT 가 먼저 나가면 로컬 대시보드의 culture
   external 판정이 INTERNAL_GOLD 폴백으로 떨어져 7종이 외부 pill 을 잃는다). `display` 는
   계약 §9 명시 유지(삭제 줄 diff 실측: refresh 7 + external 7, display 0).

---

### Task 1: 브랜치 + dbt_utils 의존성

**Files:**
- Modify: `domains/culture/packages.yml`
- Modify: `domains/culture/package-lock.yml` (dbt deps 산출물)

**Interfaces:**
- Produces: `dbt_utils.unique_combination_of_columns` generic test — Task 2 yml 에서 사용. validator 는 테스트 이름의 `unique_combination` 부분문자열로 복합 PK 근거를 인정(`serving_contract/validator.py:206`), fixture(`serving_contract/tests/fixtures/valid_contracts.yml:33`)도 이 이름을 정본으로 사용.

- [ ] **Step 1: 브랜치 생성**

```bash
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && git fetch origin dev --quiet && git checkout -b feat/346-culture-serving-contract origin/dev
```

- [ ] **Step 2: packages.yml에 dbt_utils 추가**

`domains/culture/packages.yml` 전체를 다음으로 교체:

```yaml
packages:
  - local: ../../packages/asac_axes
  - package: dbt-labs/dbt_utils
    version: 1.3.1
```

- [ ] **Step 3: 컨테이너에서 dbt deps (lock 갱신)**

sample/dbt(컨테이너 마운트 클론)를 이 브랜치로 전환 후 deps:

```bash
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && git push -u origin feat/346-culture-serving-contract
cd /c/Users/Dell3571/ask-seoul/sample/dbt && git fetch origin --quiet && git checkout feat/346-culture-serving-contract
MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt deps --profiles-dir ."
```

Expected: `Installed from hub ... dbt_utils 1.3.1` + `package-lock.yml` 갱신. 갱신된 lock 을 ASAC-DBT 쪽으로 복사(마운트 동일 파일이므로 sample/dbt 워킹트리에 생김 → `git -C /c/Users/Dell3571/ask-seoul/sample/dbt diff --name-only` 로 확인 후, ASAC-DBT 체크아웃에서 같은 편집 재현이 아니라 **sample/dbt 쪽 파일을 ASAC-DBT 워킹트리로 복사**):

```bash
cp /c/Users/Dell3571/ask-seoul/sample/dbt/domains/culture/package-lock.yml /c/Users/Dell3571/ask-seoul/ASAC-DBT/domains/culture/package-lock.yml
```

- [ ] **Step 4: parse 로 의존성 확인**

```bash
MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt parse --profiles-dir . --target dev"
```

Expected: `Performance info` 로 끝나는 정상 종료(exit 0).

- [ ] **Step 5: 커밋**

```bash
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && git add domains/culture/packages.yml domains/culture/package-lock.yml && git commit -m "build(culture): dbt_utils 1.3.1 — 복합 PK unique_combination 근거용 (#346)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: PK 근거 테스트 보강 (4모델)

**Files:**
- Modify: `domains/culture/models/gold/_culture_gold__models.yml`

**Interfaces:**
- Consumes: Task 1 의 `dbt_utils.unique_combination_of_columns`
- Produces: validator `_check_primary_key` 통과 조건 — 복합 PK 4종의 `unique_combination` 근거 + boxoffice PK 컬럼 not_null

- [ ] **Step 1: 모델-레벨 unique_combination 테스트 4건 추가**

`_culture_gold__models.yml`에서 아래 4개 모델 각각에 **모델 레벨** `tests:` 를 추가(이미 모델 레벨 tests 가 있으면 항목 추가, 없으면 `columns:` 위에 키 신설). 레포는 `tests:` 키 사용(`data_tests:` 아님, 실측 43:0):

```yaml
# gold_culture_activity_by_dong 에
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [admin_dong_code, event_date]

# gold_culture_calendar_density 에
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [gu_code, event_date]

# gold_culture_event_crowd 에
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [gu_code, day_of_week, hour_of_day]

# gold_culture_boxoffice_daily 에
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [performance_id, snapshot_date]
```

기존 싱귤러 테스트(assert_calendar_density_grain_and_range 등)와 중복 단언이지만 validator 가 yml 선언만 읽으므로 필요 — 싱귤러 쪽은 범위·불변식 검증을 겸하므로 제거하지 않는다.

- [ ] **Step 2: boxoffice_daily PK 컬럼 not_null 추가**

`gold_culture_boxoffice_daily` 의 `columns:` 에서 `performance_id`·`snapshot_date` 항목에 (테스트가 하나도 없는 상태 실측) 추가:

```yaml
      - name: performance_id
        tests: [not_null]
      - name: snapshot_date
        tests: [not_null]
```

(해당 컬럼 항목이 이미 있으면 `tests: [not_null]` 만 붙인다 — description 등 기존 속성 보존.)

- [ ] **Step 3: 컨테이너에서 신규 테스트만 실행 → 전부 PASS 확인**

```bash
MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt test --profiles-dir . --target dev --select gold_culture_activity_by_dong gold_culture_calendar_density gold_culture_event_crowd gold_culture_boxoffice_daily"
```

Expected: PASS (그레인 유일성은 싱귤러 테스트·7/27 실측으로 이미 참). FAIL 시 중복 행 원인 조사 후 진행 중단 — 계약 선언보다 데이터 결함 수정이 먼저.

- [ ] **Step 4: 커밋**

```bash
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && git add domains/culture/models/gold/_culture_gold__models.yml && git commit -m "test(culture): 서빙 PK 고유성 근거 — unique_combination 4종 + boxoffice not_null (#346)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: meta.serving 계약 선언 (7모델)

**Files:**
- Modify: `domains/culture/models/gold/_culture_gold__models.yml`

**Interfaces:**
- Consumes: Task 2 의 PK 근거 테스트 (validator 가 대조)
- Produces: manifest `config.meta.serving` 7건 — ASAC-DAG#520 공통 Publisher `contract.py` 의 입력

- [ ] **Step 1: 7모델 config.meta 에 serving 블록 추가**

각 모델의 `config: → meta:` 아래(기존 `refresh`·`external`·`display` 형제로) 삽입. **7종 개별 값**:

```yaml
# gold_culture_event_schedule
        serving:
          enabled: true
          external: true
          contract_version: v1
          product_id: culture_event_schedule
          product_question: "이번 주말·특정 기간 서울에서 무슨 문화행사가 열리나?"
          grain: "행사(event_ref)마다 한 행"
          primary_key: [event_ref]
          event_time: event_start_date
          freshness_slo_minutes: 1800
          publication_mode: snapshot
          zero_policy: retain_last_good
          publication_trigger:
            schedule_cron: "30 4 * * *"

# gold_culture_activity_by_dong
        serving:
          enabled: true
          external: true
          contract_version: v1
          product_id: culture_activity_by_dong
          product_question: "어느 행정동에서 언제 문화 활동이 얼마나 열리나?"
          grain: "행정동×날짜마다 한 행"
          primary_key: [admin_dong_code, event_date]
          event_time: event_date
          freshness_slo_minutes: 1800
          publication_mode: snapshot
          zero_policy: retain_last_good
          publication_trigger:
            schedule_cron: "30 4 * * *"

# gold_culture_calendar_density
        serving:
          enabled: true
          external: true
          contract_version: v1
          product_id: culture_calendar_density
          product_question: "구별로 어느 날짜에 행사가 몰리나(밀집도)?"
          grain: "구×날짜마다 한 행"
          primary_key: [gu_code, event_date]
          event_time: event_date
          freshness_slo_minutes: 1800
          publication_mode: snapshot
          zero_policy: retain_last_good
          publication_trigger:
            schedule_cron: "30 4 * * *"

# gold_culture_event_crowd  (명부성 — event_time 미선언)
        serving:
          enabled: true
          external: true
          contract_version: v1
          product_id: culture_event_crowd
          product_question: "무슨 요일 몇 시에 행사 주변이 붐비나?"
          grain: "구×요일×시간대마다 한 행"
          primary_key: [gu_code, day_of_week, hour_of_day]
          publication_mode: snapshot
          zero_policy: retain_last_good
          publication_trigger:
            schedule_cron: "30 4 * * *"

# gold_culture_boxoffice_daily
        serving:
          enabled: true
          external: true
          contract_version: v1
          product_id: culture_boxoffice_daily
          product_question: "지금 서울에서 예매 상위 공연은 무엇인가?"
          grain: "공연×스냅샷일마다 한 행"
          primary_key: [performance_id, snapshot_date]
          event_time: snapshot_date
          freshness_slo_minutes: 1800
          publication_mode: snapshot
          zero_policy: retain_last_good
          publication_trigger:
            schedule_cron: "30 4 * * *"

# gold_culture_dine_around  (명부성 — event_time 미선언)
        serving:
          enabled: true
          external: true
          contract_version: v1
          product_id: culture_dine_around
          product_question: "행사 많은 동네 주변 외식 상권은 어디인가?"
          grain: "행정동마다 한 행"
          primary_key: [admin_dong_code]
          publication_mode: snapshot
          zero_policy: retain_last_good
          publication_trigger:
            schedule_cron: "30 4 * * *"

# gold_culture_booking_curve  (스냅샷 요약 — event_time 미선언)
        serving:
          enabled: true
          external: true
          contract_version: v1
          product_id: culture_booking_curve
          product_question: "공연 예매가 개막까지 어떻게 차오르나?"
          grain: "공연마다 한 행"
          primary_key: [performance_id]
          publication_mode: snapshot
          zero_policy: retain_last_good
          publication_trigger:
            schedule_cron: "30 4 * * *"
```

들여쓰기 주의: 이 파일은 `config:` 가 모델 바로 아래 2칸, `meta:` 4칸(실제 파일의 기존 `external:` 들여쓰기에 맞춘다 — 위 스니펫의 8칸은 예시).

- [ ] **Step 2: validator 실행 (manifest 없이 — 구조 규칙)**

```bash
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && PYTHONIOENCODING=utf-8 python serving_contract/validate_serving_contract.py --source "domains/culture/models/gold/*.yml" --format text
```

Expected: `PASS`, 7 models, exit 0. FAIL 항목이 나오면 메시지의 필드명을 계약 문서 §3과 대조해 수정.

- [ ] **Step 3: dbt parse**

```bash
MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt parse --profiles-dir . --target dev"
```

Expected: exit 0.

- [ ] **Step 4: 커밋**

```bash
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && git add domains/culture/models/gold/_culture_gold__models.yml && git commit -m "feat(culture): 외부 gold 7종 meta.serving 계약 선언 — v1.1 첫 도메인 채택 (#346)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: manifest 검증 + 회귀 + PR

**Files:**
- Create: `domains/culture/docs/design/2026-07-27-culture-serving-contract-plan.md` (이 계획서 — PR 동승)

**Interfaces:**
- Consumes: Task 3 의 계약 선언
- Produces: ASAC-DAG#520 이 소비할 manifest (`meta.serving` 7건) + PR

- [ ] **Step 1: manifest 재생성 + validator --manifest (컬럼 실존 검증 강화)**

```bash
MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt parse --profiles-dir . --target dev"
docker cp elt-infra-airflow-scheduler-1:/opt/airflow/dbt/domains/culture/target/manifest.json "$TEMP/culture-manifest.json"
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && PYTHONIOENCODING=utf-8 python serving_contract/validate_serving_contract.py --source "domains/culture/models/gold/*.yml" --manifest "$TEMP/culture-manifest.json" --format text
```

Expected: PASS, exit 0 — `primary_key_not_a_column`·`event_time` 컬럼 실존 검증까지 통과.

- [ ] **Step 2: culture 전체 dbt test 회귀**

```bash
MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt test --profiles-dir . --target dev"
```

Expected: 기존 + 신규 전부 PASS (warn 은 기존 수준 유지).

- [ ] **Step 3: 대시보드 extract 회귀 확인**

extract 는 `meta.external`·`display` 를 소비 — 두 키를 삭제하지 않았음을 diff 로 확인:

```bash
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && git diff origin/dev -- domains/culture/models/gold/_culture_gold__models.yml | grep -E "^-" | grep -v "^---" | grep -E "external|display|refresh" ; echo "exit=$? (1=삭제줄 없음, 정상)"
```

Expected: `exit=1` (기존 키 삭제된 줄 0).

- [ ] **Step 4: 계획서 커밋 + push + PR**

```bash
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && git add domains/culture/docs/design/2026-07-27-culture-serving-contract-plan.md && git commit -m "docs(culture): #346 serving 계약 구현 계획서

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push -u origin feat/346-culture-serving-contract
```

PR: base `dev`, title `[Feat] culture 외부 gold 7종 meta.serving 계약 선언 (#346)`. body 에 Closes #346 · validator/parse/test 실행 결과 · 결정표 · "짝 이슈 ASAC-DAG#520 은 이 PR 머지 후" · 마지막 줄 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 5: 양쪽 체크아웃 dev 복귀**

```bash
cd /c/Users/Dell3571/ask-seoul/sample/dbt && git checkout dev
cd /c/Users/Dell3571/ask-seoul/ASAC-DBT && git checkout dev
```

(컨테이너가 sample/dbt 를 마운트 중 — 브랜치 방치 금지. 머지는 셀프 금지, 리뷰 대기.)

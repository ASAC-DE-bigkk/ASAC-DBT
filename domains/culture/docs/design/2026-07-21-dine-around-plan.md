# gold_culture_dine_around Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 동별 문화 밀도 × 요식업 스톡 마트 `gold_culture_dine_around` 구축 — "공연 보고 밥 먹기 좋은 동네" 질의 직답 (#308, 티어링 v2 외부 공개 7번째).

**Architecture:** culture 첫 commerce 크로스도메인 read. `gold_culture_activity_by_dong`(426동 스카폴드)을 기준으로 commerce `gold_license_dong_category_matrix`(식품 인허가 스톡)를 left join. 문화 축은 다가오는 90일 행사량, 요식업 축은 active 스톡, 결합 점수는 두 축 percent_rank의 기하평균(둘 다 높아야 높음).

**Tech Stack:** dbt 1.10 (trino adapter) · Trino/Iceberg (`iceberg_dev.culture`) · 검증은 컨테이너(`elt-infra-airflow-scheduler-1`)의 `/opt/airflow/dbt`(= `sample/dbt` 마운트, dev)에서 브랜치 detach checkout.

## Global Constraints

- 자기 도메인(culture) 스키마 밖에 쓰지 않음 — commerce는 **source 경유 read-only** (`{{ source('commerce_gold', ...) }}`, ref 금지)
- contract enforced (`+contract: {enforced: true}`) + **`meta: {external: true}`** 명시 (#308 AC)
- 식품 필터는 raw 값 **`category = 'food'`** (7/21 실측: major='health'/category='food'/category_ko='식품')
- commerce 매핑 커버리지 **219/426동(51.4%)** — 미커버 동은 `has_dining_data=false`, `dining_*`·`dining_stock_pctl`·`dine_around_score` 모두 NULL (스카폴드 426행은 유지)
- 커밋 마지막 줄: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` / PR body 마지막: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
- 셀프 머지 금지. 검증 후 `sample/dbt`는 반드시 `git checkout dev` 복귀
- 컨테이너 dbt 경로: `/home/airflow/dbt-venv/bin/dbt`, Git Bash에서 docker 호출 시 `MSYS_NO_PATHCONV=1` 필수

## 파일 구조

| 파일 | 책임 |
|---|---|
| `models/sources.yml` (Modify) | `commerce_gold` 크로스도메인 source 신규 등록 (citydata_gold 선례 미러) |
| `models/gold/gold_culture_dine_around.sql` (Create) | 마트 본체 — 426동 그레인, 좌: culture 90d 집계, 우: 식품 스톡 left join, percent_rank 점수 |
| `models/gold/_culture_gold__models.yml` (Modify) | contract enforced + meta.external=true + 컬럼 계약·테스트 |
| `tests/assert_dine_around_consistency.sql` (Create) | 싱귤러 테스트 — pctl/score 범위 + has_dining_data ↔ NULL 동조 |
| `docs/design/2026-07-21-gold-tiering-v2.md` (기작성) | 설계 문서 — 본 브랜치에 커밋 동승 |

---

### Task 1: 브랜치 + commerce_gold source 등록

**Files:**
- Modify: `domains/culture/models/sources.yml` (citydata_gold 블록 바로 아래, 파일 끝)

**Interfaces:**
- Produces: source `commerce_gold.gold_license_dong_category_matrix` — Task 2의 모델이 `{{ source('commerce_gold', 'gold_license_dong_category_matrix') }}`로 소비

- [ ] **Step 1: 브랜치 생성 (dev 최신에서)**

```bash
cd C:/Users/Dell3571/ask-seoul/ASAC-DBT
git checkout dev && git pull origin dev
git checkout -b feat/culture-dine-around
```

- [ ] **Step 2: sources.yml 끝(citydata_gold 블록 아래)에 commerce_gold source 추가**

```yaml

  # 크로스도메인 read(#308) — commerce published gold. ref 불가라 source 로 배선(citydata_gold 선례).
  #   read-only. culture 는 자기 스키마에만 write. dev=iceberg_dev.commerce / prod=iceberg.commerce.
  - name: commerce_gold
    description: commerce 도메인 published gold (ASAC-DBT domains/commerce) — 크로스도메인 read 전용
    database: "{{ target.database }}"
    schema: "{{ env_var('COMMERCE_SCHEMA', 'commerce') }}"
    tables:
      - name: gold_license_dong_category_matrix
        description: 동×업종 인허가 매트릭스 — admin_dong_code(#48 canonical 호환, 220동)·active_cnt·total_cnt·opened_last_365d. 식품 = major 'health' / category 'food' (raw 영문값)
```

- [ ] **Step 3: 커밋**

```bash
git add domains/culture/models/sources.yml
git commit -m "feat(culture): #308 commerce_gold 크로스도메인 source 등록

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(파싱 검증은 Task 2 Step 5의 컨테이너 build에 포함 — source 단독 parse를 위해 push/checkout 왕복을 추가하지 않는다)

---

### Task 2: 모델 + 계약 + 테스트

**Files:**
- Create: `domains/culture/models/gold/gold_culture_dine_around.sql`
- Modify: `domains/culture/models/gold/_culture_gold__models.yml` (파일 끝에 모델 블록 추가)
- Create: `domains/culture/tests/assert_dine_around_consistency.sql`

**Interfaces:**
- Consumes: Task 1의 source `commerce_gold.gold_license_dong_category_matrix`; 기존 `ref('gold_culture_activity_by_dong')` (컬럼: admin_dong_code·admin_dong·gu_code·gu·event_date·activities_count·performances_count)
- Produces: 테이블 `gold_culture_dine_around` — 12컬럼 계약(아래 yml), 그레인 admin_dong_code(426행)

- [ ] **Step 1: 모델 SQL 작성**

`domains/culture/models/gold/gold_culture_dine_around.sql`:

```sql
-- gold(크로스도메인): 동별 문화 밀도 × 요식업 스톡 — "공연 보고 밥 먹기 좋은 동네"(#308, 티어링 v2 #8).
--   그레인: admin_dong_code (426동 스카폴드 = activity_by_dong 전체 유지, 요식업은 left join).
--   문화 축 = 다가오는 90일 행사량(current_date 기준 — 빌드 시점마다 창이 굴러감, 일 배치 전제).
--   요식업 축 = commerce 인허가 스톡(category='food' active). culture 첫 commerce read (source 경유).
--   ⚠ commerce 동 매핑 커버리지 219/426동(51.4%, 7/21 실측) — 미커버 동은 has_dining_data=false,
--   dining_*·dining_stock_pctl·dine_around_score 모두 null (동 자체는 스카폴드에 남는다).
--   score = 두 축 percent_rank 기하평균: 둘 다 높아야 높다. 순위 질의는 score desc 정렬.

with culture as (
    select
        admin_dong_code,
        max(admin_dong)                as admin_dong,
        max(gu_code)                   as gu_code,
        max(gu)                        as gu,
        sum(case when event_date between current_date and current_date + interval '90' day
                 then activities_count else 0 end)   as events_upcoming_90d,
        sum(case when event_date between current_date and current_date + interval '90' day
                 then performances_count else 0 end) as performances_upcoming_90d
    from {{ ref('gold_culture_activity_by_dong') }}
    group by admin_dong_code
),

dining as (
    select
        admin_dong_code,
        sum(active_cnt)          as dining_active_cnt,
        sum(opened_last_365d)    as dining_opened_365d
    from {{ source('commerce_gold', 'gold_license_dong_category_matrix') }}
    where category = 'food'
    group by admin_dong_code
),

joined as (
    select
        c.admin_dong_code,
        c.admin_dong,
        c.gu_code,
        c.gu,
        c.events_upcoming_90d,
        c.performances_upcoming_90d,
        d.dining_active_cnt,
        d.dining_opened_365d,
        d.admin_dong_code is not null as has_dining_data
    from culture c
    left join dining d on d.admin_dong_code = c.admin_dong_code
),

ranked as (
    select
        *,
        percent_rank() over (order by events_upcoming_90d) as culture_events_pctl,
        -- 요식업 pctl 은 데이터 있는 동끼리만 경쟁 (partition 으로 분리 후 false 쪽은 버림)
        case when has_dining_data
             then percent_rank() over (partition by has_dining_data order by dining_active_cnt)
        end as dining_stock_pctl
    from joined
)

select
    admin_dong_code,
    admin_dong,
    gu_code,
    gu,
    cast(events_upcoming_90d as integer)        as events_upcoming_90d,
    cast(performances_upcoming_90d as integer)  as performances_upcoming_90d,
    cast(dining_active_cnt as integer)          as dining_active_cnt,
    cast(dining_opened_365d as integer)         as dining_opened_365d,
    has_dining_data,
    round(culture_events_pctl, 3)               as culture_events_pctl,
    round(dining_stock_pctl, 3)                 as dining_stock_pctl,
    round(sqrt(culture_events_pctl * dining_stock_pctl), 3) as dine_around_score
from ranked
```

- [ ] **Step 2: 계약 yml 블록 추가**

`domains/culture/models/gold/_culture_gold__models.yml` 파일 끝에:

```yaml

  - name: gold_culture_dine_around
    description: 동별 문화 밀도 × 요식업 스톡 프로필(그레인 admin_dong_code, 426동 스카폴드, #308·티어링 v2). culture 첫 commerce 크로스도메인 read. 문화 축=다가오는 90일 행사량(빌드 시점 롤링), 요식업 축=식품 인허가 active 스톡. dine_around_score=두 축 percent_rank 기하평균 — "공연 보고 밥 먹기 좋은 동네" 정렬 키. ⚠ commerce 동 매핑 커버리지 219/426(51.4%) — 미커버 동은 has_dining_data=false·dining_*/score null.
    config:
      contract:
        enforced: true   # published gold 계약(#180)
      meta:
        external: true   # 외부 카탈로그 공개(#269 티어링 v2 — 명시적 true 첫 사용, #308 AC)
    columns:
      - name: admin_dong_code
        description: 행정동 코드(#48 행안부10 canonical) — 그레인 키
        data_type: varchar
        tests: [not_null, unique]
      - name: admin_dong
        description: 행정동 이름
        data_type: varchar
        tests: [not_null]
      - name: gu_code
        description: 자치구 코드(#48 공간축)
        data_type: varchar
      - name: gu
        description: 자치구 이름
        data_type: varchar
      - name: events_upcoming_90d
        description: 다가오는 90일(current_date~+90d) 문화 행사·활동 총량(activities_count 합)
        data_type: integer
        tests: [not_null]
      - name: performances_upcoming_90d
        description: 다가오는 90일 공연 수(performances_count 합) — "공연 보고" 축의 직접 지표
        data_type: integer
        tests: [not_null]
      - name: dining_active_cnt
        description: 식품 인허가 영업중(active) 스톡 — commerce gold_license_dong_category_matrix(category='food'). 미커버 동은 null
        data_type: integer
      - name: dining_opened_365d
        description: 최근 365일 식품 신규 개업 수 — 상권 활력 프록시. 미커버 동은 null
        data_type: integer
      - name: has_dining_data
        description: commerce 동 매핑 커버 여부(219/426, 7/21 실측) — false면 dining_*·dining_stock_pctl·dine_around_score 전부 null
        data_type: boolean
        tests: [not_null]
      - name: culture_events_pctl
        description: events_upcoming_90d 의 426동 내 percent_rank(0~1, 높을수록 문화 밀도 상위)
        data_type: double
        tests: [not_null]
      - name: dining_stock_pctl
        description: dining_active_cnt 의 커버 동(219) 내 percent_rank(0~1). 미커버 동은 null
        data_type: double
      - name: dine_around_score
        description: sqrt(culture_events_pctl × dining_stock_pctl) — 둘 다 높아야 높은 결합 점수(0~1). 미커버 동은 null
        data_type: double
```

- [ ] **Step 3: 싱귤러 테스트 작성**

`domains/culture/tests/assert_dine_around_consistency.sql`:

```sql
-- #308: dine_around 정합 — pctl/score 범위(0~1)와 has_dining_data ↔ null 동조. 위반 행 반환 시 실패.
select *
from {{ ref('gold_culture_dine_around') }}
where (culture_events_pctl < 0 or culture_events_pctl > 1)
   or (dining_stock_pctl is not null and (dining_stock_pctl < 0 or dining_stock_pctl > 1))
   or (dine_around_score is not null and (dine_around_score < 0 or dine_around_score > 1))
   or (has_dining_data and (dining_active_cnt is null or dining_stock_pctl is null or dine_around_score is null))
   or ((not has_dining_data) and (dining_active_cnt is not null or dining_stock_pctl is not null or dine_around_score is not null))
```

- [ ] **Step 4: 커밋 + push**

```bash
git add domains/culture/models/gold/gold_culture_dine_around.sql \
        domains/culture/models/gold/_culture_gold__models.yml \
        domains/culture/tests/assert_dine_around_consistency.sql
git commit -m "feat(culture): #308 gold_culture_dine_around — 동별 문화 밀도 × 요식업 스톡

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push -u origin feat/culture-dine-around
```

- [ ] **Step 5: 컨테이너에서 브랜치 checkout + build (모델+계약+테스트 전부)**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git fetch origin && git checkout --detach origin/feat/culture-dine-around
cd C:/Users/Dell3571/ask-seoul/sample
MSYS_NO_PATHCONV=1 docker compose exec -T airflow-scheduler bash -lc \
  'cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt build --select gold_culture_dine_around --project-dir . --profiles-dir . --target dev'
```

Expected: `PASS` — 모델 1 + not_null 5·unique 1 + 싱귤러 1 = OK 8, ERROR 0. (contract 위반이나 컬럼 타입 불일치 시 여기서 실패 — SQL의 cast를 계약 data_type과 대조)

---

### Task 3: AC 실측 + 문서 동승 + PR + dev 복귀

**Files:**
- 기작성 커밋 동승: `domains/culture/docs/design/2026-07-21-gold-tiering-v2.md`, `domains/culture/docs/design/2026-07-21-dine-around-plan.md`

**Interfaces:**
- Consumes: Task 2가 빌드한 `iceberg_dev.culture.gold_culture_dine_around`

- [ ] **Step 1: AC 실측 쿼리 3종**

```bash
cd C:/Users/Dell3571/ask-seoul/sample
MSYS_NO_PATHCONV=1 docker compose exec -T trino trino --output-format CSV --execute \
 "select count(*) rows, count_if(has_dining_data) covered, count_if(dine_around_score is not null) scored from iceberg_dev.culture.gold_culture_dine_around"
```

Expected: `rows=426, covered=219, scored=219`

```bash
MSYS_NO_PATHCONV=1 docker compose exec -T trino trino --output-format CSV --execute \
 "select admin_dong, gu, events_upcoming_90d, dining_active_cnt, dine_around_score from iceberg_dev.culture.gold_culture_dine_around order by dine_around_score desc nulls last limit 5"
```

Expected: 상위 5동이 상식적(홍대·서교동/명동/종로 계열 등 문화+요식 밀집 동네). 비상식적이면 window·필터 재점검.

```bash
MSYS_NO_PATHCONV=1 docker compose exec -T trino trino --output-format CSV --execute \
 "select count(*) from iceberg_dev.culture.gold_culture_dine_around where has_dining_data = false and gu is not null"
```

Expected: 미커버 207동 확인(426-219). 결과를 PR body에 실측으로 기록.

- [ ] **Step 2: 설계·플랜 문서 커밋**

```bash
cd C:/Users/Dell3571/ask-seoul/ASAC-DBT
git add domains/culture/docs/design/2026-07-21-gold-tiering-v2.md \
        domains/culture/docs/design/2026-07-21-dine-around-plan.md
git commit -m "docs(culture): #308 티어링 v2 설계 + dine_around 구현 계획

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

- [ ] **Step 3: PR 생성 (base dev, 셀프 머지 금지)**

```bash
PYTHONIOENCODING=utf-8 gh pr create --base dev --title "[Feat] gold_culture_dine_around — 동별 문화 밀도 × 요식업 스톡 (#308)" --body "## 무엇을

티어링 v2 외부 공개 7번째 마트. culture 첫 commerce 크로스도메인 read (source 경유 read-only).

- 그레인 admin_dong_code 426동 스카폴드, commerce 커버 219동 left join
- 문화 축: 다가오는 90일 행사량 / 요식업 축: 식품 인허가 active 스톡
- dine_around_score = 두 축 percent_rank 기하평균

## 실측 (AC)

- [x] dbt build PASS (contract enforced + not_null·unique + 싱귤러 정합 테스트)
- [x] rows=426 · covered=219 · scored=219 (커버리지 51.4% — has_dining_data 플래그로 명시)
- [x] meta.external=true — 카탈로그 외부 노출
- [x] 자기 스키마 밖 write 없음 (commerce_gold source read-only)

## 참고

- 설계: domains/culture/docs/design/2026-07-21-gold-tiering-v2.md
- Closes #308

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

(Step 1 실측값을 body에 반영해 수치가 다르면 수정 후 생성)

- [ ] **Step 4: sample/dbt dev 복귀**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git checkout dev
```

Expected: `Switched to branch 'dev'` — 컨테이너 마운트가 dev로 복원됨. 오늘 밤 03:00 transform 런은 dev 기준(dine_around는 머지 전이므로 미포함)이 정상.

- [ ] **Step 5: #308 이슈에 PR 링크 코멘트 + 진행 보고**

```bash
cd C:/Users/Dell3571/ask-seoul/ASAC-DBT
PYTHONIOENCODING=utf-8 gh issue comment 308 --body "구현 PR 생성: (PR 링크). 실측 rows=426·covered=219·scored=219. 머지는 리뷰 대기.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Self-Review 체크

- 스펙 커버: source 등록(T1)·모델+contract+external(T2)·커버리지 갭 처리(has_dining_data, T2)·빌드/테스트+실측+외부 노출 확인(T3) — #308 AC 전부 매핑. "카탈로그 스냅샷 노출 확인"은 머지 후 extract 재실행 사안이라 PR 범위 밖(이슈에 후속 명기)
- 플레이스홀더 없음 · 타입 일치: SQL cast(integer/boolean/double) = yml data_type 동일 순서 대조 완료
- 주의: `_culture_gold__models.yml` 끝 블록 추가 시 기존 마지막 모델(qa_eval 계열)과 들여쓰기 레벨(2칸, `  - name:`) 일치 확인

# culture quality_status + 미래 커버리지 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** culture silver에 공간축 정밀도 표식 `quality_status`(3치)를 도입하고 gold로 롤업, freshness 대체로 미래 커버리지 warn 계측을 추가한다.

**Architecture:** 각 silver의 최종 select를 `stamped` CTE로 감싸고 공통 매크로 `culture_quality_status()`로 표준 컬럼(admin_dong_code/gu_code)의 null 여부에서 3치 enum을 파생한다(순수 파생, 새 조인 없음). gold는 이 컬럼을 카운트 집계한다. 미래 커버리지는 기간 fact 6개의 `max(event_start_date)`가 임계일 이상 미래를 덮는지 warn singular test로 감시한다.

**Tech Stack:** dbt (trino adapter), Iceberg on R2. dbt-only, 인프라 게이트 없음.

## Global Constraints

- 설계: `domains/culture/docs/design/2026-07-10-culture-quality-status.md` (승인·커밋됨)
- 브랜치: `feat/111-quality-status` (체크아웃됨, dev 기준)
- quality_status 값: `dong_precise` / `gu_only` / `unmatched` (정확히 이 3개, snake_case)
- 미래 커버리지 임계: `var('culture_future_coverage_days', 14)` (기본 14일)
- freshness는 **warn 계측 전용** — error 하드게이트 금지 (culture는 미래 event_at이 정상)
- 커밋 마지막 줄: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- PR body 마지막: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
- 머지는 사용자 (셀프 머지 금지)
- dev 검증 헬퍼 (컨테이너, `--no-partial-parse` 필수):
  ```
  cd C:/Users/Dell3571/ask-seoul/sample
  MSYS_NO_PATHCONV=1 docker compose exec -T airflow-scheduler bash -lc 'export DBT_PROFILES_DIR=/opt/airflow/dbt/domains/culture DBT_PROJECT_DIR=/opt/airflow/dbt/domains/culture; cd /opt/airflow/dbt/domains/culture; /home/airflow/dbt-venv/bin/dbt <ARGS> --no-partial-parse --target dev --no-use-colors'
  ```
- 작업 후 dev 브랜치 복귀 필수 (컨테이너가 워킹트리 마운트)

## File Structure

- `macros/culture_axes.sql` — `culture_quality_status()` 매크로 추가 (Task 1)
- `models/silver/silver_culture_{event,performance,festival,exhibition,sejong,kcisa_event,reservation,facility,space,sports_event}.sql` — 최종 select stamped 래핑 + quality_status (Task 1)
- `models/schema.yml` — silver 10개 quality_status 계약 (Task 1) + gold 카운트 계약 (Task 2)
- `models/gold/gold_culture_location_daily.sql` · `gold_culture_reservation_daily.sql` · `gold_culture_sports_schedule.sql` — 전파 (Task 2)
- `models/gold/gold_culture_activity_by_dong.sql` — 특성 주석만 (Task 2)
- `tests/assert_culture_future_event_coverage.sql` — 미래 커버리지 warn (Task 3)
- `README.md` + `docs/design/change-log`(있으면) — 주의점 갱신 (Task 4)

---

## Task 1: quality_status 매크로 + silver 10개 + 계약

**Files:**
- Modify: `macros/culture_axes.sql` (매크로 추가)
- Modify: silver 10개 (위 목록)
- Modify: `models/schema.yml` (10개 quality_status 계약)

**Interfaces:**
- Produces: `culture_quality_status(dong_col='admin_dong_code', gu_col='gu_code')` 매크로 → `case` 식 문자열. 각 silver 최종에 `{{ culture_quality_status() }} as quality_status` 컬럼. gold(Task 2)가 이 컬럼을 소비.

- [ ] **Step 1: 매크로 추가** — `macros/culture_axes.sql` 끝(파일 마지막 `{%- endmacro %}` 뒤)에 추가:

```sql

{#
  culture_quality_status — 공간축 정밀도 3치 표식(#111). 최종 컬럼 null 여부로 순수 파생.
  - dong_precise : admin_dong_code 있음(좌표 point-in-polygon 성공, 행정동까지)
  - gu_only      : admin_dong_code 없고 gu_code 있음(좌표 없어 구 레벨 근사)
  - unmatched    : 둘 다 없음(구도 미확정)
  stamped CTE 뒤에서 표준 컬럼명으로 무인자 호출. #48 오배정 계측과 같은 "계측 전용" 철학.
#}
{% macro culture_quality_status(dong_col='admin_dong_code', gu_col='gu_code') -%}
case
    when {{ dong_col }} is not null then 'dong_precise'
    when {{ gu_col }}   is not null then 'gu_only'
    else                                'unmatched'
end
{%- endmacro %}
```

- [ ] **Step 2: silver 10개 stamped 래핑** — 각 모델의 **최종 `select ... from ...`**(맨 끝 쿼리)을 `stamped as (\n<기존 최종 select>\n)` CTE로 감싸고, 그 뒤에 파생 select 추가. `with` 체인 마지막 CTE 뒤 콤마 처리 주의.

패턴 (모든 10개 동일):
```sql
-- 기존 파일 끝:
--   <CTE들...>
--   select <컬럼들> from <소스> <조인들>
--
-- 변경 후:
--   <CTE들...>,
--   stamped as (
--       select <컬럼들> from <소스> <조인들>
--   )
--   select *, {{ culture_quality_status() }} as quality_status
--   from stamped
```

구체 적용 (각 파일):
- **event**: 마지막 `select l.event_id... from latest l left join dong_map d... left join canon cd... left join canon_gu cg...` 전체를 `stamped as ( ... )`로. 앞 CTE 체인 끝에 콤마.
- **sports_event**: 마지막 `select p.game_date... from placed p left join dong_map d... left join canon cd... left join canon_gu cg...`. **주의: sports_event 최종 select에 gu_code/admin_dong_code alias는 있으나 lineage 축약형** — stamped 래핑 후 동일.
- **facility**: 마지막 `select j.facility_id... from joined j left join dong_map d... left join canon...`.
- **performance / festival**: facility 경유 — 최종 select에 `f.gu_code, f.admin_dong_code` (표준 alias). stamped 래핑 동일.
- **exhibition / sejong / kcisa_event / reservation / space**: 각 최종 select를 stamped로.

각 파일에서 stamped 앞 CTE의 닫는 `)` 뒤에 **콤마**를 붙이고, 최종 select를 stamped 본문으로 이동, 마지막에 2줄 추가:
```sql
select *, {{ culture_quality_status() }} as quality_status
from stamped
```

- [ ] **Step 3: schema.yml 계약 추가** — `models/schema.yml`의 silver 10개 각 모델 `columns:` 아래에 추가:

```yaml
      - name: quality_status
        description: "공간축 정밀도(#111) — dong_precise(좌표→행정동)/gu_only(구 레벨 근사)/unmatched"
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: [dong_precise, gu_only, unmatched]
```

> 주의: 이 dbt 버전은 `accepted_values`의 인자를 `arguments:` 아래 중첩 요구(파싱 경고 `MissingArgumentsPropertyInGenericTestDeprecation` 회피). 기존 schema.yml의 다른 generic test 작성 형태를 따를 것 — 만약 기존이 `values:`를 직접 두는 형태면 그 형태에 맞춘다(파일 내 일관성 우선).

- [ ] **Step 4: 파싱 + 계약 검증** — 컨테이너 dev:

```
<헬퍼> parse
<헬퍼> build --select silver_culture_event silver_culture_performance silver_culture_festival silver_culture_exhibition silver_culture_sejong silver_culture_kcisa_event silver_culture_reservation silver_culture_facility silver_culture_space silver_culture_sports_event
```
Expected: 10개 모델 빌드 + accepted_values 20개 test(각 not_null+accepted_values) PASS. 0 ERROR. facility는 quality_status 전량 `dong_precise` 예상(좌표 100%).

- [ ] **Step 5: 커밋**

```bash
git add macros/culture_axes.sql models/silver/ models/schema.yml
git commit -m "feat(culture): quality_status 공간축 정밀도 표식 — silver 10개 (#111)

$(printf '')culture_quality_status() 매크로(3치 dong_precise/gu_only/unmatched 순수 파생)
+ silver 10개 stamped 래핑 + schema.yml accepted_values 계약.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: gold 전파

**Files:**
- Modify: `models/gold/gold_culture_location_daily.sql`
- Modify: `models/gold/gold_culture_reservation_daily.sql`
- Modify: `models/gold/gold_culture_sports_schedule.sql`
- Modify: `models/gold/gold_culture_activity_by_dong.sql` (주석만)
- Modify: `models/schema.yml` (gold 카운트 계약)

**Interfaces:**
- Consumes: silver 10개의 `quality_status` 컬럼 (Task 1)
- Produces: `gold_culture_location_daily.dong_precise_count`, `gold_culture_reservation_daily.dong_precise_count`, `gold_culture_sports_schedule.quality_status`

- [ ] **Step 1: location_daily — union에 quality_status 전파 + 집계** — `gold_culture_location_daily.sql`:

`raw_activities`의 **6개 union select 각각**에 `quality_status`를 끝 컬럼으로 추가:
```sql
    select gu_code, gu, cast(performance_id as varchar) as activity_id, 'performance' as activity_type, event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_performance') }}
    union all
    select gu_code, gu, event_key, 'event', event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_event') }}
    union all
    select gu_code, gu, cast(festival_id as varchar), 'festival', event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_festival') }}
    union all
    select gu_code, gu, cast(exhibition_id as varchar), 'exhibition', event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_exhibition') }}
    union all
    select gu_code, gu, cast(sejong_id as varchar), 'sejong', event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_sejong') }}
    union all
    select gu_code, gu, 'kcisa:' || event_id,
           case service_name
               when '전시' then 'exhibition'
               when '공연' then 'performance'
               when '행사/축제' then 'festival'
               else 'event'
           end,
           event_start_date, event_end_date, quality_status
    from {{ ref('silver_culture_kcisa_event') }}
```

`expanded`에 `a.quality_status` 전파:
```sql
expanded as (
    select a.gu_code, a.gu, a.activity_id, a.activity_type, a.quality_status, d.activity_date
    from activities a
    cross join unnest(sequence(a.event_start_date, a.event_end_date, interval '1' day)) as d(activity_date)
)
```

최종 집계에 `dong_precise_count` 추가 (`sejong_count` 뒤):
```sql
    count(distinct case when activity_type = 'sejong'      then activity_id end) as sejong_count,
    count(distinct case when quality_status = 'dong_precise' then activity_id end) as dong_precise_count
```
> 의미: 이 구-일 활동 중 좌표로 행정동까지 정밀한 활동 수. (unmatched는 activities CTE의 `where gu_code is not null`로 이미 제외 — gu_code 그레인 특성. 즉 dong_precise + gu_only만 존재)

- [ ] **Step 2: reservation_daily — dong_precise_count 추가** — `gold_culture_reservation_daily.sql` (svc는 이미 `select *`라 quality_status 포함됨). 최종 select `availability_rate` 뒤에 추가:
```sql
    round(1.0 * count(case when status = '접수중' then 1 end) / nullif(count(*), 0), 3) as availability_rate,
    count(case when quality_status = 'dong_precise' then 1 end) as dong_precise_count
```

- [ ] **Step 3: sports_schedule — quality_status 컬럼 노출** — `gold_culture_sports_schedule.sql`의 최종 select에 `admin_dong_code` 뒤 추가:
```sql
    admin_dong,
    admin_dong_code,
    quality_status
from {{ ref('silver_culture_sports_event') }}
```

- [ ] **Step 4: activity_by_dong — 특성 주석 추가** — `gold_culture_activity_by_dong.sql` 파일 상단 주석 블록에 한 줄 추가 (코드 변경 없음):
```sql
-- 주의(#111): admin_dong_code 그레인이라 정의상 quality_status='dong_precise' 활동만 포함된다.
--   좌표 없는 활동(gu_only)은 이 gold 에서 누락 — 구 레벨 집계는 gold_culture_location_daily 참조.
```

- [ ] **Step 5: schema.yml gold 계약** — `gold_culture_location_daily`·`gold_culture_reservation_daily` 각 `columns:`에 추가, `gold_culture_sports_schedule`에 quality_status 계약:
```yaml
      - name: dong_precise_count
        description: "좌표로 행정동까지 정밀한 활동 수(#111 quality_status='dong_precise')"
        tests:
          - not_null
```
sports_schedule에는:
```yaml
      - name: quality_status
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: [dong_precise, gu_only, unmatched]
```

- [ ] **Step 6: 빌드 검증**

```
<헬퍼> build --select gold_culture_location_daily gold_culture_reservation_daily gold_culture_sports_schedule
```
Expected: 3개 gold + 계약 test PASS, 0 ERROR. `dong_precise_count` not_null PASS.

- [ ] **Step 7: 커밋**

```bash
git add models/gold/ models/schema.yml
git commit -m "feat(culture): quality_status gold 전파 — dong_precise_count·sports 노출 (#111)

location_daily·reservation_daily에 dong_precise_count 집계, sports_schedule
quality_status 노출, activity_by_dong 특성(dong_precise 전용) 주석.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: 미래 커버리지 warn 계측

**Files:**
- Create: `tests/assert_culture_future_event_coverage.sql`

**Interfaces:**
- Consumes: 기간 fact 6개 silver의 `event_start_date`

- [ ] **Step 1: singular test 작성** — `tests/assert_culture_future_event_coverage.sql`:

```sql
-- 미래 행사 재고 감시(#111) — 소스가 신규 공급을 멈추면 max(event_start_date)가
-- current_date 로 다가온다. event-time(등록 시각) 부재의 유일한 proxy.
-- warn 계측 전용: 이미 등록된 미래 재고가 남으면 신규 정체를 못 잡는 원천 한계(설계 §3).
-- error 하드게이트 아님(culture 는 미래 시작일이 정상).
{{ config(severity='warn') }}

with sources as (
    select 'event'       as src, max(event_start_date) as max_start from {{ ref('silver_culture_event') }}
    union all select 'performance', max(event_start_date) from {{ ref('silver_culture_performance') }}
    union all select 'festival',    max(event_start_date) from {{ ref('silver_culture_festival') }}
    union all select 'exhibition',  max(event_start_date) from {{ ref('silver_culture_exhibition') }}
    union all select 'sejong',      max(event_start_date) from {{ ref('silver_culture_sejong') }}
    union all select 'kcisa',       max(event_start_date) from {{ ref('silver_culture_kcisa_event') }}
)
select src, max_start
from sources
where max_start is null
   or max_start < date_add('day', {{ var('culture_future_coverage_days', 14) }}, current_date)
```

- [ ] **Step 2: 실행 확인**

```
<헬퍼> test --select assert_culture_future_event_coverage
```
Expected: PASS 또는 WARN. WARN이면 어느 src가 임계 미달인지 출력(현재 7월이라 대부분 통과 예상 — 비수기 소스만 걸릴 수 있음). ERROR 아님 확인.

- [ ] **Step 3: 커밋**

```bash
git add tests/assert_culture_future_event_coverage.sql
git commit -m "feat(culture): 미래 행사 커버리지 warn 계측 — freshness 대체 (#111)

기간 fact 6개 max(event_start_date) < today+14일이면 warn. 등록 시각
부재의 proxy(하드게이트 아님). var('culture_future_coverage_days', 14).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: dev 실측 검증 + 문서 + PR

**Files:**
- Modify: `README.md` (주의점 갱신)

- [ ] **Step 1: 전체 빌드 무회귀 확인**

```
<헬퍼> build
```
Expected: 전체 PASS, 0 ERROR. WARN은 기존 오배정 계측 + 신규 미래 커버리지(있으면)만.

- [ ] **Step 2: quality_status 분포 실측** — Trino:
```
cd C:/Users/Dell3571/ask-seoul/sample
docker compose exec -T trino trino --output-format TSV --execute "
select 'event' t, quality_status, count(*) from iceberg_dev.culture.silver_culture_event group by 2
union all select 'facility', quality_status, count(*) from iceberg_dev.culture.silver_culture_facility group by 2
order by 1,2"
```
Expected: facility 전량 dong_precise(좌표 100%), event는 dong_precise/gu_only 혼합. unmatched 소수/0.

- [ ] **Step 3: gold 정합 확인** — location_daily의 dong_precise_count ≤ activities_count 확인:
```
docker compose exec -T trino trino --execute "select count(*) from iceberg_dev.culture.gold_culture_location_daily where dong_precise_count > activities_count"
```
Expected: 0 (품질 카운트가 전체 카운트 초과 불가).

- [ ] **Step 4: README 주의점 갱신** — `README.md`의 "주의점 — 정직 구간" 절에 2항목 추가:
```markdown
7. **`quality_status` 활용**(#111): 각 공간축 silver·`gold_culture_sports_schedule`에 `dong_precise`(좌표로 행정동 정밀)/`gu_only`(구 레벨 근사)/`unmatched` 표식. **동 레벨 분석은 `where quality_status = 'dong_precise'`** 권장.
8. **`gold_culture_activity_by_dong`는 `dong_precise`만**: admin_dong_code 그레인이라 좌표 없는 활동(gu_only)은 누락됩니다. 구 레벨 전체는 `gold_culture_location_daily`(+`dong_precise_count`)를 보세요.
```

- [ ] **Step 5: 커밋 + push + PR**

```bash
git add README.md
git commit -m "docs(culture): README — quality_status 소비 가이드 + activity_by_dong 특성 (#111)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push -u origin feat/111-quality-status
```
PR (base dev): 제목 `feat(culture): quality_status 공간축 정밀도 표식 + 미래 커버리지 계측 (#111)`, body에 4파트 요약 + dev 실측(분포·정합) + `Closes #111` + `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 6: dev 복귀**

```bash
git checkout dev
```

---

## Self-Review 체크

- **Spec 커버리지**: ①매크로+silver 10개(Task1) ②gold 전파(Task2) ③미래 커버리지(Task3) ④검증·문서(Task4). 설계 §1~§4 전부 커버.
- **범위 밖 준수**: WAP·격리 테이블·event-time 진짜 신선도는 미포함(설계 §5).
- **타입 일관**: quality_status 값 3개 동일(dong_precise/gu_only/unmatched) 전 task. dong_precise_count 명칭 gold 2곳 동일.

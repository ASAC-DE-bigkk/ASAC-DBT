# KCISA 서울 행사 silver/gold 편입 (#85) — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bronze_kcisa_seoul_event`(523 seq)를 전량 silver로 편입하되 3축(performance·event·exhibition) anti-join dedup 후 `gold_culture_location_daily`에 합산한다.

**Architecture:** 신규 `silver_culture_kcisa_event` 1개(seq 스냅샷 dedup → 정규화 제목+기간 겹침 anti-join → 내장 좌표 행정동 매핑) + gold union 1건 추가. 기존 축 모델은 무수정 — 기존 축이 정본, 중복 시 KCISA 행 제거.

**Tech Stack:** dbt-trino(dev=iceberg_dev.culture), culture_lineage/culture_dedup_order/culture_dong_map 매크로, asac_axes 패키지.

## Global Constraints

- 설계 문서: `domains/culture/docs/design/2026-07-10-culture-kcisa-silver-gold.md` (승인됨) — 세부 근거는 이 문서가 정본.
- 워킹트리: `C:\Users\Dell3571\ask-seoul\sample\dbt` (컨테이너가 `/opt/airflow/dbt`로 마운트). 브랜치 `feat/85-culture-kcisa-silver-gold`.
- dbt 명령은 **컨테이너에서 dev 타깃 + `--no-partial-parse` 필수** (신규 파일 캐시 이슈 선례):

  ```powershell
  cd C:\Users\Dell3571\ask-seoul\sample
  docker compose exec -T airflow-scheduler bash -lc 'export DBT_PROFILES_DIR=/opt/airflow/dbt/domains/culture DBT_PROJECT_DIR=/opt/airflow/dbt/domains/culture; cd /opt/airflow/dbt/domains/culture; /home/airflow/dbt-venv/bin/dbt <ARGS> --no-partial-parse --target dev --no-use-colors'
  ```
- 자기 도메인(culture) 스키마 밖에 쓰지 않는다. API 키·시크릿 출력 금지.
- 커밋 메시지 마지막 줄: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- dedup 정규화 규칙(전 태스크 공통): `lower(regexp_replace(<제목>, '\s|\[.*?\]|\(.*?\)', ''))` — 매칭 = 정규화 제목 일치 AND (기간 교차 OR 어느 한쪽 기간 null). 기간 교차 = `a.start <= b.end AND a.end >= b.start`.
- gold `activity_id` 프리픽스: `'kcisa:' || event_id` (sema exhibition_id와 숫자 충돌 방지).
- 작업 종료 시 sample/dbt를 dev 브랜치로 복귀(컨테이너 마운트 오염 방지).

---

### Task 1: sources.yml 등록 + culture_norm_title 매크로

**Files:**
- Modify: `domains/culture/models/sources.yml` (파일 끝, `bronze_kopis_performance_detail` 엔트리 뒤)
- Modify: `domains/culture/macros/culture_axes.sql` (파일 끝)

**Interfaces:**
- Produces: `source('culture_bronze', 'bronze_kcisa_seoul_event')` 참조 가능. `{{ culture_norm_title('<컬럼>') }}` — varchar 식을 받아 정규화 제목(varchar) 방출. Task 2의 silver 모델과 singular 테스트가 이 둘을 사용.

- [ ] **Step 1: sources.yml에 bronze_kcisa_seoul_event 추가** — 파일 끝(`bronze_kopis_performance_detail`의 columns 뒤)에 append:

```yaml
      - name: bronze_kcisa_seoul_event
        description: KCISA 한눈에보는문화정보(area2, sido=서울) 원본 — 현재 활성 행사 스냅샷. seq 자연키, 좌표(gpsX=경도·gpsY=위도)·sigungu 내장. 국립기관 전시 구멍 보강 원천(#85)
        columns:
          - name: record_json
            description: 원본 레코드(JSON) — seq·title·place·serviceName·realmName·sigungu·startDate/endDate(YYYYMMDD)·gpsX/gpsY
          - name: load_date
            description: 적재 파티션 일자(KST)
          - name: ingest_ts
            description: 적재 실행 식별 타임스탬프(UTC)
```

- [ ] **Step 2: culture_axes.sql에 정규화 매크로 추가** — 파일 끝에 append (silver 모델과 singular 테스트가 같은 규칙을 쓰도록 DRY):

```sql
{#
  norm_title — 소스 간 제목 표기 차이(공백·괄호 부가어·대소문자)를 무력화한
  dedup 매칭 키(#85). silver_culture_kcisa_event 와 assert_kcisa_no_cross_duplicate 가 공유.
#}
{% macro culture_norm_title(expr) -%}
lower(regexp_replace({{ expr }}, '\s|\[.*?\]|\(.*?\)', ''))
{%- endmacro %}
```

- [ ] **Step 3: parse 게이트** — Run (Global Constraints의 컨테이너 헬퍼로):

```
dbt parse --no-partial-parse --target dev --no-use-colors
```

Expected: `Performance info` 로그로 정상 종료(에러 0).

- [ ] **Step 4: 커밋**

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git add domains/culture/models/sources.yml domains/culture/macros/culture_axes.sql
git commit -m @'
feat(culture): #85 bronze_kcisa_seoul_event 소스 등록 + norm_title 매크로

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 2: silver_culture_kcisa_event + 계약 + 교차중복 0 테스트

**Files:**
- Create: `domains/culture/models/silver/silver_culture_kcisa_event.sql`
- Create: `domains/culture/tests/assert_kcisa_no_cross_duplicate.sql`
- Modify: `domains/culture/models/schema.yml` (파일 끝, `gold_culture_sports_schedule` 뒤)

**Interfaces:**
- Consumes: Task 1의 source·`culture_norm_title`. 기존 매크로 `culture_lineage('kcisa')`, `culture_dedup_order()`, `culture_dong_map('deduped')`, `asac_axes.seoul_lonlat('lon_raw','lat_raw')`(longitude/latitude 방출), seed `seoul_admin_dong_crosswalk`.
- Produces: `silver_culture_kcisa_event` — 컬럼 `event_id(varchar)·title·venue_name·service_name·category·event_start_date(date)·event_end_date(date)·event_at(timestamp(6))·longitude·latitude·gu·gu_code·admin_dong·admin_dong_code` + lineage 6종. Task 3의 gold가 `event_id·service_name·gu_code·gu·event_start_date·event_end_date`를 사용.

- [ ] **Step 1: silver 모델 작성** — `domains/culture/models/silver/silver_culture_kcisa_event.sql`:

```sql
-- silver: KCISA 한눈에보는문화정보 서울 행사 fact — 전 serviceName 편입(#85).
-- 그레인 event_id(=seq). 좌표 내장(gpsX=경도, gpsY=위도) → 행정동 직접 매핑.
-- 3축 anti-join dedup: 기존 축(performance·event·exhibition)이 정본 —
-- 정규화 제목 일치 + (기간 교차 or 한쪽 null)이면 KCISA 행을 버린다(보강 소스).
-- 기간 조건이 재공연(같은 제목·다른 시기)을 살린다(설계 §dedup, perf 102→97 실측).

with bronze as (
    select
        json_extract_scalar(record_json, '$.seq')         as event_id_raw,
        json_extract_scalar(record_json, '$.title')       as title_raw,
        json_extract_scalar(record_json, '$.place')       as place_raw,
        json_extract_scalar(record_json, '$.serviceName') as service_raw,
        json_extract_scalar(record_json, '$.realmName')   as realm_raw,
        json_extract_scalar(record_json, '$.sigungu')     as gu_raw,
        json_extract_scalar(record_json, '$.startDate')   as start_raw,
        json_extract_scalar(record_json, '$.endDate')     as end_raw,
        json_extract_scalar(record_json, '$.gpsX')        as lon_raw,   -- 경도
        json_extract_scalar(record_json, '$.gpsY')        as lat_raw,   -- 위도
        ingest_ts,
        {{ culture_lineage('kcisa') }}
    from {{ source('culture_bronze', 'bronze_kcisa_seoul_event') }}
),

typed as (
    select
        event_id_raw as event_id,
        nullif(trim(title_raw), '')   as title,
        nullif(trim(place_raw), '')   as venue_name,
        nullif(trim(service_raw), '') as service_name,
        nullif(trim(realm_raw), '')   as category,
        nullif(trim(gu_raw), '')      as gu,
        try(cast(date_parse(start_raw, '%Y%m%d') as date)) as event_start_date,
        try(cast(date_parse(end_raw, '%Y%m%d') as date))   as event_end_date,
        {{ asac_axes.seoul_lonlat('lon_raw', 'lat_raw') }},
        ingest_ts, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
    from bronze
    where event_id_raw is not null
      and nullif(trim(title_raw), '') is not null
),

latest as (
    select * from (
        select *, row_number() over (partition by event_id order by {{ culture_dedup_order() }}) as rn
        from typed
    ) where rn = 1
),

normed as (
    select *, {{ culture_norm_title('title') }} as norm_title
    from latest
),

deduped as (
    select n.* from normed n
    where not exists (
        select 1 from {{ ref('silver_culture_performance') }} p
        where {{ culture_norm_title('p.performance_name') }} = n.norm_title
          and (p.event_start_date is null or p.event_end_date is null
               or n.event_start_date is null or n.event_end_date is null
               or (p.event_start_date <= n.event_end_date and p.event_end_date >= n.event_start_date))
    )
    and not exists (
        select 1 from {{ ref('silver_culture_event') }} e
        where {{ culture_norm_title('e.event_title') }} = n.norm_title
          and (e.event_start_date is null or e.event_end_date is null
               or n.event_start_date is null or n.event_end_date is null
               or (e.event_start_date <= n.event_end_date and e.event_end_date >= n.event_start_date))
    )
    and not exists (
        select 1 from {{ ref('silver_culture_exhibition') }} x
        where x.title is not null
          and {{ culture_norm_title('x.title') }} = n.norm_title
          and (x.event_start_date is null or x.event_end_date is null
               or n.event_start_date is null or n.event_end_date is null
               or (x.event_start_date <= n.event_end_date and x.event_end_date >= n.event_start_date))
    )
),

dong_map as {{ culture_dong_map('deduped') }},

gu_codes as (select distinct gu, gu_code from {{ ref('seoul_admin_dong_crosswalk') }})

select
    d.event_id, d.title, d.venue_name, d.service_name, d.category,
    d.event_start_date, d.event_end_date,
    cast(d.event_start_date as timestamp(6)) as event_at,
    d.longitude, d.latitude, d.gu,
    coalesce(g.gu_code, m.coord_gu_code) as gu_code,
    m.admin_dong, m.admin_dong_code,
    d.source_system, d.dag_run_id, d.raw_object_key, d.collected_at, d.ingested_at, d.load_date
from deduped d
left join dong_map m on d.longitude = m.longitude and d.latitude = m.latitude
left join gu_codes g on g.gu = d.gu
```

- [ ] **Step 2: singular 테스트 작성** — `domains/culture/tests/assert_kcisa_no_cross_duplicate.sql` (dedup 규칙과 동일 조건으로 3축 재검사 — 잔존 행이 있으면 실패, AC 직결):

```sql
-- #85: silver_culture_kcisa_event 에 3축(performance·event·exhibition) 교차 중복이
-- 남아 있으면 실패. 매칭 = 정규화 제목 일치 + (기간 교차 or 한쪽 기간 null).
with k as (
    select event_id, {{ culture_norm_title('title') }} as norm_title,
           event_start_date, event_end_date
    from {{ ref('silver_culture_kcisa_event') }}
),

axes as (
    select {{ culture_norm_title('performance_name') }} as norm_title,
           event_start_date, event_end_date
    from {{ ref('silver_culture_performance') }}
    union all
    select {{ culture_norm_title('event_title') }}, event_start_date, event_end_date
    from {{ ref('silver_culture_event') }}
    union all
    select {{ culture_norm_title('title') }}, event_start_date, event_end_date
    from {{ ref('silver_culture_exhibition') }}
    where title is not null
)

select k.event_id
from k
join axes a on a.norm_title = k.norm_title
where a.event_start_date is null or a.event_end_date is null
   or k.event_start_date is null or k.event_end_date is null
   or (a.event_start_date <= k.event_end_date and a.event_end_date >= k.event_start_date)
```

- [ ] **Step 3: schema.yml 계약 추가** — 파일 끝(`gold_culture_sports_schedule` 엔트리 뒤)에 append. `min_ratio: 0.5`는 Step 6에서 실측−5%p로 교체하는 임시 하한:

```yaml
  - name: silver_culture_kcisa_event
    description: KCISA 한눈에보는문화정보 서울 행사 fact — 전 serviceName 편입, 3축(performance·event·exhibition) anti-join dedup 잔존분(#85). 그레인 event_id(=seq), 좌표 내장.
    columns:
      - name: event_id
        tests: [not_null, unique]
      - name: title
        tests: [not_null]
      - name: load_date
        tests: [not_null]
      - name: ingested_at
        tests: [not_null]
      - name: longitude
        tests:
          - asac_axes.in_seoul_bbox:
              arguments: {kind: lon}
      - name: latitude
        tests:
          - asac_axes.in_seoul_bbox:
              arguments: {kind: lat}
      - name: gu_code
        tests:
          - asac_axes.axis_coverage:
              arguments: {min_ratio: 0.5}   # Task 2 Step 6에서 실측 -5%p로 확정
              config: {severity: warn}
```

- [ ] **Step 4: 빌드 + 테스트** — Run (컨테이너 헬퍼):

```
dbt build --select silver_culture_kcisa_event assert_kcisa_no_cross_duplicate --no-partial-parse --target dev --no-use-colors
```

Expected: 모델 1 + 테스트 8(unique·not_null 4·bbox 2·coverage 1·singular 1) 전부 PASS. 행수 로그 ~390(523 − 교차 dedup ~135, 자연 변동 허용).

- [ ] **Step 5: 국립기관 보강 실측 (AC)** — Run:

```powershell
cd C:\Users\Dell3571\ask-seoul\sample
docker compose exec -T trino trino --output-format TSV --execute "select count(*) from iceberg_dev.culture.silver_culture_kcisa_event where venue_name like '%국립%'"
```

Expected: > 0 (7/10 bronze 기준 국립기관 pool 24건 중 dedup 생존분). 대표 예시(국립현대미술관 서울관·국립중앙박물관 등) 몇 건을 `select title, venue_name`으로 뽑아 PR 본문용으로 기록.

- [ ] **Step 6: axis_coverage 실측 임계 확정** — Run:

```powershell
docker compose exec -T trino trino --output-format TSV --execute "select round(1.0*count(gu_code)/count(*), 4) from iceberg_dev.culture.silver_culture_kcisa_event"
```

실측 비율에서 5%p 뺀 값(소수 둘째 자리 내림)으로 schema.yml의 `min_ratio: 0.5`를 교체하고 주석을 `# 실측 XX.XX% - 5%p (#85 확정)`로 갱신. 예: 실측 0.9740 → `min_ratio: 0.92`. 교체 후 재실행:

```
dbt test --select silver_culture_kcisa_event --no-partial-parse --target dev --no-use-colors
```

Expected: 전부 PASS.

- [ ] **Step 7: 커밋**

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git add domains/culture/models/silver/silver_culture_kcisa_event.sql domains/culture/tests/assert_kcisa_no_cross_duplicate.sql domains/culture/models/schema.yml
git commit -m @'
feat(culture): #85 silver_culture_kcisa_event — 전량 편입 + 3축 anti-join dedup

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 3: gold_culture_location_daily 편입

**Files:**
- Modify: `domains/culture/models/gold/gold_culture_location_daily.sql` (raw_activities CTE — `silver_culture_sejong` arm 뒤)

**Interfaces:**
- Consumes: Task 2의 `silver_culture_kcisa_event`(event_id·service_name·gu_code·gu·event_start_date·event_end_date).
- Produces: gold union에 kcisa arm — `activity_id = 'kcisa:' || event_id`, `activity_type`은 serviceName 매핑(전시→exhibition, 공연→performance, 행사/축제→festival, 그 외→event). 기존 count 컬럼 의미 불변(합산).

- [ ] **Step 1: 편입 전 기준값 기록** — Run:

```powershell
cd C:\Users\Dell3571\ask-seoul\sample
docker compose exec -T trino trino --output-format TSV --execute "select sum(activities_count), sum(exhibitions_count), sum(performances_count) from iceberg_dev.culture.gold_culture_location_daily"
```

세 값을 기록(Step 4 델타 대조용).

- [ ] **Step 2: raw_activities에 kcisa arm 추가** — `gold_culture_location_daily.sql`의 `silver_culture_sejong` arm(`from {{ ref('silver_culture_sejong') }}`) 바로 뒤에:

```sql
    union all
    select gu_code, gu, 'kcisa:' || event_id,
           case service_name
               when '전시' then 'exhibition'
               when '공연' then 'performance'
               when '행사/축제' then 'festival'
               else 'event'   -- 교육/체험 등
           end,
           event_start_date, event_end_date
    from {{ ref('silver_culture_kcisa_event') }}
```

파일 상단 주석 1행도 갱신: `-- gold: culture 활동(공연·행사·축제·전시·세종·kcisa)을 gu_code × 일자로 집계 — #48 코드 축.`

- [ ] **Step 3: gold 빌드** — Run (컨테이너 헬퍼):

```
dbt build --select gold_culture_location_daily --no-partial-parse --target dev --no-use-colors
```

Expected: 모델 1 + gold 테스트(gu_code·event_date not_null) PASS.

- [ ] **Step 4: 델타 실측 (AC)** — Step 1 쿼리 재실행. Expected: 세 합계 모두 증가(전시·공연 합산 반영). 델타 값을 PR 본문용으로 기록. `'kcisa:'` 프리픽스 덕에 기존 id와 충돌 없음(감소·불변이면 편입 실패 — 중단·원인 조사).

- [ ] **Step 5: 커밋**

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git add domains/culture/models/gold/gold_culture_location_daily.sql
git commit -m @'
feat(culture): #85 gold_culture_location_daily에 kcisa 편입 — 기존 type 합산

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

---

### Task 4: 전체 빌드 + PR + dev 복귀

**Files:** 신규 파일 없음 (검증·마감).

- [ ] **Step 1: culture 전체 빌드** — Run (컨테이너 헬퍼):

```
dbt build --no-partial-parse --target dev --no-use-colors
```

Expected: 전 모델·테스트 PASS (기존 모델 회귀 없음 확인).

- [ ] **Step 2: PR 생성** — 본문에 AC 실측(행수·교차중복 0·국립기관 예시·gold 델타) 포함:

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git push -u origin feat/85-culture-kcisa-silver-gold
gh pr create --repo ASAC-DE-bigkk/ASAC-DBT --base dev --head feat/85-culture-kcisa-silver-gold --title "feat(culture): #85 KCISA 서울 행사 silver/gold 편입 — 전량 + 3축 dedup" --body "<요약 + AC 실측표 + Closes #85 + 🤖 Generated with [Claude Code](https://claude.com/claude-code)>"
```

PR은 생성만 — 머지는 사용자 소관.

- [ ] **Step 3: dev 복귀** — Run:

```powershell
cd C:\Users\Dell3571\ask-seoul\sample\dbt
git checkout dev
```

(컨테이너가 이 워킹트리를 마운트하므로 브랜치 방치 금지.)

---

## Self-Review

- **Spec 커버리지**: sources.yml 등록(T1) / 컬럼 매핑·스냅샷 dedup·3축 anti-join·행정동(T2 Step 1) / 계약·grain unique·axis_coverage 실측 임계(T2 Step 3·6) / 교차중복 0 테스트(T2 Step 2) / 국립기관 실측(T2 Step 5) / gold 편입·프리픽스·델타(T3) / 전체 빌드·PR(T4) — 설계 전 항목 매핑.
- **타입 일관성**: `event_id(varchar)`·`service_name`·`event_start_date/event_end_date(date)` — T2 Produces와 T3 arm 사용 컬럼 일치. `culture_norm_title(expr)` 시그니처 T1↔T2 일치.
- **placeholder**: `min_ratio: 0.5`는 Step 6 교체 절차가 명시된 임시값(허용). PR body는 실측값 채움 지시 명시.

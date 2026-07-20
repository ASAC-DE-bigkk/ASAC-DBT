# Q&A metric 마트 1차 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설계 문서(2026-07-20-culture-qa-metric-marts.md)의 3작업 구현 — venue_profile 신규 + activity_by_dong additive 확장 + event_crowd v2(요일 축).

**Architecture:** 마트별 이슈+브랜치+PR, 순차(A→B→C). 각 태스크 = dbt 모델 + contract yml + singular test → 컨테이너(dev) 빌드 검증 → AC 실측 → PR. base는 모두 dev.

**Tech Stack:** dbt(Trino/Iceberg), 컨테이너 elt-infra-airflow-scheduler-1(마운트 = `ask-seoul/sample/dbt`).

## Global Constraints

- 수정 범위: `ASAC-DBT/domains/culture/` 만 (멘티 소유). common·타 도메인 금지.
- 커밋 마지막 줄: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- PR body 마지막 줄: `🤖 Generated with [Claude Code](https://claude.com/claude-code)` · base=dev · **셀프 머지 금지**(명시 지시 시만).
- GitHub 이슈는 org `.github/ISSUE_TEMPLATE` 템플릿([Task] 프리픽스) 구조.
- 컨테이너 검증 패턴: ASAC-DBT push → host에서 `sample/dbt`를 `git checkout --detach origin/<branch>` → 컨테이너 dbt build → **`git checkout dev` 복귀 필수**.
- dbt build 명령(컨테이너): `MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt build --select <models+tests> --project-dir . --profiles-dir . --target dev"`
- Trino 실측 쿼리(컨테이너 python): `MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 /home/airflow/dbt-venv/bin/python -c "..."` — catalog `iceberg_dev`, schema `culture`.
- API 키·시크릿 echo/출력 금지.

---

### Task A: `gold_culture_venue_profile` 신규

**Files:**
- Create: `domains/culture/models/gold/gold_culture_venue_profile.sql`
- Modify: `domains/culture/models/gold/_culture_gold__models.yml` (끝에 블록 추가)
- Test: `domains/culture/tests/assert_venue_profile_invariants.sql`

**Interfaces:**
- Consumes: `ref('silver_culture_facility')` (facility_id·facility_name·address·latitude·longitude·seat_scale·gu·gu_code·admin_dong·admin_dong_code·quality_status), `ref('silver_culture_performance')` (facility_id·genre·event_start_date·event_end_date)
- Produces: 테이블 `iceberg_dev.culture.gold_culture_venue_profile` (그레인 facility_id, 1,689행 기대)

- [ ] **Step A1: 이슈 발행 + 브랜치**

```bash
# 이슈 body를 scratchpad에 Write 후:
gh issue create --repo ASAC-DE-bigkk/ASAC-DBT \
  --title "[Task] gold_culture_venue_profile — 시설 프로필 Q&A metric 마트" \
  --body-file <scratchpad>/issue-venue-profile.md
# body 요지: 질문("그 공연장 어떤 곳이야")·그레인 facility_id·선실측(링크 99.9%, 주소 100%,
#   seat_scale 63.7%)·meta.external=false 첫 실사용·AC(1,689행, perf>0=421). 설계 문서 링크.
cd ASAC-DBT && git checkout dev && git pull --ff-only origin dev
git checkout -b feat/culture-venue-profile
```

- [ ] **Step A2: 모델 작성**

`models/gold/gold_culture_venue_profile.sql`:

```sql
-- gold(Q&A metric): 시설 1행 프로필 — "그 공연장 어떤 곳이야". facility dim(주소·좌표 100%,
-- seat_scale 63.7% 충전) + KOPIS 공연 집계(facility_id 링크 99.9%, 공연 보유 시설 421).
-- ⚠ 공연 통계는 KOPIS 공연 기준(전시·축제·행사 미포함). perf_count=0 시설도 위치·규모 프로필로 유효.
-- meta.external=false — 외부 카탈로그 비공개(Q&A 전용), 대시보드 external 플래그의 소스 오브 트루스(#269).

with fac as (
    select facility_id, facility_name, address, latitude, longitude, seat_scale,
           gu, gu_code, admin_dong, admin_dong_code, quality_status
    from {{ ref('silver_culture_facility') }}
),

perf as (
    select
        facility_id,
        count(*)              as perf_count,
        count(distinct genre) as distinct_genres,
        min(event_start_date) as first_perf_date,
        max(event_end_date)   as last_perf_date
    from {{ ref('silver_culture_performance') }}
    where facility_id is not null
    group by facility_id
),

genre_counts as (
    select facility_id, genre, count(*) as n
    from {{ ref('silver_culture_performance') }}
    where facility_id is not null and genre is not null
    group by facility_id, genre
),

top_genre as (
    select facility_id, max_by(genre, n) as top_genre, max(n) as top_genre_count
    from genre_counts
    group by facility_id
)

select
    f.facility_id,
    f.facility_name,
    f.address,
    f.latitude,
    f.longitude,
    f.seat_scale,
    f.gu,
    f.gu_code,
    f.admin_dong,
    f.admin_dong_code,
    cast(coalesce(p.perf_count, 0) as integer)      as perf_count,
    cast(coalesce(p.distinct_genres, 0) as integer) as distinct_genres,
    t.top_genre,
    cast(t.top_genre_count as integer)              as top_genre_count,
    p.first_perf_date,
    p.last_perf_date,
    f.quality_status
from fac f
left join perf p on p.facility_id = f.facility_id
left join top_genre t on t.facility_id = f.facility_id
```

- [ ] **Step A3: 계약 yml 블록 추가**

`_culture_gold__models.yml` 끝(마지막 모델 블록 뒤)에 추가:

```yaml
  - name: gold_culture_venue_profile
    description: 시설(facility_id) 1행 프로필 — "그 공연장 어떤 곳이야"(Q&A metric). 주소·좌표 100%, seat_scale 63.7% 충전. 공연 통계는 KOPIS 공연 기준(보유 시설 421) — 전시·축제 미포함. 외부 카탈로그 비공개(meta.external=false, #269).
    config:
      contract:
        enforced: true   # published gold 계약(#180)
      meta:
        external: false  # Q&A 전용 내부 마트 — 외부 카탈로그 노출 제외(#269, 대시보드 PR#6 메커니즘)
    columns:
      - name: facility_id
        description: KOPIS 시설 ID(mt10id) — PK
        data_type: varchar
        tests: [not_null, unique]
      - name: facility_name
        description: 시설명
        data_type: varchar
      - name: address
        description: 주소(충전 100%)
        data_type: varchar
        tests: [not_null]
      - name: latitude
        description: 위도(충전 100%)
        data_type: double
        tests: [not_null]
      - name: longitude
        description: 경도(충전 100%)
        data_type: double
        tests: [not_null]
      - name: seat_scale
        description: 좌석 규모(0/공백→null 정규화, 충전 63.7%)
        data_type: integer
      - name: gu
        description: 자치구 이름
        data_type: varchar
      - name: gu_code
        description: 자치구 코드(#48 공간축)
        data_type: varchar
      - name: admin_dong
        description: 행정동 이름
        data_type: varchar
      - name: admin_dong_code
        description: 행정동 코드(행안부 canonical)
        data_type: varchar
      - name: perf_count
        description: KOPIS 공연수(링크 없으면 0) — 전시·축제 미포함 캐비앳
        data_type: integer
        tests: [not_null]
      - name: distinct_genres
        description: 공연 장르 수
        data_type: integer
      - name: top_genre
        description: 최다 장르(max_by, 공연 없으면 null)
        data_type: varchar
      - name: top_genre_count
        description: 최다 장르 공연수
        data_type: integer
      - name: first_perf_date
        description: 첫 공연 시작일
        data_type: date
      - name: last_perf_date
        description: 마지막 공연 종료일
        data_type: date
      - name: quality_status
        description: facility dim quality_status 전파(#111)
        data_type: varchar
```

- [ ] **Step A4: 불변식 테스트 작성**

`tests/assert_venue_profile_invariants.sql`:

```sql
-- venue_profile 불변식: 그레인(facility_id) 유일 + perf_count>=0
--   + perf_count=0 → top_genre null(단방향 — genre null 공연 존재 가능해 역방향 미보장)
--   + first_perf_date <= last_perf_date.
with dupes as (
    select facility_id, count(*) as n
    from {{ ref('gold_culture_venue_profile') }}
    group by facility_id
    having count(*) > 1
),
bad as (
    select facility_id
    from {{ ref('gold_culture_venue_profile') }}
    where perf_count < 0
       or (perf_count = 0 and top_genre is not null)
       or (first_perf_date is not null and last_perf_date is not null
           and first_perf_date > last_perf_date)
)
select facility_id, 'dupe' as violation from dupes
union all
select facility_id, 'invariant' as violation from bad
```

- [ ] **Step A5: push + 컨테이너 빌드 검증**

```bash
cd ASAC-DBT && git add domains/culture && git commit -m "feat(culture): gold_culture_venue_profile 시설 프로필 Q&A metric 마트

...본문...

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push -u origin feat/culture-venue-profile
cd ../sample/dbt && git fetch origin && git checkout --detach origin/feat/culture-venue-profile
MSYS_NO_PATHCONV=1 docker exec elt-infra-airflow-scheduler-1 bash -c "cd /opt/airflow/dbt/domains/culture && /home/airflow/dbt-venv/bin/dbt build --select gold_culture_venue_profile assert_venue_profile_invariants --project-dir . --profiles-dir . --target dev"
```

Expected: model 1 + test 3종(not_null·unique·singular) 전부 PASS.

- [ ] **Step A6: AC 실측**

Trino로: `select count(*), count_if(perf_count>0), count(address), count(latitude) from gold_culture_venue_profile` → 1689 / 421 / 1689 / 1689 확인. 결과 기록.

- [ ] **Step A7: PR 생성 + 컨테이너 복귀**

```bash
cd sample/dbt && git checkout dev   # 복귀 필수
# PR body scratchpad Write 후: gh pr create --repo ASAC-DE-bigkk/ASAC-DBT --base dev \
#   --head feat/culture-venue-profile --title "..." --body-file ...
# body: 질문·그레인·선실측·AC 실측치·meta.external 첫 실사용 명시 + 🤖 푸터
```

---

### Task B: `gold_culture_activity_by_dong` additive 확장 (무료·교육/체험 카운트)

**Files:**
- Modify: `domains/culture/models/intermediate/int_culture_activity_days.sql` (union 6 arm에 is_free·category 컬럼 추가)
- Modify: `domains/culture/models/gold/gold_culture_activity_by_dong.sql` (agg 2컬럼)
- Modify: `domains/culture/models/gold/_culture_gold__models.yml` (activity_by_dong 블록에 컬럼 2개)
- Test: `domains/culture/tests/assert_activity_by_dong_free_counts.sql`

**Interfaces:**
- Consumes: `int_culture_activity_days`에 추가되는 `is_free varchar`·`category varchar` (event arm만 실값, 나머지 5 arm은 `cast(null as varchar)`)
- Produces: `gold_culture_activity_by_dong`에 `free_events_count bigint`·`edu_experience_events_count bigint` (그레인·기존 컬럼 불변)
- 주의: `gold_culture_location_daily`도 이 int를 소비하나 명시 컬럼 select라 additive 추가는 비파괴 — 빌드로 확인.

- [ ] **Step B1: 이슈 + 브랜치** — A와 동일 패턴. 제목 `[Task] activity_by_dong 무료·교육/체험 카운트 additive 확장`. body에 "free_access 흡수(티어링 #19 처분권고), 기술적 명명 원칙(family 해석은 Q&A 레이어 몫)" 명시. 브랜치 `feat/culture-dong-free-counts` (dev에서).

- [ ] **Step B2: int 확장** — `int_culture_activity_days.sql`의 6개 union arm 각각에 두 컬럼 추가 (quality_status 다음, event_start_date 앞 위치 통일):
  - performance·festival·exhibition·sejong·kcisa arm: `cast(null as varchar) as is_free, cast(null as varchar) as category,`
  - event arm: `is_free, category,` (silver_culture_event 실컬럼)
  - 최종 select에 `v.is_free, v.category,` 추가
  - 헤더 주석에 한 줄: `-- is_free·category(#B이슈): event arm만 실값 — activity_by_dong free/edu 카운트용, 타 arm null.`

- [ ] **Step B3: gold 집계 추가** — `gold_culture_activity_by_dong.sql`:
  - `expanded` CTE select에 `is_free, category` 추가
  - `agg` CTE에:
    ```sql
    count(distinct case when activity_type = 'event' and is_free = '무료' then activity_id end) as free_events_count,
    count(distinct case when activity_type = 'event' and category = '교육/체험' then activity_id end) as edu_experience_events_count
    ```
  - 최종 select에 `coalesce(a.free_events_count, 0) as free_events_count, coalesce(a.edu_experience_events_count, 0) as edu_experience_events_count`
  - 헤더 주석에 free_access 흡수 경위 1줄

- [ ] **Step B4: yml 컬럼 2개 추가** — activity_by_dong 블록 kcisa_count 다음:

```yaml
      - name: free_events_count
        description: 그날 그 동의 무료(is_free='무료') 서울시 문화행사 수 — event 소스만(타 소스 유무료 정보 없음). free_access(#19) 흡수
        data_type: bigint
      - name: edu_experience_events_count
        description: 그날 그 동의 교육/체험 카테고리 행사 수 — 기술적 카운트("가족적합" 해석은 Q&A 레이어 몫)
        data_type: bigint
```

- [ ] **Step B5: 테스트** — `tests/assert_activity_by_dong_free_counts.sql`:

```sql
-- free/edu 카운트 불변식: 부분집합이므로 events_count 이하 + 비음수.
select admin_dong_code, event_date
from {{ ref('gold_culture_activity_by_dong') }}
where free_events_count > events_count
   or edu_experience_events_count > events_count
   or free_events_count < 0
   or edu_experience_events_count < 0
```

- [ ] **Step B6: push + 컨테이너 빌드** — A5 패턴. select 대상: `gold_culture_activity_by_dong gold_culture_location_daily assert_activity_by_dong_free_counts` (location_daily는 int 공유 소비자 비파괴 확인용). Expected 전부 PASS.

- [ ] **Step B7: AC 실측 + PR + 복귀** — 그레인 행수 변화 없음(확장 전후 count(*) 동일), `sum(free_events_count) > 0`, `max(free_events_count <= events_count)` 위반 0. PR 생성(A7 패턴), sample/dbt dev 복귀.

---

### Task C: `gold_culture_event_crowd` v2 — 요일 축

**Files:**
- Modify: `domains/culture/models/gold/gold_culture_event_crowd.sql`
- Modify: `domains/culture/models/gold/_culture_gold__models.yml` (event_crowd 블록)
- Modify: `domains/culture/tests/assert_event_crowd_invariants.sql`

**Interfaces:**
- Produces: 그레인 `gu_code × day_of_week × hour_of_day`(~4,008행, v1 576행에서 세분화). `day_of_week integer` 컬럼 추가(Trino day_of_week(): 월1…일7). **파괴적 그레인 변경** — PR에 명시.

- [ ] **Step C1: 이슈 + 브랜치** — 제목 `[Task] event_crowd v2 — 요일 축 추가(그레인 변경)`. body에 선실측(4,008셀·p50 66·희소 0%)과 "외부 공개 직후라 그레인 변경 마지막 적기" 정당화. 브랜치 `feat/culture-event-crowd-dow` (dev에서).

- [ ] **Step C2: 모델 수정** — `gold_culture_event_crowd.sql`:
  - `crowd` CTE에 `day_of_week(event_at) as day_of_week,` 추가 (hour 위)
  - `lvl_counts`: select·group by에 `day_of_week` 추가
  - `typical`: group by `gu_code, day_of_week, hour_of_day`
  - `agg`: select·group by에 `day_of_week` 추가
  - 최종 select: `cast(a.day_of_week as integer) as day_of_week,` (gu 다음, hour 앞) + typical join 조건에 `and t.day_of_week = a.day_of_week`
  - 헤더 주석 갱신: 그레인 `gu_code × day_of_week × hour_of_day`, v2(#C이슈), "무슨 요일 몇 시가 한적한가", 셀당 p50 66샘플 실측

- [ ] **Step C3: yml 갱신** — description 그레인 문구 교체(`gu_code×hour_of_day` → `gu_code×day_of_week×hour_of_day, v2 #C이슈`), hour_of_day 앞에:

```yaml
      - name: day_of_week
        description: 요일(1=월 … 7=일, Trino day_of_week) — v2 추가 축. "무슨 요일 몇 시가 한적한가"
        data_type: integer
        tests: [not_null]
```

- [ ] **Step C4: 테스트 갱신** — `assert_event_crowd_invariants.sql`: dupes group by에 `day_of_week` 추가, bad에 `or day_of_week < 1 or day_of_week > 7` 추가, select 컬럼에 day_of_week 포함, 헤더 주석 그레인 갱신.

- [ ] **Step C5: push + 컨테이너 빌드** — select `gold_culture_event_crowd assert_event_crowd_invariants`. Expected PASS.

- [ ] **Step C6: AC 실측 + PR + 복귀** — `count(*)`≈4,008(gu 커버리지에 따라 ±), `count(distinct day_of_week)=7`, `min(crowd_samples)>=1`. PR body에 **그레인 변경(파괴적)** 섹션 + v1 대비 행수. sample/dbt dev 복귀.

---

### Task D: 마무리

- [ ] **Step D1**: 로드맵 #269에 Q&A 트랙 진행 코멘트(3 PR 링크 + free_access·venue_crowd_baseline이 흡수/축소로 해소됐음 명시).
- [ ] **Step D2**: 티어링 TSV 갱신 — #18 venue_profile 구축상태 완료, #19 free_access "activity_by_dong 흡수 완료", #21 venue_crowd_baseline "event_crowd v2로 흡수" 처분 반영.
- [ ] **Step D3**: 메모리 갱신(culture-gold-external-catalog 또는 신규 Q&A 트랙 메모리).

## Self-review 체크 결과

- 스펙 커버리지: 설계 A/B/C → Task A/B/C 1:1, 스코프 밖(qa_eval·weather_fit·대시보드) 어느 태스크에도 없음 ✓
- 플레이스홀더: 코드 블록 전부 실코드. 이슈/PR body는 요지 명시(발행 시점 작성) ✓
- 타입 일관성: venue_profile perf_count integer(모델 cast = yml data_type), free/edu counts bigint(count distinct 기본), day_of_week integer cast ✓
- location_daily 회귀: B6 빌드 select에 포함 ✓

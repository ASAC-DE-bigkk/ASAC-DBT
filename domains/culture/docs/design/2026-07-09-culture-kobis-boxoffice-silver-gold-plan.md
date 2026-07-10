# culture KOBIS 영화 박스오피스 silver/gold 구현 계획 (#86)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** KOBIS 일별 박스오피스 bronze(전국+서울 top10)를 silver `silver_culture_movie_boxoffice`(일×순위)와 gold `gold_culture_movie_boxoffice_daily`(서울 쏠림 관객 비중)로 편입한다.

**Architecture:** dbt(Trino/Iceberg) SQL 모델. bronze `record_json`을 union·파싱·타입화·dedup → silver, region별 집계 → gold. 검증은 컨테이너 안 dbt를 dev 타깃으로 `run`/`test`(pytest 아님).

**Tech Stack:** dbt-core 1.10 · dbt-trino · Iceberg(iceberg_dev.culture) · 매크로 `culture_lineage`/`culture_dedup_order`.

## Global Constraints

- **작업 트리**: `C:/Users/Dell3571/ask-seoul/sample/dbt` (컨테이너가 `/opt/airflow/dbt`로 마운트) 브랜치 `feat/86-culture-kobis-silver-gold`. 최상위 `ask-seoul/ASAC-DBT` 클론은 건드리지 않는다. **완료 후 sample/dbt를 `dev`로 복귀**.
- **모델 이름 정확히**: `silver_culture_movie_boxoffice`, `gold_culture_movie_boxoffice_daily`. 기존 `silver_culture_boxoffice`/`gold_culture_boxoffice_daily`(KOPIS 예매상황판)는 **절대 수정·삭제 금지**.
- **region 값 정확히**: `'nation'`(전국) / `'seoul'`(서울 한정 wideAreaCd=0105001).
- **매크로 사용(DRY)**: `{{ culture_lineage('kobis') }}` + `{{ culture_dedup_order() }}` — 다른 silver와 동일 패턴. 계보 컬럼은 `source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date`.
- **boxoffice_date**: `cast(load_date as date) - interval '1' day`.
- **materialized: table**(프로젝트 기본, 별도 config 불필요). culture 스키마 밖 미수정, 인프라 미변경.
- **dbt 실행 헬퍼**(컨테이너, dev 타깃) — 아래 모든 `run`/`test`/`show`에 사용:
  ```bash
  cd C:/Users/Dell3571/ask-seoul/sample
  docker compose exec -T airflow-scheduler bash -lc \
    'export DBT_PROFILES_DIR=/opt/airflow/dbt/domains/culture DBT_PROJECT_DIR=/opt/airflow/dbt/domains/culture; \
     /home/airflow/dbt-venv/bin/dbt <ARGS> --target dev --no-use-colors'
  ```
  파일은 sample/dbt에 저장하면 마운트로 컨테이너에 즉시 반영된다.
- **커밋 마지막 줄**: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- **PR body 마지막 줄**: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
- **PR 셀프 머지 금지** — PR 생성까지만, 머지는 사용자.

---

### Task 1: sources.yml — KOBIS bronze 2건 등록

**Files:**
- Modify: `domains/culture/models/sources.yml` (culture_bronze `tables:` 리스트 끝에 추가)

**Interfaces:**
- Produces: source 참조 `{{ source('culture_bronze', 'bronze_kobis_boxoffice_nation') }}` / `..._seoul` — Task 2가 소비.

- [ ] **Step 1: 소스 2건 추가**

`domains/culture/models/sources.yml`의 `bronze_kopis_boxoffice` 엔트리(기존 KOPIS 예매상황판) 바로 뒤, `tables:` 리스트에 아래를 추가한다:

```yaml
      - name: bronze_kobis_boxoffice_nation
        description: KOBIS 일별 박스오피스 — 전국 top10 스냅샷(영화 관객수). record_json=영화 1건. KOPIS 예매상황판(bronze_kopis_boxoffice)과 다른 축.
        columns:
          - name: record_json
            description: 원본 레코드(JSON) — rank·movieCd·movieNm·openDt·audiCnt·salesAmt·scrnCnt·showCnt 등
          - name: load_date
            description: 적재 파티션 일자(KST). 실제 관객일 targetDt = load_date − 1일
          - name: ingest_ts
            description: 적재 실행 식별 타임스탬프(UTC)
      - name: bronze_kobis_boxoffice_seoul
        description: KOBIS 일별 박스오피스 — 서울 한정(wideAreaCd=0105001) top10 스냅샷. 전국과 다른 영화 집합.
        columns:
          - name: record_json
            description: 원본 레코드(JSON) — 서울 상영지역 랭킹
          - name: load_date
            description: 적재 파티션 일자(KST). 실제 관객일 targetDt = load_date − 1일
          - name: ingest_ts
            description: 적재 실행 식별 타임스탬프(UTC)
```

- [ ] **Step 2: 소스가 dev에서 해석되는지 확인**

Run (헬퍼로):
```
dbt show --inline "select count(*) n from {{ source('culture_bronze','bronze_kobis_boxoffice_nation') }}" --target dev --limit 1 --no-use-colors
```
Expected: 에러 없이 `n` 컬럼과 행수(≥10) 출력. `Compilation Error`나 `TABLE_NOT_FOUND`면 실패.

- [ ] **Step 3: 커밋**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git add domains/culture/models/sources.yml
git commit -m "feat(culture): #86 KOBIS 박스오피스 bronze 소스 2건 등록

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: silver_culture_movie_boxoffice + 계약/테스트

**Files:**
- Create: `domains/culture/models/silver/silver_culture_movie_boxoffice.sql`
- Create: `domains/culture/tests/assert_movie_boxoffice_grain_unique.sql`
- Create: `domains/culture/tests/assert_movie_boxoffice_seoul_subset.sql`
- Modify: `domains/culture/models/schema.yml` (models 리스트 끝에 silver 엔트리 추가)

**Interfaces:**
- Consumes: `{{ source('culture_bronze','bronze_kobis_boxoffice_nation') }}` / `..._seoul` (Task 1), 매크로 `culture_lineage`/`culture_dedup_order`.
- Produces: `{{ ref('silver_culture_movie_boxoffice') }}` — 컬럼 `region, boxoffice_date, rank, movie_cd, movie_nm, open_date, audience_count, audience_acc, sales_amount, sales_share, screen_count, show_count, event_at, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date`. Task 3·테스트가 소비.

- [ ] **Step 1: grain unique 테스트 작성 (실패 예정)**

`domains/culture/tests/assert_movie_boxoffice_grain_unique.sql`:
```sql
-- 영화 박스오피스 그레인 (region, boxoffice_date, rank) 유일성 단언. 중복(>0행)이면 실패.
select region, boxoffice_date, rank, count(*) as n
from {{ ref('silver_culture_movie_boxoffice') }}
group by region, boxoffice_date, rank
having count(*) > 1
```

- [ ] **Step 2: 테스트가 실패(모델 부재)하는지 확인**

Run:
```
dbt test --select assert_movie_boxoffice_grain_unique --target dev --no-use-colors
```
Expected: `Compilation Error` — `model 'silver_culture_movie_boxoffice' ... depends on ... which was not found`. (모델이 아직 없어 ref 해석 실패 = 올바른 red 상태.)

- [ ] **Step 3: silver 모델 구현**

`domains/culture/models/silver/silver_culture_movie_boxoffice.sql`:
```sql
-- silver: KOBIS 일별 영화 박스오피스(전국+서울 한정) fact. top10 스냅샷.
-- 그레인 = (region, boxoffice_date, rank). boxoffice_date = load_date − 1일
-- (targetDt가 record_json에 없어 로더 계약[ASAC-DAG#197]에서 복원).
-- KOPIS 예매상황판 boxoffice(공연 예매)와 다른 축 = 영화 관객수. 공간축 시도(서울)까지라 면제.
-- region: 'nation'(전국) / 'seoul'(서울 한정 wideAreaCd=0105001). 두 랭킹은 서로 다른 영화 집합.

with unioned as (
    select 'nation' as region, record_json, ingest_ts,
           {{ culture_lineage('kobis') }}
    from {{ source('culture_bronze', 'bronze_kobis_boxoffice_nation') }}
    union all
    select 'seoul' as region, record_json, ingest_ts,
           {{ culture_lineage('kobis') }}
    from {{ source('culture_bronze', 'bronze_kobis_boxoffice_seoul') }}
),

typed as (
    select
        region,
        cast(json_extract_scalar(record_json, '$.rank') as integer)           as rank,
        json_extract_scalar(record_json, '$.movieCd')                         as movie_cd,
        nullif(trim(json_extract_scalar(record_json, '$.movieNm')), '')       as movie_nm,
        try(cast(json_extract_scalar(record_json, '$.openDt') as date))       as open_date,
        try(cast(json_extract_scalar(record_json, '$.audiCnt') as bigint))    as audience_count,
        try(cast(json_extract_scalar(record_json, '$.audiAcc') as bigint))    as audience_acc,
        try(cast(json_extract_scalar(record_json, '$.salesAmt') as bigint))   as sales_amount,
        try(cast(json_extract_scalar(record_json, '$.salesShare') as double)) as sales_share,
        try(cast(json_extract_scalar(record_json, '$.scrnCnt') as integer))   as screen_count,
        try(cast(json_extract_scalar(record_json, '$.showCnt') as integer))   as show_count,
        cast(load_date as date) - interval '1' day                            as boxoffice_date,
        ingest_ts, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
    from unioned
    where json_extract_scalar(record_json, '$.movieCd') is not null
),

latest as (
    select * from (
        select *, row_number() over (
            partition by region, boxoffice_date, rank
            order by {{ culture_dedup_order() }}
        ) as rn
        from typed
    ) where rn = 1
)

select
    region,
    boxoffice_date,
    rank,
    movie_cd,
    movie_nm,
    open_date,
    audience_count,
    audience_acc,
    sales_amount,
    sales_share,
    screen_count,
    show_count,
    cast(boxoffice_date as timestamp(6)) as event_at,
    source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
from latest
```

- [ ] **Step 4: silver 빌드 + grain 테스트 통과 확인**

Run:
```
dbt run  --select silver_culture_movie_boxoffice --target dev --no-use-colors
dbt test --select assert_movie_boxoffice_grain_unique --target dev --no-use-colors
```
Expected: run `PASS`(모델 생성), test `PASS`(중복 0). 그 후 표본 확인:
```
dbt show --inline "select region, boxoffice_date, rank, movie_nm, audience_count from {{ ref('silver_culture_movie_boxoffice') }} order by region, rank" --target dev --limit 20 --no-use-colors
```
Expected: nation/seoul 각 rank 1~10, boxoffice_date=load_date−1, audience_count 정수.

- [ ] **Step 5: subset 불변식 테스트 작성 + 통과 확인**

`domains/culture/tests/assert_movie_boxoffice_seoul_subset.sql`:
```sql
-- AC 불변식: 같은 관객일·영화(movie_cd)가 전국·서울 양쪽 top10에 있으면 서울 관객 ≤ 전국 관객(서울⊂전국).
-- 위반 행이 있으면 실패(>0행).
with nation as (
    select boxoffice_date, movie_cd, audience_count
    from {{ ref('silver_culture_movie_boxoffice') }} where region = 'nation'
),
seoul as (
    select boxoffice_date, movie_cd, audience_count
    from {{ ref('silver_culture_movie_boxoffice') }} where region = 'seoul'
)
select
    s.boxoffice_date, s.movie_cd,
    s.audience_count as seoul_audience, n.audience_count as nation_audience
from seoul s
join nation n on s.boxoffice_date = n.boxoffice_date and s.movie_cd = n.movie_cd
where s.audience_count > n.audience_count
```

Run:
```
dbt test --select assert_movie_boxoffice_seoul_subset --target dev --no-use-colors
```
Expected: `PASS`(위반 0행 — 서울은 전국의 부분집합).

- [ ] **Step 6: schema.yml에 silver 엔트리 추가**

`domains/culture/models/schema.yml`의 `models:` 리스트 맨 끝(현재 마지막은 `gold_culture_boxoffice_daily`)에 추가:
```yaml
  - name: silver_culture_movie_boxoffice
    description: KOBIS 일별 영화 박스오피스(전국+서울 한정). 그레인 region×boxoffice_date×rank, boxoffice_date=load_date-1. KOPIS 예매상황판 boxoffice와 별개 축.
    columns:
      - name: region
        description: 'nation'(전국) / 'seoul'(서울 한정 wideAreaCd=0105001)
        tests:
          - accepted_values:
              values: ["nation", "seoul"]
      - name: movie_cd
        description: KOBIS 영화 코드(movieCd)
        tests:
          - not_null
      - name: rank
        description: 그날 region top10 순위(1~10)
        tests:
          - not_null
      - name: boxoffice_date
        description: 실제 관객일(load_date − 1일)
```

- [ ] **Step 7: schema 테스트 통과 확인**

Run:
```
dbt test --select silver_culture_movie_boxoffice --target dev --no-use-colors
```
Expected: `accepted_values_...region`, `not_null_...movie_cd`, `not_null_...rank` 전부 `PASS`.

- [ ] **Step 8: 커밋**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git add domains/culture/models/silver/silver_culture_movie_boxoffice.sql \
        domains/culture/tests/assert_movie_boxoffice_grain_unique.sql \
        domains/culture/tests/assert_movie_boxoffice_seoul_subset.sql \
        domains/culture/models/schema.yml
git commit -m "feat(culture): #86 silver_culture_movie_boxoffice + grain·subset 계약

일×순위 그레인(region×boxoffice_date×rank), boxoffice_date=load_date-1 복원.
서울⊂전국 movieCd 불변식 테스트로 AC 실측.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: gold_culture_movie_boxoffice_daily + 계약

**Files:**
- Create: `domains/culture/models/gold/gold_culture_movie_boxoffice_daily.sql`
- Modify: `domains/culture/models/schema.yml` (models 리스트 끝에 gold 엔트리 추가)

**Interfaces:**
- Consumes: `{{ ref('silver_culture_movie_boxoffice') }}` (Task 2).
- Produces: `{{ ref('gold_culture_movie_boxoffice_daily') }}` — 컬럼 `boxoffice_date, nation_top_audience, seoul_top_audience, seoul_audience_share, nation_top_movie, seoul_top_movie`.

- [ ] **Step 1: gold 모델 구현**

`domains/culture/models/gold/gold_culture_movie_boxoffice_daily.sql`:
```sql
-- gold: 일별 서울/전국 영화 관객 비중 ("서울 쏠림"). 그레인 = boxoffice_date (날짜 1행).
-- 서울 top10 ≠ 전국 top10(서로 다른 영화 집합) → 비중 = top10 관객 합의 비율.
-- 공간 시도(서울시)까지라 자치구 gold 미편입 — 일 단위 서울 영화소비 축 전용.

with bo as (
    select region, boxoffice_date, rank, movie_nm, audience_count
    from {{ ref('silver_culture_movie_boxoffice') }}
),

agg as (
    select
        boxoffice_date,
        sum(case when region = 'nation' then audience_count end)        as nation_top_audience,
        sum(case when region = 'seoul'  then audience_count end)        as seoul_top_audience,
        max(case when region = 'nation' and rank = 1 then movie_nm end) as nation_top_movie,
        max(case when region = 'seoul'  and rank = 1 then movie_nm end) as seoul_top_movie
    from bo
    group by boxoffice_date
)

select
    boxoffice_date,
    nation_top_audience,
    seoul_top_audience,
    round(1.0 * seoul_top_audience / nullif(nation_top_audience, 0), 3) as seoul_audience_share,
    nation_top_movie,
    seoul_top_movie
from agg
```

- [ ] **Step 2: gold 빌드 + 표본 확인**

Run:
```
dbt run --select gold_culture_movie_boxoffice_daily --target dev --no-use-colors
dbt show --inline "select * from {{ ref('gold_culture_movie_boxoffice_daily') }} order by boxoffice_date" --target dev --limit 20 --no-use-colors
```
Expected: run `PASS`. 각 boxoffice_date 1행, `seoul_audience_share`가 0~1 사이 소수(예: 서울 관객합/전국 관객합), nation/seoul top_movie 영화명.

- [ ] **Step 3: schema.yml에 gold 엔트리 추가**

`domains/culture/models/schema.yml` 맨 끝(Task 2에서 추가한 silver 엔트리 뒤)에 추가:
```yaml
  - name: gold_culture_movie_boxoffice_daily
    description: 일별 서울/전국 영화 관객 비중(서울 쏠림). 그레인 boxoffice_date. 시도 그레인이라 자치구 gold 미편입.
    columns:
      - name: boxoffice_date
        description: 관객일(날짜 1행)
        tests:
          - not_null
          - unique
      - name: seoul_audience_share
        description: 서울 top10 관객합 / 전국 top10 관객합 (서울 쏠림 신호)
        tests:
          - not_null
```

- [ ] **Step 4: gold 계약 테스트 통과 확인**

Run:
```
dbt test --select gold_culture_movie_boxoffice_daily --target dev --no-use-colors
```
Expected: `not_null_...boxoffice_date`, `unique_...boxoffice_date`, `not_null_...seoul_audience_share` 전부 `PASS`.

- [ ] **Step 5: 커밋**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git add domains/culture/models/gold/gold_culture_movie_boxoffice_daily.sql \
        domains/culture/models/schema.yml
git commit -m "feat(culture): #86 gold_culture_movie_boxoffice_daily (서울 쏠림 관객 비중)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 전체 검증 + AC 실측 + PR

**Files:**
- (검증만 — 코드 변경 없음. PR 생성)

- [ ] **Step 1: movie_boxoffice 전 모델·테스트 일괄 빌드**

Run:
```
dbt build --select silver_culture_movie_boxoffice+ --target dev --no-use-colors
```
Expected: silver·gold 2 모델 + 계약/singular 테스트 전부 `PASS`, `ERROR`/`FAIL` 0. (`+`로 silver의 하류 gold까지 포함.)

- [ ] **Step 2: AC 실측 증거 수집**

Run:
```
dbt show --inline "select boxoffice_date, nation_top_audience, seoul_top_audience, seoul_audience_share, nation_top_movie, seoul_top_movie from {{ ref('gold_culture_movie_boxoffice_daily') }} order by boxoffice_date" --target dev --limit 30 --no-use-colors
```
확인: 모든 행에서 `seoul_audience_share ∈ (0,1)`, `seoul_top_audience < nation_top_audience`. subset 테스트(Task 2 Step 5)도 이미 통과 = "서울⊂전국" 실측 완료. 이 출력을 PR 본문에 인용.

- [ ] **Step 3: 회귀 안전 확인 — 기존 KOPIS boxoffice 무변경**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git diff --name-only dev...HEAD
```
Expected: 변경 파일이 신규 movie_boxoffice 3개 + schema.yml + sources.yml + 설계문서뿐. `silver_culture_boxoffice.sql`·`gold_culture_boxoffice_daily.sql`·`assert_boxoffice_grain_unique.sql`는 목록에 **없어야** 한다.

- [ ] **Step 4: 푸시 + PR 생성**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git push -u origin feat/86-culture-kobis-silver-gold
gh pr create --repo ASAC-DE-bigkk/ASAC-DBT --base dev --head feat/86-culture-kobis-silver-gold \
  --title "feat(culture): #86 KOBIS 영화 박스오피스 silver/gold (서울 쏠림)" \
  --body "$(cat <<'EOF'
## 요약
KOBIS 일별 박스오피스(전국+서울 top10) bronze를 silver/gold로 편입. Closes #86.

- `silver_culture_movie_boxoffice` — 일×순위(region×boxoffice_date×rank), boxoffice_date=load_date-1 복원, 측정값 캐스팅, culture_lineage/dedup_order 정합.
- `gold_culture_movie_boxoffice_daily` — 날짜 1행, `seoul_audience_share`(서울/전국 관객 비중) + rank1 영화명.
- 계약: grain unique + `assert_movie_boxoffice_seoul_subset`(서울⊂전국 불변식).

## 네이밍
기존 `*_boxoffice`(KOPIS 예매상황판)와 혼동 회피 위해 `movie_boxoffice` 사용. 기존 KOPIS 모델 무변경.

## dev 검증
- `dbt build --select silver_culture_movie_boxoffice+` 전 테스트 PASS.
- AC: gold 실측 `seoul_audience_share ∈ (0,1)`, subset 테스트로 서울⊂전국 확인.

## 완료 조건
- [x] dbt parse/compile 통과
- [x] dbt test 통과 (grain unique + subset)
- [x] culture 스키마 밖 미기재
- [x] 서울/전국 비중 파생 실측

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR URL 출력. **머지는 사용자.**

- [ ] **Step 5: sample/dbt를 dev로 복귀**

```bash
cd C:/Users/Dell3571/ask-seoul/sample/dbt
git checkout dev
```
Expected: 마운트 워킹트리가 dev로 복귀(컨테이너 정합).

---

## Self-Review

**Spec coverage**: silver(일×순위·region·캐스팅·boxoffice_date) = Task 2 · gold(서울/전국 비중) = Task 3 · schema.yml+grain unique = Task 2/3 · subset 불변식(AC) = Task 2 Step 5 · dev 실측 = Task 4. 설계 전 항목 커버.

**Placeholder scan**: 모든 SQL·YAML·명령 전문 기재. TBD 없음.

**Type consistency**: silver Produces 컬럼(region, boxoffice_date, rank, movie_cd, movie_nm, audience_count, …)을 Task 3 gold와 테스트가 동일 이름으로 소비. `region` 값 'nation'/'seoul' 일관. 매크로 방출 컬럼(source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date)은 `culture_lineage` 정의와 일치.

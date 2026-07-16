# 상태·기간 집계 쿼리 — 개업/폐업/상태별 × 연/월 × 업종 (silver 원형 + gold 집계)

silver 원형 정리본(entity/detail — 레이어 재분류 #70) + gold 집계 기반 **개업·폐업·상태별 기간 집계** 정본 쿼리 모음. 전 쿼리는 dev 실데이터로
**실행 검증**됐다(2026-07-15, entity 289만 행). D1(SQLite) 서빙 시 집계 관리 방안은 §7.

- 대상: `iceberg_dev.commerce.silver_license_entity`(현재 상태) + `silver_<domain>_detail`(API 별
  상이 컬럼) + `commerce_dataset_taxonomy`(업종 분류 시드) — 구조: dags `docs/PROJECT.md` §4.3
- 실행: Trino(DBeaver 등). prod 는 `iceberg_dev` → `iceberg`.

---

## 1. 실측 기반 계약 (쿼리가 전제하는 사실)

### 1.1 영업상태 코드(trdstategbn) — 코드 기준 정규화 필수

라벨(trdstatenm)은 v1/v2·dataset 별로 이질적(같은 `01`이 영업/정상/신규/재개업)이므로
**`substr(trim(trdstategbn),1,2)` 코드로 그룹핑**한다. 전수 census(2026-07-15):

| 코드 | 의미(대표) | 건수 | 상태 이벤트 일자 |
|---|---|---|---|
| `01` | 영업/정상 (신규·재개업 포함) | 957,293 | 개업 = `apvpermymd` (100%) |
| `02` | 휴업 | 3,698 | `clgstdt`(**detail**, 105 dataset 보유) — 공통 컬럼엔 없음(0.3%) |
| `03` | 폐업/폐쇄 | 1,560,844 | `dcbymd` (**98%** 보유) |
| `04` | 취소/말소/만료/정지/중지 | 186,791 | `apvcancelymd`(**detail**, 93 dataset) — dcbymd 는 13%뿐 |
| `05` | 제외/삭제/전출 | 184,525 | `dcbymd` (94% — 전출 시 폐업일 기록) |
| `06` | 기타 | 23 | 없음(무시 가능) |

`dtlstategbn`(상세상태)은 **dataset 별 코드체계가 달라**(01/1/0000/13/2…) 전역 정규화 불가 —
dataset 스코프 안에서만 (gbn, nm) 쌍으로 집계할 것.

### 1.2 날짜 형식·파싱 규약

- `apvpermymd`: 100% `YYYY-MM-DD`. `dcbymd`: `YYYY-MM-DD` 172.8만 + NULL/빈값 116.5만 + `YYYYMMDD` 3건
  (그중 `20090229` 같은 **무효 날짜 존재** — 원천 오류).
- **연/월 집계는 date 파싱 없이 문자열 `substr`** 를 쓴다(ISO 문자열은 사전순=날짜순):
  - Trino 482 는 `try()`+복합식에서 옵티마이저 버그(`Bind cannot be cast to Lambda`)가 있어
    date 캐스트 파싱이 불안정하고, substr 방식은 무효 날짜(2/29)도 연·월 추출은 안전하다.
- 공통 가드 식(이하 쿼리에서 `/*O*/`, `/*C*/` 로 표기):

```sql
-- 개업일 ISO (o_iso): 하이픈 형식 그대로, 8자리는 재조립, 그 외 NULL
case when regexp_like(trim(coalesce(apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(apvpermymd)
     when regexp_like(trim(coalesce(apvpermymd,'')), '^\d{8}$')
     then substr(trim(apvpermymd),1,4)||'-'||substr(trim(apvpermymd),5,2)||'-'||substr(trim(apvpermymd),7,2)
end
-- 폐업일 ISO (c_iso): dcbymd 에 동일 패턴
```

### 1.3 업종 축 (3단 + 업태)

- **대분류(major)/중분류(category)/소분류(dataset)**: `commerce_dataset_taxonomy` 시드 조인
  (`short = dataset`; 분류 정본: dags docs/PROJECT.md §1 — culture 56 · health 51 · industry 32 · environment 13).
- **업태(uptaenm)**: 19개 detail(56 dataset)이 payload 로 보유 — detail 조인으로 도출(§5).

### 1.4 현재(최신) 버전 detail 확보 — 정본 패턴 [실측 검증]

detail 은 **버전 이력**(grain = 자연키 × collected_at × content_hash)이다. 최신 버전만 얻는
정본은 **entity 조인**(entity 가 곧 "현재 버전" 앵커):

```sql
select e.trdstategbn, e.trdstatenm, d.*          -- 상태값(공통)은 entity, 상이 컬럼은 detail
from iceberg_dev.commerce.silver_license_entity e
join iceberg_dev.commerce.silver_<domain>_detail d
  on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
  and d.mgtno = e.mgtno and d.content_hash = e.content_hash;
```

- 검증(2026-07-15, food_sanitation 21 dataset): entity 1,121,462 = 조인 1,121,462 —
  **커버리지 100%·팬아웃 0**. (A→B→A 원복으로 같은 content_hash 가 2버전 존재해도 검증상
  팬아웃 0 — 안전벨트가 필요하면 조인에 `and d.collected_at = e.collected_at` 추가.)
- detail 단독 window(`row_number() over (partition by 자연키 order by collected_at desc)`)는
  **근사**다 — 버전 정렬의 정본은 updatedt 기반(silver)이고 detail 엔 collected_at 뿐이라
  동시수집·재수집 케이스에서 어긋날 수 있다. entity 조인을 기본으로 쓸 것.

---

## 2. 연 단위 개업·폐업 × 업종 [검증됨]

```sql
with e as (
  select t.major, t.category, e.dataset,
         case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.apvpermymd)
              when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{8}$')
              then substr(trim(e.apvpermymd),1,4)||'-'||substr(trim(e.apvpermymd),5,2)||'-'||substr(trim(e.apvpermymd),7,2)
         end o_iso,
         case when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.dcbymd)
              when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{8}$')
              then substr(trim(e.dcbymd),1,4)||'-'||substr(trim(e.dcbymd),5,2)||'-'||substr(trim(e.dcbymd),7,2)
         end c_iso
  from iceberg_dev.commerce.silver_license_entity e
  join iceberg_dev.commerce.commerce_dataset_taxonomy t on t.short = e.dataset
),
ev as (
  select 'opened' evt, substr(o_iso,1,4) y, major, category, dataset from e where o_iso is not null
  union all
  select 'closed', substr(c_iso,1,4), major, category, dataset from e where c_iso is not null
)
select y, major, category, dataset,                -- 그레인 조절: 대분류만이면 y, major 로 축소
       count_if(evt='opened') opened,
       count_if(evt='closed') closed
from ev
-- where y between '2015' and '2026'               -- 기간 필터(문자열 비교)
group by 1,2,3,4
order by 1 desc, 2,3,4;
```

검증 스팟(대분류 그레인): 2025 — industry 개업 53,099·폐업 32,251 / health 47,253·51,874 /
culture 7,628·5,356 / environment 797·879.

## 3. 월 단위 개업·폐업 × 업종 [검증됨]

§2 에서 `substr(x_iso,1,4)` → **`substr(x_iso,1,7)`**(=`YYYY-MM`)로 바꾸면 끝. 검증 스팟:
2025-01 개업 9,393·폐업 8,979 … 2025-06 개업 9,138·폐업 6,713.

## 4. 상태값별 기간 집계 [검증됨]

### 4.1 전 상태군 × 연도 (entity 공통 컬럼만 — 커버리지 포함)

상태군마다 이벤트 일자가 다르다(§1.1). 공통 컬럼으로 가능한 범위(01=개업일, 03/04/05=폐업일)의
정식 쿼리 — `with_event_date` 로 커버리지를 항상 병기해 해석 오류를 막는다:

```sql
with e as (
  select substr(trim(trdstategbn),1,2) st, t.major, t.category, e.dataset,
         case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.apvpermymd) end o_iso,
         case when regexp_like(trim(coalesce(e.dcbymd,'')),     '^\d{4}-\d{2}-\d{2}$') then trim(e.dcbymd)     end c_iso
  from iceberg_dev.commerce.silver_license_entity e
  join iceberg_dev.commerce.commerce_dataset_taxonomy t on t.short = e.dataset
),
ev as (select st, major, category, dataset,
              case st when '01' then o_iso else c_iso end ev_iso from e)
select substr(ev_iso,1,4) y,                       -- 월별이면 substr(ev_iso,1,7)
       st,
       case st when '01' then '영업(개업)' when '02' then '휴업' when '03' then '폐업'
               when '04' then '취소/말소' when '05' then '제외/전출' else '기타' end status_group,
       major, category, dataset,
       count(*) n
from ev
where ev_iso is not null
group by 1,2,3,4,5,6
order by 1 desc, 2;
```

> 한계(실측): `02 휴업`은 공통 일자 0.3%, `04 취소`는 13%만 — 이 두 군의 기간 집계는 4.2/4.3 의
> **detail 정밀 쿼리**를 쓴다. `03 폐업` 98%·`05 제외/전출` 94% 는 이 쿼리로 충분.

### 4.2 휴업 — detail `clgstdt`(휴업시작일) 기준 [검증됨]

`clgstdt` 는 54개 detail(105 dataset)이 보유. 보유 테이블 목록은 §6 쿼리로 도출. 예(유원시설):

```sql
select substr(trim(d.clgstdt),1,4) suspend_year,   -- 월별: substr(...,1,7)
       e.dataset, count(*) n
from iceberg_dev.commerce.silver_license_entity e
join iceberg_dev.commerce.silver_amusement_park_detail d
  on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
  and d.mgtno = e.mgtno and d.content_hash = e.content_hash        -- 현재 버전 매칭
where regexp_like(trim(coalesce(d.clgstdt,'')), '^\d{4}-\d{2}-\d{2}')
group by 1,2 order by 1 desc;
-- 상태 '02'(현재 휴업 중)만 보려면: and substr(trim(e.trdstategbn),1,2)='02'
-- (조건 없이면 '휴업 이력 있던 업소' 전체 — 재개업(ropnymd, 29 dataset)·휴업종료(clgenddt)도 동일 패턴)
```

### 4.3 취소/말소 — detail `apvcancelymd`(취소일) 기준 [검증됨]

```sql
select substr(trim(d.apvcancelymd),1,4) cancel_year, e.dataset, count(*) n
from iceberg_dev.commerce.silver_license_entity e
join iceberg_dev.commerce.silver_amusement_park_detail d
  on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
  and d.mgtno = e.mgtno and d.content_hash = e.content_hash
where substr(trim(e.trdstategbn),1,2) = '04'
  and regexp_like(trim(coalesce(d.apvcancelymd,'')), '^\d{4}')
group by 1,2 order by 1 desc;
```

### 4.4 상세상태(dtlstategbn) — dataset 스코프 집계

```sql
-- dataset 별 코드체계가 달라 전역 정규화 불가(§1.1) — 반드시 dataset 그레인으로.
select e.dataset, e.dtlstategbn, max(e.dtlstatenm) dtlstatenm,
       substr(c_iso,1,4) y, count(*) n
from ( select dataset, dtlstategbn, dtlstatenm,
              case when regexp_like(trim(coalesce(dcbymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(dcbymd) end c_iso
       from iceberg_dev.commerce.silver_license_entity ) e
where c_iso is not null
group by 1,2,4 order by 1, 5 desc;
```

## 5. 업태(uptaenm) 축 — "해당 업종이 무엇인지" [검증됨]

taxonomy(대/중/소분류)보다 세밀한 **업태 구분**은 detail 의 `uptaenm` 으로 도출한다
(19 detail·56 dataset 보유). 예(식품위생업 cluster — 21 dataset):

```sql
select t.major, t.category, e.dataset, d.uptaenm,
       substr(trim(e.apvpermymd),1,4) y, count(*) opened
from iceberg_dev.commerce.silver_license_entity e
join iceberg_dev.commerce.silver_food_sanitation_business_detail d
  on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
  and d.mgtno = e.mgtno and d.content_hash = e.content_hash
join iceberg_dev.commerce.commerce_dataset_taxonomy t on t.short = e.dataset
where d.uptaenm is not null
group by 1,2,3,4,5 order by 5 desc, 6 desc;
```

검증 스팟(2025 개업): 즉석판매제조가공업 9,260 · 기타 휴게음식점 2,799 · 한식 2,367 · 커피숍 1,909.

## 6. 보조 — 이벤트 일자·업태 보유 detail 찾기

어떤 detail 테이블이 `clgstdt`/`apvcancelymd`/`uptaenm`/`ropnymd` 를 갖는지는 카탈로그가 정본:

```sql
select object, members
from iceberg_dev.commerce.meta_detail_catalog
where payload_columns like '%clgstdt%'             -- 원하는 컬럼으로 교체
order by object;
```

## 7. 당해/당월/이번주/오늘 + D1(SQLite) 집계 관리 방안

### 7.1 현재 기간 쿼리 (Trino/Iceberg — 문자열 비교) [검증됨]

```sql
with e as (
  select case when regexp_like(trim(coalesce(apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(apvpermymd) end o,
         case when regexp_like(trim(coalesce(dcbymd,'')),     '^\d{4}-\d{2}-\d{2}$') then trim(dcbymd)     end c
  from iceberg_dev.commerce.silver_license_entity)
select '당해'  k, count_if(substr(o,1,4) = substr(cast(current_date as varchar),1,4)) opened,
                 count_if(substr(c,1,4) = substr(cast(current_date as varchar),1,4)) closed from e
union all
select '당월',  count_if(substr(o,1,7) = substr(cast(current_date as varchar),1,7)),
               count_if(substr(c,1,7) = substr(cast(current_date as varchar),1,7)) from e
union all
select '이번주', count_if(o between cast(date_trunc('week',current_date) as varchar) and cast(current_date as varchar)),
               count_if(c between cast(date_trunc('week',current_date) as varchar) and cast(current_date as varchar)) from e
union all
select '오늘',  count_if(o = cast(current_date as varchar)),
               count_if(c = cast(current_date as varchar)) from e;
```

> 원천이 **일 1회 배치**(04:00 KST 수집)이므로 '오늘/이번주' 값은 항상 **최신 수집분 기준**이다
> (실시간 아님 — 검증 시점 실측: 오늘 폐업 2 · 이번주 개업 6).

### 7.2 D1(SQLite) 관리 방안 제안 — 상대 기간은 저장하지 말 것

PROJECT.md §4.2(소형·전량 교체 스냅샷·읽기 최적화)와 정합하는 권장 구성:

**원칙: '당해/당월/이번주/오늘' 라벨을 미리 계산해 D1 에 굳히지 않는다.** 자정·주 경계를
넘는 순간 낡은 값이 되고, 갱신은 일 1회뿐이라 어긋난 라벨이 하루 종일 서빙된다. 대신
**불변 키(일/월) grain 팩트만 저장**하고 상대 기간은 조회 시 SQLite date 함수로 필터한다.

**D1 테이블 2개(+메타 1개) — 매일 전량 교체 스냅샷:**

```sql
-- ① 일 grain (최근 400일 롤링) — 오늘/이번주/당월/최근 N일 임의 합산용
create table agg_license_daily (
  dt        text not null,          -- 'YYYY-MM-DD' (이벤트 발생일)
  major     text not null, category text not null, dataset text not null,
  opened    integer not null default 0,
  closed    integer not null default 0,
  primary key (dt, dataset)
);
create index idx_daily_dt on agg_license_daily(dt);

-- ② 월 grain (전 기간) — 월/연 집계용 (+ 상태군 컬럼 확장: suspended/cancelled/excluded)
create table agg_license_monthly (
  ym        text not null,          -- 'YYYY-MM'
  major     text not null, category text not null, dataset text not null,
  opened    integer not null default 0,
  closed    integer not null default 0,
  cancelled integer not null default 0,   -- §4.3 detail 기준
  suspended integer not null default 0,   -- §4.2 detail 기준
  primary key (ym, dataset)
);

-- ③ 갱신 메타 1행 — 클라이언트가 "기준일"을 표시(일배치 특성 고지)
create table meta_refresh (loaded_at text not null, source_max_event_date text not null);
```

**적재(export) 방식**: gold(Iceberg)에서 §2~§4 쿼리로 재계산 → 새 SQLite 파일 생성 →
D1 원자 교체(또는 트랜잭션 내 `DELETE` 후 `INSERT`). **증분 upsert 금지** — 단일 writer
제약·과거 수정(원천 소급) 반영·멱등성 모두 스냅샷 재생성이 단순하고 안전하다.
크기 실측 근거: monthly ≈ 활성 연월(~600) × dataset(152) 희소 행 → 수십만 행 << D1 한도.

**조회 예(SQLite)** — 상대 기간을 조회 시점에 계산:

```sql
-- 오늘(KST):      select sum(opened), sum(closed) from agg_license_daily
--                 where dt = date('now','+9 hours');
-- 이번주(월요일~): where dt >= date('now','+9 hours','weekday 1','-7 days')
--                   and dt <= date('now','+9 hours');
-- 당월:           select * from agg_license_monthly where ym = strftime('%Y-%m', 'now','+9 hours');
-- 당해(업종별):    select major, sum(opened), sum(closed) from agg_license_monthly
--                 where ym like strftime('%Y', 'now','+9 hours') || '-%' group by major;
```

D1 은 UTC 기준이므로 KST 는 `'+9 hours'` 보정. `weekday 1`은 "다음 월요일"이므로 `-7 days`
와 조합해 이번 주 월요일을 얻는다(일요일 시작이면 `weekday 0`).

### 7.3 일일 리프레시 구문 세트 — DROP 후 재적재(준비 완료, 그대로 실행 가능)

하루 단위로 값이 바뀌므로(당해/당월/이번주/어제) **매일 SQLite 를 DROP 하고 새로 적재**하는
전제의 구문. 흐름: `[Trino 추출 E1·E2] → [SQLite R1 재적재] → [조회 Q]`.

#### E1. Trino 추출 — 일 grain (agg_license_daily 적재분, 최근 400일)

```sql
with e as (
  select t.major, t.category, e.dataset,
         case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.apvpermymd) end o_iso,
         case when regexp_like(trim(coalesce(e.dcbymd,'')),     '^\d{4}-\d{2}-\d{2}$') then trim(e.dcbymd)     end c_iso
  from iceberg_dev.commerce.silver_license_entity e
  join iceberg_dev.commerce.commerce_dataset_taxonomy t on t.short = e.dataset),
ev as (
  select o_iso dt, major, category, dataset, 1 o, 0 c from e where o_iso is not null
  union all
  select c_iso, major, category, dataset, 0, 1 from e where c_iso is not null)
select dt, major, category, dataset, sum(o) opened, sum(c) closed
from ev
where dt >= cast(date_add('day', -400, current_date) as varchar)   -- 롤링 400일
group by 1,2,3,4 order by 1,4;
```

#### E2. Trino 추출 — 월 grain (agg_license_monthly 적재분, 전 기간)

```sql
-- E1 의 ev 까지 동일, 마지막 select 만 교체:
select substr(dt,1,7) ym, major, category, dataset, sum(o) opened, sum(c) closed
from ev group by 1,2,3,4 order by 1,4;
-- (suspended/cancelled 확장 시 §4.2·§4.3 detail 쿼리 결과를 같은 (ym, dataset) 그레인으로 union)
```

#### R1. SQLite 재적재 — DROP 후 재생성(단일 트랜잭션, 실패 시 원상)

```sql
BEGIN;
DROP TABLE IF EXISTS agg_license_daily;
DROP TABLE IF EXISTS agg_license_monthly;
DROP TABLE IF EXISTS meta_refresh;

CREATE TABLE agg_license_daily (
  dt text not null, major text not null, category text not null, dataset text not null,
  opened integer not null default 0, closed integer not null default 0,
  primary key (dt, dataset));
CREATE INDEX idx_daily_dt ON agg_license_daily(dt);

CREATE TABLE agg_license_monthly (
  ym text not null, major text not null, category text not null, dataset text not null,
  opened integer not null default 0, closed integer not null default 0,
  primary key (ym, dataset));
CREATE INDEX idx_monthly_ym ON agg_license_monthly(ym);

CREATE TABLE meta_refresh (loaded_at text not null, source_max_event_date text not null);

-- E1/E2 결과를 그대로 multi-row INSERT (export 스크립트가 값 채움)
INSERT INTO agg_license_daily   (dt, major, category, dataset, opened, closed) VALUES /* E1 rows */;
INSERT INTO agg_license_monthly (ym, major, category, dataset, opened, closed) VALUES /* E2 rows */;
INSERT INTO meta_refresh VALUES (datetime('now'), /* E1 의 max(dt) */);
COMMIT;
```

> D1 배포 시엔 파일 통째 교체(`wrangler d1 import` / 신규 DB 스왑)가 위 트랜잭션과 등가 —
> 어느 쪽이든 **증분 upsert 없이 전량 재생성**(§7.2 원칙).

#### Q. 조회 — 어제/오늘/이번주/당월/당해 (KST 보정, 적재 후 그대로 사용)

```sql
-- 어제:    select major, sum(opened) opened, sum(closed) closed from agg_license_daily
--          where dt = date('now','+9 hours','-1 day') group by major;
-- 오늘:    where dt = date('now','+9 hours')            -- 일배치라 값은 최신 수집분 기준(§7.1)
-- 이번주:  where dt between date('now','+9 hours','weekday 1','-7 days') and date('now','+9 hours')
-- 당월:    select * from agg_license_monthly where ym = strftime('%Y-%m','now','+9 hours');
-- 당해:    select major, sum(opened), sum(closed) from agg_license_monthly
--          where ym like strftime('%Y','now','+9 hours')||'-%' group by major;
```

---

## 부록 — flow 모델 증분 계약(#73)

`gold_license_flow_daily/monthly/yearly` 는 **완결 기간(당일/당월/당해 제외) 중 기적재 최대
기간 초과분만 append**(incremental_strategy=append). **재실행 시 신규 완결 기간이 없으면
`INSERT 0 rows`** (append-only 멱등 — 실증: 재실행 2·3회차 모두 0건, 22 테이블 행수 불변).
지연 도착(과거 기간 소급 신고)은 이 경로로 안 잡히므로 **정기 `--full-refresh`**
(commerce_load_gold_refresh)로 스윕한다. ~~D1 export 도 동일하게 D1 max(기간키) 초과분만 append.~~
**(폐기 — 서빙 설계 확정)** D1 export 는 **전량 교체 스냅샷**이 정본이다(opus-serving-build-instructions.md §1.4):
full-refresh 소급 스윕이 과거 기간을 재작성하므로 append 로는 D1 에 반영 불가하고, 롤업 후 최대
~18만 행이라 전량 교체 비용이 무해하다.

## 변경 이력

- 2026-07-15: 최초 작성 — 전 쿼리 dev 실측 검증(상태 census·날짜 형식·커버리지 포함).
  Trino 482 `try()` 복합식 버그 회피(문자열 substr 규약) 명시. D1 관리 방안(§7.2) 제안.

- 2026-07-15: **레이어 재분류(#70) 반영** — 원형(entity/entity_history/detail)은 silver_ 명칭,
  카탈로그는 meta_detail_catalog, 집계(dong_summary)만 gold. 쿼리 내 테이블 명칭 전면 치환.

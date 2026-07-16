# Opus 구현 지시서 — gold 서빙 API·화면 (commerce)

> 대상: 이 문서만 읽고 백엔드 API 6묶음 + 프런트 화면 6종을 구현하는 에이전트(Opus).
> 원천: 서울 열린데이터 인허가(LOCALDATA) 상권 ELT, medallion raw→bronze(Iceberg)→silver→**gold(집계 전용, Iceberg)**→Serve=**D1(SQLite)**.
> 분류 3단: 대분류 `major`(health/culture/industry/environment) · 중분류 `category` · 소분류 `dataset`(=API 단위). 지역 3축: `gu_code`(25) · `admin_dong_code`(~426) · `legal_code`. `event_type`=opened|closed. 날짜=문자열 ISO(사전순=날짜순).

---

## 0. 목표·범위 / 산출물 / 비목표

### 0.1 목표
gold 22테이블을 재료로, 6개 화면(market-flow / survival / geo-place / biz-profile / succession / governance)을 서빙하는 **읽기 전용 API**와 **프런트 대시보드**를 구현한다. 핵심 설계 제약은 **서빙 데이터 소스 이원화**다: 소형 gold 는 **D1(SQLite)** 전량 교체 스냅샷으로, 대용량 gold(flow_daily 등)는 **Iceberg(Trino) 직조회** 또는 **화면 축으로 사전 롤업한 소형 파생 D1**으로 서빙한다.

### 0.2 산출물
1. **백엔드 API**: 6화면 × 엔드포인트 전수(§3). 소스가 D1인지 Iceberg인지 엔드포인트별로 고정.
2. **D1 export 파이프라인**: gold(Iceberg)→D1 테이블로 전량 교체 스냅샷 생성(§1.3, §2.1). 자연키/결정키, 타입 정규화, 롤업 축소.
3. **프런트 화면 6종**: 위젯·필터·드릴다운·경고 배지(씨앗/근사/커버리지)까지 포함(§4).
4. **공통 규약**: 필터 enum, 페이지네이션, 에러 포맷, 미완결/UNK/근사 라벨링 규칙(§3.1, §6).

### 0.3 비목표
- gold 모델(dbt) 자체의 재계산 로직 수정 — **불가**(gold SQL은 읽기 참조만).
- 쓰기/업서트 API — 서빙은 전량 읽기. D1은 파이프라인이 스냅샷 교체만.
- 실시간 스트리밍/웹소켓 — 모든 데이터는 일 단위 스냅샷(가장 최근 `latest_collected_at`).
- 개별 업소(원장 행) 조회 — gold 는 전부 집계 grain. 개별 업소 payload 서빙은 범위 밖.
- 좌표는 X/Y·grid_lat/grid_lng(파생 위경도)만. 별도 지오코딩 신규 수행 없음.

---

## 1. 아키텍처 결정(명시적)

### 1.1 서빙 데이터 소스 이원화

**원칙(PROJECT.md §4 준수):**
- D1 특성: DB당 실용 용량 ≪1GB · 단일 writer · 시퀀스 없음 · 엣지 읽기 최적 · 동적 타이핑.
- 따라서: (1) **소형 테이블만 D1 export**, 수백만 행 원장은 **D1 금지·Iceberg 전용**. (2) export=**전량 교체 스냅샷**(증분 upsert 아님). (3) **자연키/결정키**. (4) 조회형태로 **사전 집계·평탄화**(조인 최소화). (5) 타입 정규화(좌표 double, 코드 varchar, decimal→double).

**서빙 티어 판정표 (22테이블 전수):**

| gold 테이블 | 행수(실측) | 티어 | D1 대상/롤업 축 | Iceberg 폴백 |
|---|---:|---|---|---|
| gold_license_flow_daily | 2,918,695 | **iceberg_api** | — (원장 금지) | 임의기간+다축 직조회 |
| gold_license_flow_monthly | 1,338,656 | **d1_rollup** | (ym,event_type,major,category,gu_code)→181,430행 | dong/legal/dataset 세부 |
| gold_license_flow_yearly | 446,330 | **d1_rollup** | (y,event_type,major,category,gu_code)→21,558행 | dataset/dong 세부 |
| gold_license_seasonality | 2,912 | **d1_direct** | 원본 그대로 | — |
| gold_license_churn_yearly | 59,536 | **d1_rollup** | (y,major,category,gu_code)+비율 재산출 | dataset 세부 |
| gold_license_cohort_survival | 7,502 | **d1_direct** | 원본 그대로 | — |
| gold_license_lifespan | 2,867 | **d1_direct** | 원본 그대로 | — |
| gold_license_status_duration | 596 | **d1_direct** | 원본 그대로 | — |
| gold_license_status_transition | 108 | **d1_direct** | 원본 그대로 | — |
| gold_license_dong_summary | 417 | **d1_direct** | 원본 그대로 | — |
| gold_license_dong_category_matrix | 3,488 | **d1_direct** | 원본 그대로(UNK 보존) | — |
| gold_license_geo_grid | 16,353 | **d1_rollup** | overview=(grid×major), detail=(grid×major×category) | 원 grain 크로스탐색 |
| gold_license_gu_specialization | 283 | **d1_direct** | 원본 그대로 | — |
| gold_license_stock_age_band | 12,822 | **d1_rollup** | (major,category,gu_code,age_band) dataset 드롭 | dataset 정밀 |
| gold_detail_area_profile | 859 | **d1_direct** | 원본 그대로 | — |
| gold_detail_uptae_mix | 29,683 | **d1_rollup** | (dataset,uptaenm) gu 드롭 top-N | gu 드릴다운 전 grain |
| gold_license_multi_site | 140 | **d1_direct** | 원본 그대로 | — |
| gold_license_change_activity | 152 | **d1_direct** | 원본 그대로 | — |
| gold_license_address_succession | 99 | **d1_direct** | 원본 그대로 | — |
| gold_license_phone_succession | 91 | **d1_direct** | 원본 그대로 | — |
| gold_license_data_quality | 152 | **d1_direct** | 원본 그대로 | — |
| gold_env_facility_operation | 51 | **d1_direct** | 원본 그대로 | — |

**정책 주석:** geo_grid(16K)·stock_age_band(12K)·uptae_mix(29K)는 절대 크기로는 D1 상한 내이나, **원 grain에 dataset/좌표×업종 세분축이 포함**돼 정책상 "D1 원장 금지" 목록에 명시되어 있다 → **화면이 쓰는 축으로 롤업한 소형 파생만 D1**, 세부 드릴다운은 Iceberg 폴백. flow_monthly/yearly/churn 도 동일 논리(롤업 D1 + detail Iceberg).

### 1.2 스택 제안(엣지 친화)

**권장:** Cloudflare Workers(API 런타임) + **D1**(소형 스냅샷) + **Trino/Iceberg 백엔드**(대용량 직조회 프록시).

- **D1 경로**: Workers 가 D1 바인딩으로 직접 SQL. 저지연(엣지), 인덱스 없이도 풀스캔 무해(모든 D1 테이블 ≤~20만행, 대부분 수백~수천행).
- **Iceberg 경로**: `iceberg_api` / `*_rollup` 의 detail 은 Workers 가 자체 Trino 조회 불가 → **별도 백엔드 서비스(예: Node/FastAPI on Cloud Run/VM)**가 Trino REST 로 `iceberg_dev.commerce` 스키마 조회, Workers 가 이를 프록시. 조회 예: `docker exec elt-infra-trino-1 trino --output-format=TSV --execute "SQL"`(운영에선 Trino HTTP endpoint).
- **근거**: 지도 pan/zoom·시계열 조회는 엣지 저지연이 UX 핵심 → 소형은 D1. 임의기간·다축 대용량은 파티션 프루닝되는 Trino가 유일 해법.
- **대안**: (a) 전부 백엔드(Postgres) — 폐기 확정(PROJECT.md). (b) 전부 Trino — 소형 조회에도 왕복 지연·동시성 부담, 엣지 캐시 불가 → 반대. (c) D1 대신 KV/R2 정적 JSON — 정렬/필터 서버연산 불가 → 반대.
- **위험**: (1) Trino 백엔드 가용성 = 대용량 API SPOF → 응답 캐시(예: Cloudflare Cache API, TTL 1h) + `503 + retryable` 처리. (2) D1 스냅샷 교체 중 원자성 → §1.3. (3) gold 테이블이 정기 --full-refresh 로 **재빌드되는 짧은 구간** 동안 일시 조회 불가(Trino "Metadata not found") → API가 `503 building` 반환(§6), 재빌드 완료 후 자동 정상화.

### 1.3 D1 export 파이프라인

**흐름:** dbt gold(Iceberg) → Trino SELECT(롤업 포함) → 정규화(타입/코드) → **D1 신규 테이블 적재 → 원자적 스왑**.

- **전량 교체 스냅샷**: 증분 upsert 금지. 매 실행 `*_next` 테이블에 적재 후 `DROP old; ALTER RENAME` 혹은 `_meta` 버전 스위치. 재실행 멱등.
- **자연키/결정키(PK)**: §2.1 DDL 참조. 시퀀스 없음.
- **타입 정규화**: `decimal`(비율)→`REAL(double)`, 좌표→`REAL`, 모든 코드(`gu_code`/`status_code`/`dataset`)→`TEXT`. `boolean`→`INTEGER(0/1)`. `timestamp`→`TEXT`(ISO). NULL 유지(rate 분모 0, close_date_coverage 폐업0 등).
- **롤업 D1 파생 규칙**:
  - flow_monthly → `d1_flow_monthly`: `SELECT ym,event_type,major,category,gu_code,SUM(cnt) cnt GROUP BY 1..5`. (UNK gu_code 보존)
  - flow_yearly → `d1_flow_yearly`: 동일, `y` 축.
  - churn_yearly → `d1_churn_yearly`: `SUM(opened),SUM(closed),SUM(stock_start)` 집계 후 **비율 재산출** `churn_rate=closed/NULLIF(stock_start,0)`, `birth_rate=opened/NULLIF(stock_start,0)`, `net_change=opened-closed`. (비율은 합산 불가 → 반드시 재계산)
  - geo_grid → `d1_geo_grid_overview`(grid_lat,grid_lng,major 집계) + `d1_geo_grid_detail`(grid×major×category 원본).
  - stock_age_band → `d1_age_band`: `SUM(active_cnt) GROUP BY major,category,gu_code,age_band`(dataset 드롭).
  - uptae_mix → `d1_uptae_rollup`: `SUM(active_cnt),SUM(total_cnt),SUM(opened_last_365d) GROUP BY major,category,dataset,uptaenm`(gu 드롭), 저장 시 dataset별 top-N(예 상위 100) 프리컷 옵션 + `share` 사전계산 가능.
- **`_meta` 테이블**: `snapshot_at`(ISO), `source_table`, `row_count`, `build_status`(`ready|building|stale`). API가 `latest_collected_at`/데이터 기준일·미빌드 상태를 여기서 읽어 화면에 노출.

---

## 2. 데이터 계약

### 2.1 D1 테이블 DDL (소형/롤업 export 대상)

> SQLite 문법. 모든 코드 컬럼 `TEXT`, 비율/좌표 `REAL`, boolean `INTEGER`. 인덱스는 필터 상 열 위주(풀스캔도 무해하나 정렬 가속용).

```sql
-- ===== market-flow =====
CREATE TABLE d1_flow_monthly (        -- from gold_license_flow_monthly (롤업)
  ym TEXT, event_type TEXT, major TEXT, category TEXT, gu_code TEXT,
  cnt INTEGER,
  PRIMARY KEY (ym,event_type,major,category,gu_code));
CREATE INDEX ix_fm_major_gu ON d1_flow_monthly(major,gu_code,ym);

CREATE TABLE d1_flow_yearly (         -- from gold_license_flow_yearly (롤업)
  y TEXT, event_type TEXT, major TEXT, category TEXT, gu_code TEXT,
  cnt INTEGER,
  PRIMARY KEY (y,event_type,major,category,gu_code));

CREATE TABLE d1_seasonality (         -- from gold_license_seasonality (직송)
  event_type TEXT, month_of_year TEXT, major TEXT, category TEXT, dataset TEXT,
  cnt INTEGER,
  PRIMARY KEY (event_type,month_of_year,major,category,dataset));

CREATE TABLE d1_churn_yearly (        -- from gold_license_churn_yearly (롤업+비율재산출)
  y TEXT, major TEXT, category TEXT, gu_code TEXT,
  opened INTEGER, closed INTEGER, net_change INTEGER, stock_start INTEGER,
  churn_rate REAL, birth_rate REAL,
  PRIMARY KEY (y,major,category,gu_code));

-- ===== survival =====
CREATE TABLE d1_cohort_survival (     -- gold_license_cohort_survival (직송)
  major TEXT, category TEXT, cohort_y TEXT, years_elapsed INTEGER,
  cohort_n INTEGER, survivors INTEGER, survival_rate REAL,
  PRIMARY KEY (major,category,cohort_y,years_elapsed));
CREATE TABLE d1_lifespan (            -- gold_license_lifespan (직송)
  major TEXT, category TEXT, dataset TEXT, gu_code TEXT,
  n_closed INTEGER, avg_days REAL, p50_days INTEGER, p90_days INTEGER,
  closed_within_1y INTEGER, early_close_ratio REAL, survived_10y_then_closed INTEGER,
  PRIMARY KEY (major,category,dataset,gu_code));
CREATE TABLE d1_status_duration (     -- gold_license_status_duration (직송)
  dataset TEXT, major TEXT, category TEXT, status_code TEXT, status_group TEXT,
  is_ongoing INTEGER, n_segments INTEGER, avg_days REAL,
  p50_days INTEGER, p90_days INTEGER, max_days INTEGER,
  PRIMARY KEY (dataset,status_code,is_ongoing));
CREATE TABLE d1_status_transition (   -- gold_license_status_transition (직송)
  major TEXT, category TEXT, dataset TEXT,
  from_status TEXT, to_status TEXT, from_group TEXT, to_group TEXT, transitions INTEGER,
  PRIMARY KEY (dataset,from_status,to_status));

-- ===== geo-place =====
CREATE TABLE d1_dong_summary (        -- gold_license_dong_summary (직송)
  admin_dong_code TEXT PRIMARY KEY, admin_dong TEXT, gu_code TEXT, gu TEXT,
  business_count INTEGER, business_open_count INTEGER, business_closed_count INTEGER,
  dataset_count INTEGER, geocoded_count INTEGER, latest_collected_at TEXT);
CREATE INDEX ix_ds_gu ON d1_dong_summary(gu_code);
CREATE TABLE d1_dong_category_matrix ( -- gold_license_dong_category_matrix (직송, UNK 보존)
  admin_dong_code TEXT, admin_dong TEXT, gu_code TEXT, gu TEXT,
  major TEXT, category TEXT, active_cnt INTEGER, total_cnt INTEGER, opened_last_365d INTEGER,
  PRIMARY KEY (admin_dong_code,major,category));
CREATE INDEX ix_dcm_cat ON d1_dong_category_matrix(category,active_cnt);
CREATE TABLE d1_geo_grid_overview (   -- geo_grid 롤업(major)
  grid_lat REAL, grid_lng REAL, major TEXT,
  active_cnt INTEGER, opened_last_365d_active INTEGER,
  PRIMARY KEY (grid_lat,grid_lng,major));
CREATE TABLE d1_geo_grid_detail (     -- geo_grid (major,category)
  grid_lat REAL, grid_lng REAL, major TEXT, category TEXT,
  active_cnt INTEGER, opened_last_365d_active INTEGER,
  PRIMARY KEY (grid_lat,grid_lng,major,category));
CREATE INDEX ix_ggd_bbox ON d1_geo_grid_detail(grid_lat,grid_lng);
CREATE TABLE d1_gu_specialization (   -- gold_license_gu_specialization (직송)
  gu_code TEXT, gu TEXT, major TEXT, category TEXT,
  active_cnt INTEGER, share_in_gu REAL, lq REAL,
  PRIMARY KEY (gu_code,major,category));
CREATE TABLE d1_age_band (            -- stock_age_band 롤업(dataset 드롭)
  major TEXT, category TEXT, gu_code TEXT, age_band TEXT, active_cnt INTEGER,
  PRIMARY KEY (major,category,gu_code,age_band));

-- ===== biz-profile =====
CREATE TABLE d1_area_profile (        -- gold_detail_area_profile (직송)
  major TEXT, category TEXT, dataset TEXT, gu_code TEXT,
  n_with_area INTEGER, avg_m2 REAL, p50_m2 REAL, p90_m2 REAL,
  lt_33m2 INTEGER, ge_330m2 INTEGER,
  PRIMARY KEY (dataset,gu_code));
CREATE TABLE d1_uptae_rollup (        -- uptae_mix 롤업(gu 드롭)+share 사전계산
  major TEXT, category TEXT, dataset TEXT, uptaenm TEXT,
  active_cnt INTEGER, total_cnt INTEGER, opened_last_365d INTEGER, share REAL,
  PRIMARY KEY (dataset,uptaenm));
CREATE INDEX ix_up_dataset ON d1_uptae_rollup(dataset,active_cnt);
CREATE TABLE d1_multi_site (          -- gold_license_multi_site (직송)
  major TEXT, category TEXT, dataset TEXT PRIMARY KEY,
  sites_with_phone INTEGER, multi_site_locations INTEGER, multi_site_ratio REAL,
  multi_site_operators INTEGER, max_sites_per_operator INTEGER);
CREATE TABLE d1_change_activity (     -- gold_license_change_activity (직송)
  major TEXT, category TEXT, dataset TEXT PRIMARY KEY,
  businesses INTEGER, avg_versions REAL, max_versions INTEGER,
  with_rename INTEGER, rename_ratio REAL, with_relocation INTEGER, relocation_ratio REAL);

-- ===== succession =====
CREATE TABLE d1_address_succession (  -- gold_license_address_succession (직송)
  closed_major TEXT, closed_category TEXT, opened_major TEXT, opened_category TEXT,
  successions INTEGER, avg_gap_days REAL, p50_gap_days INTEGER, within_90d INTEGER,
  PRIMARY KEY (closed_major,closed_category,opened_major,opened_category));
CREATE TABLE d1_phone_succession (    -- gold_license_phone_succession (직송)
  closed_major TEXT, closed_category TEXT, opened_major TEXT, opened_category TEXT,
  successions INTEGER, avg_gap_days REAL, p50_gap_days INTEGER, within_1y INTEGER,
  PRIMARY KEY (closed_major,closed_category,opened_major,opened_category));

-- ===== governance =====
CREATE TABLE d1_data_quality (        -- gold_license_data_quality (직송)
  major TEXT, category TEXT, dataset TEXT PRIMARY KEY,
  total_rows INTEGER, active_rows INTEGER,
  phone_coverage REAL, geo_coverage REAL, admin_dong_coverage REAL,
  address_coverage REAL, close_date_coverage_of_closed REAL, name_coverage REAL);
CREATE TABLE d1_env_facility_operation ( -- gold_env_facility_operation (직송)
  dataset TEXT, gu_code TEXT, gu TEXT,
  facility_rows INTEGER, with_operating_days INTEGER,
  avg_operating_days_per_year REAL, p50_operating_days REAL,
  with_operating_hours INTEGER, avg_operating_hours REAL, p50_operating_hours REAL,
  PRIMARY KEY (dataset,gu_code));

-- 공통 메타
CREATE TABLE d1_meta (
  source_table TEXT PRIMARY KEY, snapshot_at TEXT, row_count INTEGER,
  build_status TEXT);  -- ready|building|stale
```

### 2.2 Iceberg(Trino) 직조회 대상 + 권장 조회 패턴

스키마: `iceberg_dev.commerce`. 접속: Trino HTTP(운영) / `docker exec elt-infra-trino-1 trino ...`(로컬).

| 용도 | 테이블 | 권장 필터/프루닝 |
|---|---|---|
| daily 기간 드릴다운 | `gold_license_flow_daily` | `event_date >= :from AND event_date <= :to`(문자열 비교=파티션 프루닝), + event_type/major/category/dataset/gu/dong/legal. **반드시 from/to 필수 강제**(무제한 스캔 금지). |
| monthly 세부 | `gold_license_flow_monthly` | `ym BETWEEN` + dataset/admin_dong/legal 세부축 |
| yearly 세부 | `gold_license_flow_yearly` | `y BETWEEN` + dataset/dong 세부 |
| churn 세부 | `gold_license_churn_yearly` | `y BETWEEN` + dataset |
| geo_grid 전 grain 크로스탐색 | `gold_license_geo_grid` | bbox(`grid_lat BETWEEN` 등) + category |
| stock_age_band dataset 정밀 | `gold_license_stock_age_band` | dataset 지정 시 |
| uptae_mix gu 드릴다운 | `gold_detail_uptae_mix` | dataset + gu_code 지정, uptaenm top-N |

**공통 규칙:** Iceberg 조회 엔드포인트는 (1) 범위 필터 필수(daily는 from/to, geo는 bbox), (2) `LIMIT` 상한 강제(기본 5,000·최대 50,000), (3) 응답 캐시 TTL 부여, (4) 반환은 D1 응답과 **동일 필드 스키마**로 정규화(프런트가 소스 무관하게 소비).

---

## 3. API 명세

### 3.1 공통 규약

- **Base**: `/api`. 전부 `GET`, 읽기 전용, JSON.
- **필터 enum**:
  - `major` ∈ `health|culture|industry|environment`
  - `event_type` ∈ `opened|closed`
  - `category` ∈ `food|livestock|health_medical|pharmacy|animal|hygiene_beauty|optical_dental|lodging|culture|industry|environment`(major=health 는 앞 8종, 그 외 major 는 동명 1종)
  - `status_code` ∈ `01`(영업)`|02`(휴업)`|03`(폐업)`|04`(취소/말소)`|05`(제외/전출)`|06`(기타)
  - `age_band` ∈ `0_lt1y|1_1to3y|2_3to5y|3_5to10y|4_10to20y|5_ge20y`
  - `gu_code` 25종 + `UNK`; `admin_dong_code` ~426; 지역 결측은 `UNK` 버킷.
- **기간 파라미터**: 전부 **문자열 ISO**. `from/to`=`YYYY-MM-DD`, `from_ym/to_ym`=`YYYY-MM`, `from_y/to_y`=`YYYY`. 범위 필터는 문자열 사전순 비교(사전순=날짜순).
- **페이지네이션**: `limit`(기본 100, 최대 1000), `offset`(기본 0). 응답에 `{ "meta": { "total", "limit", "offset", "source":"d1|iceberg", "snapshot_at", "build_status" } }` 포함.
- **정렬**: `sort`(허용 컬럼 화이트리스트), `order` ∈ `asc|desc`(기본 desc).
- **집계 규약**: `group_by` 지원 엔드포인트는 콤마 구분 컬럼(화이트리스트). 서버가 `SUM(cnt)` 등 사전 정의 집계만 수행.
- **응답 봉투**: `{ "data": [...], "meta": {...}, "notes": [ "approx"|"seed"|"coverage"|"incomplete_period"|"building" ... ] }`. 화면 경고 배지는 `notes`로 신호.
- **에러**: `400`(enum/range 위반, 필수 param 누락 — 예 daily from/to 없음), `404`(단건 코드 없음), `429`(rate), `503`(Iceberg 백엔드 불가 → `{ "error":"upstream_unavailable","retryable":true }`; 미빌드 테이블 → `{ "error":"building" }`), `500`.
- **미완결/UNK/근사 신호**: 완결기간 계약상 최신 미완결 구간(당일/당월/당해)은 애초 gold에 없음 → API는 해당 없음. UNK 행은 기본 포함하되 `include_unk` 옵션 있는 엔드포인트는 그 규칙 따름.

---

### 3.2 화면 1 — market-flow (5테이블)

#### `GET /api/market-flow/daily` — 소스: **Iceberg** (flow_daily)
- **query**: `from`(YYYY-MM-DD, **필수**), `to`(**필수**), `event_type`(enum, opt), `major`(enum, opt), `category`(enum, opt), `dataset`(opt), `gu_code`(opt), `admin_dong_code`(opt), `legal_code`(opt), `group_by`(콤마: `event_date,event_type,dataset,gu_code,major,category` 중; 기본 `event_date,event_type`), `limit`(기본 1000, 최대 50000).
- **response_fields**: `event_date,event_type,major,category,dataset,gu_code,admin_dong_code,legal_code,cnt`(group_by에 따라 축소).
- **예시**: `GET /api/market-flow/daily?from=2024-01-01&to=2024-03-31&major=health&category=food&gu_code=11680&group_by=event_date,event_type`
```json
{ "data":[
  {"event_date":"2024-01-02","event_type":"opened","cnt":7},
  {"event_date":"2024-01-02","event_type":"closed","cnt":3}],
  "meta":{"source":"iceberg","limit":1000,"offset":0},
  "notes":[]}
```
- **규약**: from/to 없으면 400. 파티션 프루닝 위해 range 필수. Top 위젯용 `group_by=gu_code,dataset` 지원.

#### `GET /api/market-flow/monthly` — 소스: **D1** (`d1_flow_monthly`)
- **query**: `from_ym`, `to_ym`, `event_type`, `major`, `category`, `gu_code`, `sort`(`ym|cnt`, 기본 ym asc).
- **response**: `ym,event_type,major,category,gu_code,cnt`.
- **예시**: `GET /api/market-flow/monthly?from_ym=2023-07&to_ym=2025-06&major=industry&event_type=opened`
- **파생**: `net=opened-closed`, 이동평균은 프런트 계산.

#### `GET /api/market-flow/monthly/detail` — 소스: **Iceberg** (flow_monthly 원본)
- **query**: `from_ym`(필수),`to_ym`(필수),`event_type`,`major`,`category`,`dataset`,`gu_code`,`admin_dong_code`,`legal_code`.
- **response**: `ym,event_type,dataset,gu_code,admin_dong_code,legal_code,cnt`.
- **예시**: `GET /api/market-flow/monthly/detail?from_ym=2024-01&to_ym=2024-12&dataset=food&admin_dong_code=1168064000`

#### `GET /api/market-flow/yearly` — 소스: **D1** (`d1_flow_yearly`)
- **query**: `from_y`,`to_y`,`event_type`,`major`,`category`,`gu_code`,`sort`(`y|cnt`).
- **response**: `y,event_type,major,category,gu_code,cnt`.
- **기본범위**: 미지정 시 최근 30년(예 1996~2025). 전체(1900~) 은 명시 요청 시. 1900 등 극단연도는 이상치.
- **예시**: `GET /api/market-flow/yearly?from_y=1995&to_y=2025&major=culture&event_type=closed`

#### `GET /api/market-flow/yearly/detail` — 소스: **Iceberg** (flow_yearly 원본)
- **query**: `from_y`(필수),`to_y`(필수),`event_type`,`major`,`category`,`dataset`,`gu_code`,`admin_dong_code`,`legal_code`.
- **response**: `y,event_type,dataset,gu_code,admin_dong_code,legal_code,cnt`.
- **예시**: `GET /api/market-flow/yearly/detail?from_y=2015&to_y=2025&dataset=general_restaurant&gu_code=11680`

#### `GET /api/market-flow/seasonality` — 소스: **D1** (`d1_seasonality`)
- **query**: `event_type`,`major`,`category`,`dataset`.
- **response**: `event_type,month_of_year,major,category,dataset,cnt`.
- **미빌드 처리**: `d1_meta.build_status='building'` 이면 `503 {"error":"building"}` + `notes:["building"]` → 위젯 '데이터 준비중'.
- **부제**: "최근 10년 완결연도 기준 근사 계절패턴".

#### `GET /api/market-flow/churn` — 소스: **D1** (`d1_churn_yearly`)
- **query**: `from_y`(2006~2025),`to_y`,`major`,`category`,`gu_code`,`metric`(`net_change|churn_rate|birth_rate`),`sort`.
- **response**: `y,major,category,gu_code,opened,closed,net_change,stock_start,churn_rate,birth_rate`.
- **notes**: 항상 `["approx"]`(stock_start 근사). `stock_start=0` → rate NULL.
- **예시**: `GET /api/market-flow/churn?from_y=2016&to_y=2025&major=industry&gu_code=11680&metric=churn_rate`

#### `GET /api/market-flow/churn/detail` — 소스: **Iceberg**
- **query**: `from_y`(필수),`to_y`(필수),`major`,`category`,`dataset`,`gu_code`. response 동일 + `dataset`.

---

### 3.3 화면 2 — survival (4테이블, 전부 D1)

#### `GET /api/survival/cohort-curve` — `d1_cohort_survival`
- **query**: `major`(필수),`category`(필수),`cohort_y`(단일 or 콤마 다중),`min_cohort_n`(기본 30).
- **response**: `major,category,cohort_y,years_elapsed,cohort_n,survivors,survival_rate`.
- **notes**: `["approx"]`(연 단위 근사·우측검열 보정). `cohort_n<min_cohort_n` 행은 `low_sample:true` 플래그.
- **예시**: `GET /api/survival/cohort-curve?major=health&category=food&cohort_y=2010,2015,2020`

#### `GET /api/survival/cohort-heat` — `d1_cohort_survival`
- **query**: `major`,`category`,`max_k`(기본 10). response: `cohort_y,years_elapsed,survival_rate,cohort_n`.

#### `GET /api/survival/lifespan` — `d1_lifespan`
- **query**: `major`,`category`,`dataset`,`gu_code`,`sort`(`p50_days|early_close_ratio|n_closed`),`order`,`min_n_closed`.
- **response**: `major,category,dataset,gu_code,n_closed,avg_days,p50_days,p90_days,closed_within_1y,early_close_ratio,survived_10y_then_closed`.
- **notes**: `["survivor_bias"]`('폐업 완결분 기준' — 실제 기대수명보다 짧게 편향).
- **예시**: `GET /api/survival/lifespan?major=health&category=food&sort=early_close_ratio&order=desc&min_n_closed=20`

#### `GET /api/survival/lifespan/by-gu` — `d1_lifespan`
- **query**: `dataset`(필수),`metric`(`p50_days|early_close_ratio`). response: `gu_code,p50_days,early_close_ratio,n_closed`.

#### `GET /api/survival/status-duration` — `d1_status_duration`
- **query**: `major`,`category`,`dataset`,`status_code`,`is_ongoing`(bool),`min_n_segments`.
- **response**: `dataset,major,category,status_code,status_group,is_ongoing,n_segments,avg_days,p50_days,p90_days,max_days`.
- **notes**: `["approx","seed"]`(approx_percentile·이력 축적중). `status_code=02` 관련 + `n_segments<30` → `low_sample:true`.
- **예시**: `GET /api/survival/status-duration?major=health&status_code=02`

#### `GET /api/survival/status-transition` — `d1_status_transition`
- **query**: `major`,`category`,`dataset`,`from_status`,`to_status`,`min_transitions`.
- **response**: `major,category,dataset,from_status,to_status,from_group,to_group,transitions`.
- **notes**: `["seed"]`. `transitions<30` → `low_sample:true`(회색 처리 신호).
- **예시**: `GET /api/survival/status-transition?major=health&category=food`

---

### 3.4 화면 3 — geo-place (5테이블)

#### `GET /api/geo/dong-summary` — `d1_dong_summary`
- **query**: `gu_code`,`sort`(`business_count|business_open_count|business_closed_count|dataset_count|geocoded_count`),`order`,`limit`,`offset`.
- **response**: `admin_dong_code,admin_dong,gu_code,gu,business_count,business_open_count,business_closed_count,dataset_count,geocoded_count,latest_collected_at`.
- **파생 노출**: 프런트가 `geocoded_count/business_count` = 지도 커버리지.
- **예시**: `GET /api/geo/dong-summary?gu_code=11680&sort=business_count&order=desc&limit=20`

#### `GET /api/geo/dong-summary/{admin_dong_code}` — 단건. 없으면 404.

#### `GET /api/geo/dong/{admin_dong_code}/categories` — `d1_dong_category_matrix`
- **query**: `major`,`sort`(`active_cnt|total_cnt|opened_last_365d`),`order`.
- **response**: `admin_dong_code,admin_dong,gu_code,gu,major,category,active_cnt,total_cnt,opened_last_365d`.

#### `GET /api/geo/dong-matrix` — `d1_dong_category_matrix`
- **query**: `gu_code`,`major`,`category`,`sort`(`active_cnt|opened_last_365d`),`order`,`include_unk`(기본 false),`limit`.
- **notes**: opened_last_365d 관련 위젯은 `["coverage:opened_date"]`(개업일 보유분 기준).

#### `GET /api/geo/heatmap` — `d1_geo_grid_detail`
- **query**: `major`,`category`,`bbox`(`minLat,minLng,maxLat,maxLng`),`metric`(`active_cnt|opened_last_365d_active`),`min_cnt`.
- **response**: `grid_lat,grid_lng,major,category,active_cnt,opened_last_365d_active`.
- **notes**: `["coverage:geocoded_84pct"]`(좌표 보유 약 84%만).
- **예시**: `GET /api/geo/heatmap?major=health&category=food&metric=active_cnt&bbox=37.49,126.98,37.58,127.10`
- **폴백**: 원 grain 크로스탐색 필요 시 `?source=iceberg` 로 `gold_license_geo_grid` 직조회.

#### `GET /api/geo/heatmap/overview` — `d1_geo_grid_overview`
- **query**: `major`,`metric`. response: `grid_lat,grid_lng,major,active_cnt,opened_last_365d_active`.

#### `GET /api/geo/gu/{gu_code}/specialization` — `d1_gu_specialization`
- **query**: `major`,`sort`(`lq|active_cnt|share_in_gu`),`order`,`min_lq`.
- **response**: `gu_code,gu,major,category,active_cnt,share_in_gu,lq`.
- **예시**: `GET /api/geo/gu/11680/specialization?sort=lq&order=desc&min_lq=1`

#### `GET /api/geo/specialization` — `d1_gu_specialization`
- **query**: `category`,`major`,`min_lq`,`sort`(`lq|active_cnt`),`order`. (업종별 구 간 비교/매트릭스)

#### `GET /api/geo/age-bands` — `d1_age_band`
- **query**: `gu_code`,`major`,`category`,`dataset`(지정 시 iceberg 폴백),`group_by`(`gu|category`).
- **response**: `major,category,gu_code,age_band,active_cnt`.
- **notes**: `["coverage:opened_date"]`.

#### `GET /api/geo/age-bands/profile` — `d1_age_band`
- **query**: `gu_code`,`major`,`category`. response: `age_band,active_cnt,share`(share=밴드/합계, 서버계산).

---

### 3.5 화면 4 — biz-profile (4테이블)

#### `GET /api/biz-profile/area` — `d1_area_profile`
- **query**: `major`,`category`,`dataset`,`gu_code`,`sort`(`avg_m2|p50_m2|n_with_area`),`order`.
- **response**: `major,category,dataset,gu_code,n_with_area,avg_m2,p50_m2,p90_m2,lt_33m2,ge_330m2`.
- **notes**: `["coverage:area_78pct"]`. `n_with_area` 낮으면 `low_sample:true`.
- **예시**: `GET /api/biz-profile/area?dataset=general_restaurant&sort=n_with_area&order=desc`

#### `GET /api/biz-profile/area/summary` — `d1_area_profile`
- **query**: `dataset`,`gu_code`. response: 위 - major/category. (미보유 dataset은 404 → '면적 데이터 없음').

#### `GET /api/biz-profile/uptae` — `d1_uptae_rollup`(gu 미지정) / **Iceberg**(gu 지정 시)
- **query**: `dataset`,`gu_code`(지정 시 iceberg 전 grain),`metric`(`active_cnt|opened_last_365d`),`top`(기본 20),`sort`,`order`.
- **response**: `major,category,dataset,uptaenm,gu_code,active_cnt,total_cnt,opened_last_365d`.
- **notes**: `["coverage:lodging_excluded"]`(lodging 스키마 드리프트 제외).

#### `GET /api/biz-profile/uptae/rollup` — `d1_uptae_rollup`
- **query**: `dataset`,`top`(기본 20),`metric`. response: `dataset,uptaenm,active_cnt,total_cnt,opened_last_365d,share`.
- **예시**: `GET /api/biz-profile/uptae/rollup?dataset=general_restaurant&top=15&metric=active_cnt`

#### `GET /api/biz-profile/multi-site` — `d1_multi_site`
- **query**: `major`,`category`,`dataset`,`sort`(`multi_site_ratio|multi_site_operators|max_sites_per_operator`),`order`.
- **response**: `major,category,dataset,sites_with_phone,multi_site_locations,multi_site_ratio,multi_site_operators,max_sites_per_operator`.
- **notes**: `["approx:phone_44pct"]`(전화 보유율 44%·번호공유≠법인동일).

#### `GET /api/biz-profile/change-activity` — `d1_change_activity`
- **query**: `major`,`category`,`dataset`,`sort`(`rename_ratio|relocation_ratio|avg_versions`),`order`.
- **response**: `major,category,dataset,businesses,avg_versions,max_versions,with_rename,rename_ratio,with_relocation,relocation_ratio`.
- **notes**: `["seed"]`(이력 축적 초기 씨앗, avg_versions≈1).

---

### 3.6 화면 5 — succession (2테이블, 전부 D1)

#### `GET /api/succession/address` — `d1_address_succession`
- **query**: `closed_major`,`closed_category`,`opened_major`,`opened_category`,`min_successions`,`sort`(`successions|avg_gap_days|p50_gap_days|within_90d`),`order`,`limit`.
- **response**: `closed_major,closed_category,opened_major,opened_category,successions,avg_gap_days,p50_gap_days,within_90d`.
- **notes**: `["approx:address_building_unit"]`.
- **예시**: `GET /api/succession/address?closed_category=food&min_successions=50&sort=successions&order=desc&limit=20`

#### `GET /api/succession/address/matrix` — 피벗
- **query**: `dim`(`major|category`),`min_successions`. response: `from,to,successions,p50_gap_days`.

#### `GET /api/succession/address/summary` — KPI 스칼라(서버 집계)
- **query**: `closed_major`,`closed_category`.
- **response**: `total_successions,diagonal_successions,diagonal_ratio,within_90d_total,within_90d_ratio,median_gap_overall`.
- **diagonal**: `closed_major==opened_major AND closed_category==opened_category` 합.

#### `GET /api/succession/phone` — `d1_phone_succession`
- **query**: 위와 동형, `within_1y` 사용. sort=`...|within_1y`.
- **response**: `...,successions,avg_gap_days,p50_gap_days,within_1y`.
- **notes**: `["approx:phone_44pct_reassign"]`.

#### `GET /api/succession/phone/matrix` — `dim`,`min_successions`. response: `from,to,successions,p50_gap_days`.

#### `GET /api/succession/phone/summary`
- **response**: `total_successions,diagonal_successions,diagonal_ratio,within_1y_total,within_1y_ratio,median_gap_overall,coverage_note`(고정 문구 '전화 약 44% 커버리지·근사').

> **금지**: address 와 phone 결과 합산/병합 금지(매칭축·window·컬럼 상이). 절대 승계건수를 '분모 없는 절대율'로 오독 금지 → 상대 비교·매트릭스로만.

---

### 3.7 화면 6 — governance (2테이블, 전부 D1)

#### `GET /api/governance/data-quality` — `d1_data_quality`
- **query**: `major`,`category`,`dataset`,`min_geo_coverage`,`max_geo_coverage`,`sort_by`(`phone_coverage|geo_coverage|admin_dong_coverage|address_coverage|close_date_coverage_of_closed|name_coverage|total_rows`),`order`,`limit`,`offset`.
- **response**: `major,category,dataset,total_rows,active_rows,phone_coverage,geo_coverage,admin_dong_coverage,address_coverage,close_date_coverage_of_closed,name_coverage`.
- **예시**: `GET /api/governance/data-quality?sort_by=geo_coverage&order=asc&limit=10` (좌표결측 최악 API)
```json
{"data":[
 {"dataset":"door_to_door_sale","geo_coverage":0.6156,"total_rows":...},
 {"dataset":"pharmacy","geo_coverage":0.6260,"...":"..."}],
 "meta":{"source":"d1"},"notes":[]}
```
- **주의**: `close_date_coverage_of_closed` 는 폐업행 0인 dataset에서 NULL → '해당없음'.

#### `GET /api/governance/data-quality/summary` — 서버 집계
- **query**: `group_by`(`major|category`). response: `major,category,dataset_count,avg_phone_coverage,avg_geo_coverage,avg_admin_dong_coverage,weakest_field`.

#### `GET /api/governance/env-facility-operation` — `d1_env_facility_operation`
- **query**: `dataset`(`air_pollution_facility|water_pollution_facility`),`gu_code`,`sort_by`(`facility_rows|avg_operating_days_per_year|avg_operating_hours|with_operating_days`),`order`.
- **response**: `dataset,gu_code,gu,facility_rows,with_operating_days,avg_operating_days_per_year,p50_operating_days,with_operating_hours,avg_operating_hours,p50_operating_hours`.
- **notes**: `["approx:percentile"]`. 수질은 `with_operating_days≈0`.
- **예시**: `GET /api/governance/env-facility-operation?dataset=air_pollution_facility&sort_by=avg_operating_days_per_year&order=desc` (예: 강서구 300.0일)

#### `GET /api/governance/env-facility-operation/coverage`
- **query**: `dataset`. response: `dataset,total_facility_rows,total_with_operating_days,days_coverage_ratio,hours_coverage_ratio`. (수질 days_coverage_ratio≈0 경고용)

---

## 4. 화면 명세 (6종)

> 공통 셸: 좌측 글로벌 필터 사이드바(major/category/dataset 3단, 지역 3축, 기간) + 상단 데이터 기준일(`latest_collected_at`/`snapshot_at`) + 우측 콘텐츠. 경고 배지 3종 표준화 — 🟠 **근사(approx)**, 🟡 **씨앗(seed, 이력 축적중)**, 🔵 **커버리지(coverage)**. `notes` 배열을 배지로 렌더. `low_sample:true` 행/셀은 회색 처리.

### 4.1 market-flow — 상권 흐름 대시보드

**레이아웃(와이어):**
```
[필터: major·category·dataset | gu·dong·legal | 해상도(연/월/일) 탭 | 기간]
[KPI: 개업합계 | 폐업합계 | 순증 델타 ]
[라인: 시계열 추이(선택 해상도)   ][ Bar: 월/연 순증(net) 발산 ]
[히트맵: 계절성 12개월×category ][ Matrix/사분면: churn 동태 ]
[테이블: 지역×업종 상위 개폐업]
```
**위젯:**
| 위젯 | 타입 | 바인딩 | 인터랙션·드릴다운 |
|---|---|---|---|
| 시계열 추이 | line | monthly(기본)/yearly/daily | opened/closed 2계열 토글, 이동평균(3/12M) 토글, **연→월→일 드릴다운**(같은 필터 좁혀 호출), 미완결 최신 구간 회색 |
| 개폐업 합계·순증 | kpi-card | daily/monthly 집계 sum(cnt) by event_type | 필터 반영, opened-closed 델타 |
| 월별 순증 | bar | monthly 파생 net | 발산색, 클릭 시 해당 월 daily 드릴다운 |
| 연도별 장기추세 | line | yearly | 기본 최근 30년, 전체(1900~) 토글 |
| 연도별 순증 스택 | bar | yearly opened(+)/closed(−) | 연 클릭→월 |
| 계절 히트맵 | heatmap | seasonality(month_of_year×category) | event_type 토글, **미빌드 시 스켈레톤+'데이터 준비중'**, 부제 '최근 10년 근사' |
| 월별 분포 | bar | seasonality | '최근 10년 근사' 배지 |
| 순증 bar | bar | churn net_change | 발산색 |
| 교체율 vs 신생비 | line | churn churn_rate/birth_rate | 🟠 '근사 스톡' 배지, stock_start=0 NULL 표시 |
| 동태 사분면 | matrix | churn(최근연) birth_rate(x)/churn_rate(y)/버블=stock_start | 성장·교체·정체·쇠퇴 사분면 라벨 |
| 지역/업종 상위 | table | daily group_by=gu_code,dataset | 정렬, 행클릭 필터 드릴다운 |

**경고/상태**: 미완결 구간 회색; UNK 지역 지도/필터 별도 처리(합계 각주); seasonality/churn window 상이(10년 vs 20년) 나란히 비교 시 기준연도 각주; churn `["approx"]` 배지 상시; 극단연도(1900) 기본 접힘.

**정합 체크(화면)**: 동일 필터에서 `yearly cnt = Σ monthly = Σ daily` 이어야 함(드릴다운 검증).

### 4.2 survival — 업종 생존·수명·상태

**레이아웃:**
```
[필터: major·category·dataset·cohort_y·gu]
[KPI: 5년 생존율 | 10년 생존율 | 휴업 평균지속·진행중 건수]
[생존곡선(코호트 오버레이)     ][ 코호트×경과 히트맵 ]
[수명 랭킹 테이블(업종×구)     ][ 자치구 조기폐업률 지도 ]
[상태 지속 bar(p50/p90)][ 상태전이 매트릭스 ][ 휴업 이후 경로 bar ]
```
**위젯:**
| 위젯 | 타입 | 바인딩 | 인터랙션 |
|---|---|---|---|
| 코호트 생존곡선 | survival-curve | cohort-curve years_elapsed(x)/survival_rate(y)/cohort_y(series) | 코호트 다중선택 오버레이, hover cohort_n·survivors, 🟠 '연단위 근사·우측검열 보정' |
| 생존율 히트맵 | heatmap | cohort-heat | cohort_n<임계 회색 |
| 5/10년 생존율 | kpi-card | cohort-curve(k=5,10) | 전체평균 대비 편차색 |
| 수명 랭킹 | table | lifespan | early_close_ratio 히트, min_n_closed 슬라이더, 🟠 '폐업 완결분 기준(생존편향)' |
| 조기폐업률 지도 | heatmap-map | lifespan/by-gu | dataset 선택, 구 클릭 |
| 수명 분포 요약 | bar | lifespan p50/p90/avg | 10년+생존후폐업 오버레이 |
| 상태 지속기간 | bar | status-duration status_group×p50/p90 | 완결 vs 진행중 분리, 🟠 approx_percentile |
| 휴업 지속·진행중 | kpi-card | status-duration(02) | 🟡 '이력 축적중·표본부족(휴업 0.24%)', n_segments<30 회색 |
| 상태 전이 매트릭스 | matrix | status-transition from_group×to_group×transitions | transitions<30 회색, 🟡 씨앗 배지, dataset 드릴다운 |
| 휴업 이후 경로 | bar | status-transition(02→01 vs 02→03) | 재개 vs 폐업 비율 |

**주의(화면)**: cohort_survival=편향 없는 정본, lifespan=폐업분만(짧게 편향), status_duration=상태별 — **숫자 직접 등치 금지**. 상태코드 01~06 정규화(dtl 세부와 다름) 툴팁.

### 4.3 geo-place — 지역 프로파일·지도

**레이아웃:**
```
[필터: gu·dong·major·category | 지도 뷰포트]
[동네 개요 KPI 4종][ 지도 커버리지 배지 ]
[코로플레스(동 밀도) | 밀도 히트맵(격자) | 신규 핫스팟 토글]
[동네 업종 구성 bar][ 최근1년 신규개업 테이블 ]
[구 특화 LQ bar][ 구×업종 LQ 매트릭스 ][ 업력밴드 구성 ]
```
**위젯:**
| 위젯 | 타입 | 바인딩 | 인터랙션 |
|---|---|---|---|
| 동네 개요 | kpi-card | dong-summary/{code} business_count/open/closed/dataset_count | 폐업률 보조표기(**business_count=누적, active와 혼용 금지**) |
| 지도 커버리지 | kpi-card | dong-summary geocoded/business | <70% 경고색, '히트맵은 좌표 보유만' |
| 동 코로플레스 | heatmap-map | dong-summary business_open_count(경계 GeoJSON 정적) | 호버, 클릭 동 선택 |
| 상권 밀도 히트맵 | heatmap-map | geo/heatmap active_cnt | bbox 재조회(pan/zoom), 🔵 '좌표 84%만' |
| 신규 핫스팟 | heatmap-map | geo/heatmap metric=opened_last_365d_active | metric 토글, 🔵 '개업일 보유분' |
| 밀집 격자 Top-N | table | geo/heatmap | 클릭 시 지도 센터링 |
| 동네 업종 구성 | bar | dong/{code}/categories active_cnt | 클릭→히트맵/랭킹 필터 |
| 신규 개업 업종 | table | dong/{code}/categories opened_last_365d | 🔵 '개업일 보유분', 유입강도 배지 |
| 동×업종 히트 매트릭스 | matrix | dong-matrix?gu_code= | 열클릭→category 지도 |
| 업종별 많은 동 랭킹 | table | dong-matrix?category= | active/opened 토글 |
| 구 특화 LQ | bar | gu/{code}/specialization lq | LQ=1 기준선, >1 특화색 |
| 업종 특화 코로플레스 | heatmap-map | specialization?category= lq | 발산형(1 중심), LQ 범례 |
| 구×업종 LQ 매트릭스 | matrix | specialization | lq 발산색 |
| 업력밴드 구성 | bar | age-bands/profile age_band(고정순서)/share | 신생·노포 색구분, 🔵 '개업일 보유분' |
| 구×업력 매트릭스 | matrix | age-bands?group_by=gu | 신생/노포 구 스캔 |
| 상권 성숙도 | kpi-card | age-bands/profile | 신생비중·노포비중 |

**주의(화면)**: **'현재 영업(active_cnt)' vs '누적(business_count)' 절대 혼용 금지**. UNK 행은 지도/리스트 숨김+합계 각주. `latest_collected_at`=데이터 기준일 하단.

### 4.4 biz-profile — 업소 특성·규모·업태

**dataset 선택 하나로 4패널 동시 갱신.**
```
[필터: major·category·dataset·gu]
[표준 점포규모 KPI][ 체인화 KPI ][ 정보변경 KPI ]
[구별 p50 면적 bar][ 소형/대형 구성 bar ]
[업태 구성 top-N bar][ 최근1년 성장 업태 bar ]
[업종별 다지점 랭킹 bar][ 변경활동 랭킹 bar ]
[면적/업태/체인/변경 상세 테이블 4종]
```
**위젯:**
| 위젯 | 타입 | 바인딩 | 인터랙션 |
|---|---|---|---|
| 표준 점포규모 | kpi-card | area/summary avg/p50/p90/n_with_area | n_with_area 낮으면 '표본 적음', 🔵 '면적 78%' |
| 구별 중앙면적 | bar | area p50_m2 by gu | 막대클릭 드릴다운 |
| 소형/대형 구성 | bar | area lt_33m2/ge_330m2 | 스택/비율 토글 |
| 면적 상세표 | table | area 전필드 | 🔵 '면적 커버리지 78%' 고정 |
| 업태 구성 top-N | bar | uptae/rollup uptaenm/active_cnt/share | top-N 슬라이더, 막대클릭→gu 드릴(iceberg) |
| 성장 주도 업태 | bar | uptae/rollup metric=opened_last_365d | 스톡 대비 신규비중 툴팁 |
| 업태 믹스 상세 | table | uptae(gu 지정=iceberg) | top-N 페이징+검색, 🔵 'lodging 제외' |
| 체인화 지표 | kpi-card | multi-site ratio/operators/max | 🟠 '전화 44%·번호공유≠법인동일' 상시 |
| 다지점 비율 랭킹 | bar | multi-site multi_site_ratio | sites_with_phone 툴팁 |
| 정보변경 활발도 | kpi-card | change-activity avg_versions/rename/relocation | 🟡 '씨앗지표 avg≈1' 상시 |
| 개명·이전 랭킹 | bar | change-activity rename/relocation | 로그/확대 스케일 옵션 |
| 변경활동 상세 | table | change-activity 전필드 | '상대순위로 해석' 각주 |

### 4.5 succession — 자리 승계·연쇄창업

```
[상단 근사 경고 배너(상시)]
[탭: 자리승계(주소) | 연쇄창업(전화)]
[KPI: 총 승계 | 자기업종 재입점률 | 90일(또는 1년)내 승계율]
[전이 매트릭스 히트맵(from→to)][ 코드/생키 다이어그램 ]
[승계속도 bar(p50 gap & within_*)][ 조합 상세 테이블 ]
```
**위젯(주소/전화 대칭):**
| 위젯 | 타입 | 바인딩 | 인터랙션 |
|---|---|---|---|
| KPI 3종 | kpi-card | address|phone /summary | 🟠 근사 툴팁(주소=건물단위 / 전화=44%·재배정) |
| 전이 매트릭스 | heatmap-matrix | */matrix?dim=category from/to/successions | 로그색, **대각선 강조 테두리**, 셀클릭 드릴, p50_gap 툴팁, dim 토글 |
| 흐름도 | chord(주소)/sankey(전화) | */matrix?dim=major | 자기순환 아크 별색, 근사 워터마크 |
| 승계속도 | bar | */ p50_gap_days & within_*/successions | 간격 오름차순 '빨리 채워지는 조합' |
| 조합 상세 | table | address|phone 8필드 | 정렬, min_successions 슬라이더, 근사 배너 고정 |

**주의(화면)**: 두 탭 데이터 **합산/병합 금지**. 절대건수를 절대율로 오독 금지 → 매트릭스·상대비교만. 히스토그램 대신 요약통계(avg/p50/within_*)만(원장 없음).

### 4.6 governance — 데이터 품질·환경 특수축

```
[상단 고지: '일반 업종 영업시간 필드 원천 부재(payload 0건)']
[탭: 데이터 품질 | 환경 가동축]
[KPI: 대분류별 평균 커버리지 4카드]
[API별 품질 프로파일 테이블][ 커버리지 히트맵(API×필드) ]
[폐업일 보유율 bar]
--- 환경 ---
[원천 커버리지 경고 배너(수질 가동일수≈0)]
[자치구 가동일수 지도][ 업종별 평균 가동시간 bar ][ 배출시설 실측 테이블 ]
```
**위젯:**
| 위젯 | 타입 | 바인딩 | 인터랙션 |
|---|---|---|---|
| API 품질 프로파일 | table | data-quality 전필드 | 정렬(sort_by), 셀 색상(<0.7 적색), 행클릭 드릴 |
| 커버리지 히트맵 | heatmap | data-quality 6개 coverage | hover(비율·total_rows), <0.7 하이라이트 |
| 대분류 평균 커버리지 | kpi-card | data-quality/summary?group_by=major | 카드클릭→테이블 필터 |
| 폐업일 보유율 | bar | close_date_coverage_of_closed | 낮은순, lifespan/cohort 신뢰도 경고 연동, 폐업0=NULL '해당없음' |
| 자치구 가동 실측 | table | env-facility-operation | 대기/수질 토글, 커버리지 비율 배지 |
| 자치구 가동일수 지도 | heatmap-map | env avg_operating_days_per_year | 커버리지 낮은 구 빗금/회색 |
| 원천 커버리지 경고 | kpi-card | env/coverage | 🔵 '수질=가동필드 원천결측, 실측 불가' 고정 |
| 평균 가동시간 | bar | env avg/p50_operating_hours | 🟠 'p50 근사' 병기 |

**연동**: data-quality의 close_date/geo/phone coverage 는 다른 화면(survival·geo·succession) 신뢰도 배지의 씨앗 → 프런트 공용 store 로 배지 연동.

### 4.7 반응형·접근성(전 화면 공통)
- 반응형: 상대 단위·flex/grid, 넓은 테이블/매트릭스/차트는 `overflow-x:auto` 컨테이너 내 스크롤(바디 가로스크롤 금지). 지도는 모바일에서 리스트 폴백.
- 접근성: 색만으로 신호 금지(발산·LQ·경고는 아이콘/패턴 병행), 히트맵 셀 aria-label(값), 키보드 포커스, 명도 대비 준수. 색맹 대비 발산 팔레트.
- 상태: 로딩=스켈레톤, 빈값='데이터 없음', 미빌드='데이터 준비중', low_sample=회색+'표본 부족'.

---

## 5. 구현 순서(마일스톤) + 수용 기준

**M0 — 기반**: D1 스키마 생성(§2.1 DDL), `_meta` 테이블, Trino 백엔드 접속.
- ✅ 22 gold→D1 매핑표대로 테이블 존재. ✅ `d1_meta` 에 각 source_table row.

**M1 — D1 export 파이프라인**: 직송 15 + 롤업 7. 타입 정규화·비율 재산출·전량 교체 스왑.
- ✅ 재실행 2회 후 행수·PK 동일(멱등). ✅ churn 롤업 `churn_rate=closed/stock_start` 재산출값이 원본 합과 일치(±반올림). ✅ flow_monthly 롤업 181,430행 근사. ✅ decimal→REAL, 코드→TEXT, boolean→0/1.

**M2 — D1 API(소형)**: survival·geo(non-heatmap)·biz(rollup)·succession·governance 전 엔드포인트.
- ✅ 각 엔드포인트 200 + 스키마 일치. ✅ enum 위반 400, 단건 없음 404. ✅ 페이지네이션·정렬·meta 봉투. ✅ summary 엔드포인트 서버집계(diagonal_ratio 등) 정확.

**M3 — Iceberg API(대용량)**: daily, monthly/detail, churn/detail, uptae(gu), heatmap(iceberg 폴백).
- ✅ daily from/to 없으면 400. ✅ 파티션 프루닝 확인(explain range). ✅ 503 retryable + 캐시. ✅ `yearly=Σmonthly=Σdaily` 정합(동일 필터 샘플 3건).

**M4 — 프런트 화면 6종**: 필터 셸→위젯→드릴다운→경고 배지.
- ✅ 6화면 위젯 전수 바인딩. ✅ 드릴다운(연→월→일, 구→동, 매트릭스 셀). ✅ notes→배지(approx/seed/coverage), low_sample 회색. ✅ 재빌드 윈도우 '준비중' 상태 처리, 미등록 gold graceful. ✅ active vs 누적 혼용 없음(코드리뷰 체크).

**M5 — 검수·최적화**: 캐시 TTL, 접근성, 반응형, 데이터 기준일 노출.
- ✅ 라이트하우스 접근성 통과. ✅ 모바일 가로스크롤 없음. ✅ 모든 화면 `snapshot_at` 노출.

**전역 수용 기준(테스트 가능):**
1. 22 gold 지표가 최소 1개 API·위젯에 매핑(추적표 §1.1).
2. D1 응답과 Iceberg 폴백 응답의 **필드 스키마 동일**(프런트 소스 무관).
3. 기간 range 필터가 문자열 비교로 동작(2024-02-30 같은 무효는 400).
4. UNK 버킷: 집계 포함되되 지도/동리스트 기본 숨김+각주.
5. 근사/씨앗/커버리지 라벨이 해당 위젯에 100% 노출.

---

## 6. 주의·함정

1. **flow 완결기간·멱등**: flow_daily/monthly/yearly 는 당일/당월/당해 제외 완결분만(append-only, 재실행 0건). 화면은 미완결 최신 구간을 표시 안 하거나 회색. D1 롤업도 이 계약 상속.
2. **해상도 정합**: 동일 필터에서 `yearly cnt = Σ monthly = Σ daily`. 드릴다운은 연→월→일 같은 축 좁혀 호출. 어긋나면 롤업 GROUP BY 버그.
3. **문자열 ISO 사전순**: 날짜 range 는 문자열 비교로 안전(`'2024-01' <= ym <= '2024-12'`). Date 파싱/타임존 변환 금지. 커버리지 1900~2025 원천 그대로 → 기본 최근 20~30년, 1900 등 극단연도 접기.
4. **UNK 지역코드**: gu/admin_dong/legal 결측='UNK' 버킷. 지도·지역필터에서 별도 처리(합계 각주).
5. **churn 근사(seed)**: stock_start=연 단위 문자열 연산 기반 '근사 영업스톡'(분모). 🟠 배지. stock_start=0 → rate NULL. **비율은 롤업 시 합산 불가 → opened/closed/stock_start 합산 후 재산출**.
6. **재빌드 윈도우**: gold 는 정기 --full-refresh 로 재빌드되며 그 짧은 구간엔 조회 불가('Metadata not found') → API 503 building, 위젯 '준비중', 완료 후 자동 정상화. seasonality window=최근 10년 완결연도 근사.
7. **window 상이**: seasonality(10년) vs churn(20년, 2006~2025). 나란히 비교 시 기준연도 각주.
8. **생존 편향**: lifespan=폐업 완결분만(짧게 편향, 🟠 '폐업분 기준'). cohort_survival=편향 없는 정본. 두 수명 3종(cohort/lifespan/status_duration) grain·모수 상이 → 직접 등치 금지.
9. **씨앗 지표(seed)**: status_transition/duration, change_activity 는 이력 축적중. 휴업(02) 원천 0.24%(3,718행) → 02 셀 표본부족, transitions<30 회색. avg_versions≈1 → 절대치보다 상대순위. 🟡 배지.
10. **approx_percentile**: status_duration/lifespan p50/p90, env p50 는 근사 백분위 → 툴팁 '근사'.
11. **상태코드 정규화**: 01~05 + 06(기타)로 dataset별 라벨 이질 통합. dtl 세부 상태와 다름.
12. **LQ 해석**: `lq=구 업종비중/서울 업종비중`. >1=특화. 발산 팔레트 1 중심, 범례 필수. share_in_gu 와 혼동 금지.
13. **active vs 누적**: geo 화면 `active_cnt`(영업 01 스톡) ≠ `business_count`(폐업 포함 누적). **절대 혼용 금지**.
14. **커버리지 각주**: 지오코딩 84%(geo_grid/geocoded_count), 개업일 보유분(opened_last_365d/stock_age_band), 면적 78%(area), 전화 44%(multi_site/phone_succession). 🔵 배지·각주.
15. **succession 근사·비합산**: address(건물단위 주소·window 365d·within_90d·gap≥0) vs phone(전화·주소상이·window 3y·within_1y·gap>0) — 축·시맨틱 상이 → 합산/병합 금지. 분모 없는 절대율 오독 금지. 요약통계만(원장 없음).
16. **decimal 반올림·좌표 double**: 비율 decimal→REAL export 시 반올림 오차 감안(정합 비교 ±ε). 좌표는 double(REAL), 코드는 varchar(TEXT). boolean→0/1.
17. **D1 용량 상한**: 실용 ≪1GB. flow_daily(2.9M)·uptae_mix 원 grain·geo_grid/stock_age_band 세분축은 **D1 금지** → 롤업 파생만. 세부 드릴다운 Iceberg 폴백.
18. **재빌드 중 미등록**: 재빌드 윈도우엔 해당 gold 가 Trino 미등록일 수 있음(D1 export 후엔 무관, Iceberg 폴백만 재빌드 완료 대기). API graceful 503.
19. **lodging 제외**: uptae_mix 는 lodging 스키마 드리프트로 제외 → 각주.
20. **env 수질 결측**: water_pollution_facility 가동일수/시간 보유율≈0 → '원천 결측·실측 불가' 고정 경고. 일반 업종 영업시간은 LOCALDATA 원천 필드 부재(payload 0건) → 화면 상단 고지.

---

*(끝) — 이 문서의 §1.1 매핑표가 22 gold→API·화면 추적의 단일 소스다. 참고 SQL: `dbt/domains/commerce/models/gold/<table>.sql`, 서빙 쿼리: `dbt/domains/commerce/docs/DB/gold/status-aggregation-queries.md`.*
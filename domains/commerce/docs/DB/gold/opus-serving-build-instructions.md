# Opus 구현 지시서 — gold 서빙 API·화면 (commerce)

> 대상: 이 문서만 읽고 백엔드 API 6묶음 + 프런트 화면 6종을 구현하는 에이전트(Opus).
> 원천: 서울 열린데이터 인허가(LOCALDATA) 상권 ELT, medallion raw→bronze(Iceberg)→silver→**gold(집계 전용, Iceberg)**→Serve=**D1(SQLite)**.
> 분류 3단: 대분류 `major`(health/culture/industry/environment) · 중분류 `category` · 소분류 `dataset`(=API 단위). 지역 3축: `gu_code`(25) · `admin_dong_code`(~426) · `legal_code`. `event_type`=opened|closed. 날짜=문자열 ISO(사전순=날짜순).


> 지역 3축 실측 보정: `admin_dong_code` 는 **gold 실측 417개**(dong_summary 기준, 10자리 코드 예 `1168051000`; flow 계열은 +`UNK` 로 418 distinct). 서울 행정동 명목 ~426개 대비 일부 동은 매핑 데이터가 없어 gold 에 부재 — 경계 GeoJSON 과 코로플레스 조인 시 **데이터 없는 동은 '데이터 없음' 스타일**로 렌더(0 과 구분).

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
- 개별 업소(원장 행) 조회 — **Phase 2 로 의도적 이월**(영구 배제가 아니라 단계 밖). 이 문서(Phase 1)는 gold 22 집계만 서빙한다. PROJECT.md §4.3 은 `silver_license_entity` 를 'D1 선별(필터/컬럼 축소) 후보', `silver_<domain>_detail` 을 '대상별 선별 후보'로 명시하며 **서빙 단위 추출 = 코어(entity) ⋈ detail** 이 원칙 — 이 경로는 Phase 2 로 분리한다(윤곽: serving-design.md §8). Phase 1 구현은 Phase 2 를 막지 않도록 `/api/place/*` 경로를 예약하고, 집계 API 의 축 컬럼(dataset·gu_code·admin_dong_code)을 Phase 2 필터 계약과 동일하게 유지한다.
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

### 1.4 Airflow 통합 — export 시점·재개·R2 마커·stale 규칙

**배치·트리거(정기).** D1 export 는 **매일 1회**, 별도 스케줄이 아니라 `commerce_load_gold`(06:00 KST, 선행 체인: bronze 04:00 → silver 05:00 → gold 06:00, 모두 KST) **같은 DAG run 안**에서 dbt 성공 직후·리포트 직전에 실행한다.

```
dbt_gold(Cosmos — 22 gold run+test) ──> export_d1(직송 15 + 롤업 7 + current 2 + dim 4) ──> report_gold
```

- `export_d1` 은 **dbt_gold 전체 성공 시에만** 실행(기본 all_success). 일부 gold 실패 시 그날 export 는 스킵하고 D1 은 **직전 스냅샷을 그대로 서빙**(해당 테이블 `d1_meta.build_status='stale'` 갱신). `report_gold` 는 기존 `trigger_rule="all_done"` 유지 — export 가 실패해도 반드시 보고.
- **롤업 파생 7종(§1.3)·current 계열 2종(§2.1)·dim 4종(§2.1)은 별도 dbt 모델이 아니라 export_d1 태스크 내 Trino SELECT/소스 직독**으로 산출한다 — D1 전용 형상이므로 Iceberg 에 물리 테이블을 늘리지 않는다(늘리면 유지보수 op·리포트 정본 목록이 같이 늘어난다). current 계열은 소스가 silver_license_entity 라 silver 완료 후면 추출 가능하지만, **단일 export 실행으로 22 gold 스냅샷과 같은 시점에 함께 갱신**한다(화면 데이터 기준일 단일화).
- **대상 명단 정본**: 22 gold 목록은 `include/gold/report.py::AGG_TABLES`(정본)를 그대로 소비하고, gold→d1 테이블 매핑(§1.1 판정표)만 export 모듈 상수로 둔다 — DAG select·리포트·export 가 1곳 관리 규약을 유지.
- **수동 전량 재구축(`commerce_load_gold_refresh`, 트리거 전용)**: full-refresh 는 지연 도착(과거 기간 소급 신고)을 스윕하므로 완료 시점에 D1 이 반드시 낡는다 → `load_details_full` 뒤에 동일 `export_d1` 을 편입해 **재export 까지가 refresh 의 완료 조건**이다. 임의 시점 단독 export 트리거는 금지(재빌드 윈도우·메타 캐시 경합 — §6-21·23).

```
build_catalog ──> dbt_gold(full-refresh) ──> load_details_full ──> export_d1 ──> report_gold
```

**재개 계약(PROJECT.md §3 준수).** export 단계도 §3 표준의 단위·마커를 갖는다.

| 단계 | 단위 | 완료 제외 | 실패 이어받기 | 중단 → 미완성 drop |
|---|---|---|---|---|
| **serve(D1 export)** | d1 테이블 1개 | R2 export 마커(아래)의 `snapshot_at` ≥ 이번 run 의 dbt_gold 완료 시각이면 skip | 마커 미기록(실패) 테이블만 재export — 성공분은 마커로 제외 | `*_next` 스테이징 테이블 DROP 후 재실행(스왑 전 중단분은 D1 서빙에 노출되지 않음) |

- **부분 실패 허용**: 22 대상 중 일부 실패 시 성공 테이블은 스왑·마커 기록까지 전진하고, 실패 테이블만 `d1_meta.build_status='stale'`(직전 스냅샷 서빙 유지) — 같은 run 재시도(retries)·다음 run 이 실패분만 이어받는다. 테이블 간 참조·조인이 없으므로(§1.1 평탄화) 테이블 단위 부분 전진은 안전하다.
- **방식 정본 확정**: flow 계열 포함 모든 D1 대상은 **전량 교체 스냅샷**이 정본이다. `status-aggregation-queries.md` 부록의 "D1 export 도 max(기간키) 초과분만 append" 는 초기 제안으로 폐기한다 — full-refresh 소급 스윕이 과거 기간을 재작성하므로 append 로는 D1 에 반영 불가하고, 롤업 후 최대 ~18만 행이라 전량 교체 비용이 무해하다(해당 문서 부록에 폐기 주석 반영).

**스왑 전 게이트(행수 밴드 — 비용·오적재 가드).** export 는 테이블별 **기대 행수 밴드**(§1.1 실측치 ±50%)를 상수로 갖고, 적재된 `*_next` 의 행수가 밴드 밖이면 **스왑하지 않고** `build_status='stale'` 유지 + `log_event("serve.d1_rowcount_alert", ...)` 경보. 특히 **0행**(원천 파손/재빌드 윈도우 충돌 — 무조건 중단)과 **2배 초과**(롤업 GROUP BY 회귀 — 예: uptae gu 드롭 누락 시 29,683행 원 grain 유입)를 잡는다. 어느 경우든 D1 은 직전 스냅샷 유지로 실패가 서빙에 전파되지 않는다.

**R2 export 상태 마커(`commerce_serve_state`).** `d1_meta` 는 API 노출용(소비자 측)이고, **파이프라인 재개·검증의 정본은 R2 파일 레이어**로 둔다 — silver 의 `commerce_silver_state`(`_markers.json`/`_watermark.json`)와 대칭 규약(마커 테이블 유실 실측 이후 확립된 패턴). `export_d1` 이 테이블 스왑 성공 직후마다 갱신한다(테이블과 파일은 한 몸, 기록 실패는 경고만·fail-open — 파일이 뒤처지면 skip 없이 재export 할 뿐이라 안전).

```json
// commerce_serve_state/_export_state.json — 테이블별 export 완료 기록(전량 스냅샷)
{"tables": {
   "d1_flow_monthly": {
     "snapshot_at": "2026-07-16T21:12:03+00:00",      // D1 스왑 완료 시각(UTC) = d1_meta.snapshot_at 과 동일 값(이중 기록)
     "source_table": "gold_license_flow_monthly",
     "iceberg_snapshot_id": 4812734596871234567,       // export 가 읽은 Iceberg 스냅샷($snapshots 최신, §6-21 검증값)
     "source_row_count": 1338656, "d1_row_count": 181430,
     "gold_built_at": "2026-07-16T21:05:40+00:00"}},   // 이번 run dbt_gold 완료 시각
 "updated_at": "..."}
```

- 용도: ① 재실행 skip 판정(위 재개 계약 — `snapshot_at ≥ gold_built_at` 이면 완료 제외), ② **full-refresh 후 재export 필요 판정** — 현재 gold 의 `$snapshots` 최신 id ≠ 마커의 `iceberg_snapshot_id` 면 D1 이 낡은 것, ③ D1↔Iceberg 정합 감사(행수 대조), ④ 화면 '데이터 기준일'의 파이프라인 측 근거.

**stale 판정·`d1_meta` 확장.** `d1_meta` 에 `source_max_event_date TEXT` 컬럼을 추가한다(status-aggregation-queries §7.3 의 `meta_refresh` 를 별도 테이블로 두지 않고 통합 — §2.1 DDL). API `meta` 봉투와 화면 '데이터 기준일'은 `snapshot_at`(적재 시각)과 `source_max_event_date`(이벤트 최신일)를 **구분해** 노출한다. **stale 판정 규칙**: 조회 시 `snapshot_at < now − 26h`(일 1회 주기 + 여유 2h)면 `build_status='stale'` 취급 → `notes:["stale"]` + 화면 기준일 옆 경고 배지. `building`(재빌드 윈도우)은 Iceberg 경로 한정 — D1 경로는 스왑이 원자적이라 building 이 없고 stale 만 발생한다.

**보안 게이트.** export 스크립트의 외부 호출(Cloudflare D1 API/Trino HTTP)·시크릿·로그·영수증 규약은 §7.6(CLAUDE.md §20 게이트) — 신규 export 코드도 기존 수집기와 동일 게이트 대상이다.

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

-- ===== current-period (entity 파생, gold 22 외 별도 트랙 — status-aggregation-queries §7.3 정본) =====
CREATE TABLE agg_license_daily (      -- from silver_license_entity (§7.3 E1, 롤링 400일)
  dt TEXT NOT NULL, major TEXT NOT NULL, category TEXT NOT NULL, dataset TEXT NOT NULL,
  opened INTEGER NOT NULL DEFAULT 0, closed INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (dt,dataset));
CREATE INDEX ix_ald_dt ON agg_license_daily(dt);

CREATE TABLE agg_license_monthly (    -- from silver_license_entity (§7.3 E2, 전 기간)
  ym TEXT NOT NULL, major TEXT NOT NULL, category TEXT NOT NULL, dataset TEXT NOT NULL,
  opened INTEGER NOT NULL DEFAULT 0, closed INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ym,dataset));
CREATE INDEX ix_alm_ym ON agg_license_monthly(ym);

-- ===== 차원(dim) — 코드→한글 라벨 (조회용 데이터가 아니라 라벨 해석용) =====
CREATE TABLE d1_dim_dataset (         -- from dags/.../config/dataset_registry.yaml (152행, 단일 진실 공급원)
  dataset TEXT PRIMARY KEY,           -- = registry short (gold 의 dataset 키와 동일. data_quality 152종과 1:1 실측)
  name_ko TEXT,                       -- 정식명. 예: '서울시 일반음식점 인허가 정보'
  name_short_ko TEXT,                 -- 표시명. 예: '일반음식점' — name_ko 에서 접두 '서울시 '·접미 ' 인허가 정보' 제거(152종 전부 동일 패턴 실측)
  major TEXT, category TEXT, sub_category TEXT, oa_id TEXT);
CREATE INDEX ix_dd_cat ON d1_dim_dataset(major,category);

CREATE TABLE d1_dim_gu (              -- from gold_license_dong_summary 롤업(자치구 25행) + UNK 1행
  gu_code TEXT PRIMARY KEY, gu TEXT); -- 예: '11680'→'강남구'. 'UNK'→'미상(결측)' 행 명시 삽입

CREATE TABLE d1_dim_dong (            -- from gold_license_dong_summary (417행 — 실측 전수 한글명 보유)
  admin_dong_code TEXT PRIMARY KEY, admin_dong TEXT, gu_code TEXT, gu TEXT);
CREATE INDEX ix_dg_gu ON d1_dim_dong(gu_code);

CREATE TABLE d1_dim_label (           -- enum 코드→한글 정적 시드(§3.1 필터 enum 전수)
  kind TEXT, key TEXT, label_ko TEXT,
  PRIMARY KEY (kind,key));            -- kind ∈ major|category|sub_category|status_code|event_type|age_band



-- 공통 메타
CREATE TABLE d1_meta (
  source_table TEXT PRIMARY KEY, snapshot_at TEXT, row_count INTEGER,
  build_status TEXT,               -- ready|building|stale (stale 판정 26h 규칙: §1.4)
  source_max_event_date TEXT);     -- 이벤트 최신일(status-aggregation-queries §7.3 meta_refresh 통합) — snapshot_at(적재 시각)과 구분 노출
```

> **current 계열 규약**: ① 상대기간 컬럼(`is_today`·`period_label` 류) 저장 금지 — 어제/오늘/이번주/당월/당해는 조회 시점에 SQLite date 함수로 계산(§3.2 `/current`). ② 매일 전량 교체(status-aggregation-queries §7.3 R1 트랜잭션과 등가). ③ §7.3 의 `meta_refresh` 는 별도 테이블로 두지 않고 **`d1_meta.source_max_event_date` 로 통합**(§1.4) — agg_license_daily/monthly 도 각각 `d1_meta` 에 source_table row 를 갖는다.
>
> **dim export 규칙**: ① dim 4종도 본문과 동일하게 **전량 교체 스냅샷**(자연키 PK·멱등, `d1_meta` 에 row 등록). ② `d1_dim_dataset` 소스는 dbt seed(commerce_dataset_taxonomy — name_ko 없음)가 아니라 **registry yaml 직독**(`dags/domains/commerce/config/dataset_registry.yaml`, 152행 단일 진실 공급원). ③ `d1_dim_gu`/`d1_dim_dong` 은 dong_summary 스냅샷에서 파생(동 이름 변경·신설 자동 추종). ④ M0/M1 수용 기준에 dim 4종 존재·행수(152/26/417/시드 전수)를 포함한다(§5).



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



**silver 원형 참조 규칙(Phase 2·정합 검증 대비):** Iceberg 백엔드가 silver 를 참조할 일이 생기면(개별 업소 검증, Phase 2 선행 실험) 정본은 다음과 같다.
- 업소 '현재 상태'는 **`silver_license_entity`**(자연키 `(dataset,opnsfteamcode,mgtno)` grain, 서빙 프로젝션)를 쓴다. `silver_license_current` 는 entity 와 1:1 이지만 `record_json`(통짜 JSON)·주소 정규화 키·버전 정렬키·수집 계보 컬럼을 포함한 **내부 정본 — 서빙 경로 조회 금지**(대형 스캔·내부 컬럼 노출).
- `silver_<domain>_detail` 은 **버전 이력**(grain = 자연키 × collected_at × content_hash). 최신 버전 확보는 **entity ⋈ content_hash 조인이 정본**(status-aggregation-queries §1.4 — food_sanitation 21 dataset 실측 커버리지 100%·팬아웃 0). detail 단독 `row_number() over (partition by 자연키 order by collected_at desc)` 는 근사 — 사용 금지.
- `silver_license_entity_history`·`silver_license_history` 는 대용량 append 이력 — 서빙 조회 대상 아님(Iceberg 전용, PROJECT.md §4.3).
- 단, **이 문서(Phase 1) 범위의 API 는 위 어느 것도 조회하지 않는다** — entity/detail 선별 export·조회는 Phase 2 결정 사항(§0.3).

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


  - `status_group`(status_duration) ∈ `영업/정상|휴업|폐업|취소/말소|제외/전출|기타` — **한국어 라벨 원문**(실측, status_code 01~06 대응). `from_group/to_group`(status_transition) ∈ `영업|휴업|폐업|취소/말소|제외/전출` — 01 라벨이 두 테이블에서 **상이**('영업/정상' vs '영업')하므로 화면·조인은 반드시 `status_code`/`from_status·to_status` 기준으로 매핑하고 group 라벨은 표시용으로만 쓴다(라벨 문자열 조인 금지, §6-24).
  - `from_status/to_status` 실측 도메인: 전이 쌍 9종만 존재 — `01→02|03|04|05`, `02→01|03`, `03→01`, `04→01|03`. 05·06 발(發) 전이 없음 → 전이 매트릭스는 5×5 전체가 아니라 희소 셀만 렌더.
- **라벨 정본(한글)**: 코드→한글 매핑의 단일 소스는 PROJECT.md §1 + `include/commerce_core/run_report.py` 의 `MAJOR_KO`/`CATEGORY_KO`/`SUB_KO`. D1 export 시 `d1_dim_label` 로 시드하고(§2.1), 라벨 추가·수정은 그 두 곳과 함께 갱신한다(문서 단독 수정 금지).
  - `major`: `health`=보건 · `culture`=문화 · `industry`=산업 · `environment`=환경
  - `category`(보건 하위 8종): `food`=식품 · `livestock`=축산 · `health_medical`=의료 · `pharmacy`=약국 · `animal`=동물 · `hygiene_beauty`=위생·미용 · `optical_dental`=안경·치과 · `lodging`=숙박. 문화/산업/환경의 category 는 대분류와 동명 1종 → 라벨도 대분류와 동일(문화/산업/환경).
  - **중분류 한계(주의)**: 문화/산업/환경의 실제 중분류(`sub_category` 29종 — 게임제공업·판매업·폐기물 등, 한글 정본 `SUB_KO`)는 **gold 어느 테이블에도 없다**(gold 축=major/category/dataset). 중분류 필터·표기가 필요한 위젯은 `d1_dim_dataset.sub_category` 를 dataset 키로 조인해 클라이언트에서 파생한다 — 서버 스키마 변경 없음.
- **라벨 서빙 규약**: 데이터 엔드포인트는 **코드만 반환**하고 라벨을 조인하지 않는다(D1/Iceberg 필드 스키마 동일 계약 §5-2 유지·응답 경량화). 한글 라벨은 프런트가 부팅 시 `GET /api/dims`(§3.8)를 1회 로드해 클라이언트 dim 캐시(map)로 해석한다. 단, gold 가 원래 실어주는 한글 컬럼(dong_summary·dong_category_matrix·gu_specialization·env 의 `gu`/`admin_dong`)은 그대로 통과.
- **기간 파라미터**: 전부 **문자열 ISO**. `from/to`=`YYYY-MM-DD`, `from_ym/to_ym`=`YYYY-MM`, `from_y/to_y`=`YYYY`. 범위 필터는 문자열 사전순 비교(사전순=날짜순).
- **페이지네이션**: `limit`(기본 100, 최대 1000), `offset`(기본 0). 응답에 `{ "meta": { "total", "limit", "offset", "source":"d1|iceberg", "snapshot_at", "build_status" } }` 포함.
- **정렬**: `sort`(허용 컬럼 화이트리스트), `order` ∈ `asc|desc`(기본 desc).
- **집계 규약**: `group_by` 지원 엔드포인트는 콤마 구분 컬럼(화이트리스트). 서버가 `SUM(cnt)` 등 사전 정의 집계만 수행.
- **응답 봉투**: `{ "data": [...], "meta": {...}, "notes": [ "approx"|"seed"|"coverage"|"incomplete_period"|"building" ... ] }`. 화면 경고 배지는 `notes`로 신호.
- **에러**: `400`(enum/range 위반, 필수 param 누락 — 예 daily from/to 없음), `404`(단건 코드 없음), `429`(rate), `503`(Iceberg 백엔드 불가 → `{ "error":"upstream_unavailable","retryable":true }`; 미빌드 테이블 → `{ "error":"building" }`), `500`.
- **미완결/UNK/근사 신호**: 완결기간 계약상 **flow 계열**(daily/monthly/yearly·그 롤업)에는 최신 미완결 구간(당일/당월/당해)이 애초 없음 → flow 엔드포인트는 해당 없음. **현재기간 수치는 전용 `/api/market-flow/current`(entity 파생 `agg_license_*`, §3.2)만 서빙**하며 항상 `notes:["daily_batch"]`(일 1회 04:00 KST 수집 기준·실시간 아님)를 동반한다. UNK 행은 기본 포함하되 `include_unk` 옵션 있는 엔드포인트는 그 규칙 따름.

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
- **예시**: `GET /api/market-flow/monthly/detail?from_ym=2024-01&to_ym=2024-12&dataset=general_restaurant&admin_dong_code=1168064000`
- **주의**: `dataset` 은 소분류(API `short`, 예 `general_restaurant`) — 중분류 값(`food` 등)을 넣으면 0건. 서버는 dataset 값이 registry short 목록(=`d1_dim_dataset`)에 없으면 400 을 반환해 category/dataset 혼동을 조기에 잡는다.

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



#### `GET /api/market-flow/current` — 소스: **D1** (`agg_license_daily`·`agg_license_monthly`)
- **query**: `period`(**필수**, 콤마 다중) ∈ `yesterday|today|this_week|this_month|this_year`, `major`,`category`,`dataset`(enum, opt), `group_by`(`major|category|dataset` 중, 기본 없음=전체 합계).
- **response_fields**: `period,(group_by 축),opened,closed,net`(net=opened−closed 서버 계산).
- **계산 규약(상대기간 저장 금지 — 조회 시점 계산, status-aggregation-queries §7.2/§7.3 Q)**: KST=UTC+9 보정 고정.
  - `yesterday`: `dt = date('now','+9 hours','-1 day')` (agg_license_daily)
  - `today`: `dt = date('now','+9 hours')`
  - `this_week`: `dt BETWEEN date('now','+9 hours','weekday 1','-7 days') AND date('now','+9 hours')`(월요일 시작)
  - `this_month`: `ym = strftime('%Y-%m','now','+9 hours')` (agg_license_monthly)
  - `this_year`: `ym LIKE strftime('%Y','now','+9 hours')||'-%'`
- **notes**: 항상 `["daily_batch"]` — 원천 일 1회(04:00 KST) 수집이라 '오늘/이번주'는 최신 수집분 기준(실시간 아님). `meta` 에 `source_max_event_date` 포함(어디까지의 이벤트인지).
- **예시**: `GET /api/market-flow/current?period=yesterday,this_month,this_year&group_by=major`
```json
{ "data":[
  {"period":"yesterday","major":"health","opened":41,"closed":58,"net":-17},
  {"period":"this_month","major":"health","opened":812,"closed":790,"net":22}],
  "meta":{"source":"d1","snapshot_at":"2026-07-16T06:40:00+09:00","source_max_event_date":"2026-07-16"},
  "notes":["daily_batch"]}
```
- **정합 계약**: 완결 구간에서 `Σ agg_license_monthly = d1_flow_monthly`(동일 필터) — 어긋나면 추출(E1/E2) 버그.

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
- **query**: `major`,`category`,`dataset`,`min_geo_coverage`,`max_geo_coverage`,`min_total_rows`(기본 0 — 워스트 랭킹 시 초소형 dataset 노이즈 컷용),`sort_by`(`phone_coverage|geo_coverage|admin_dong_coverage|address_coverage|close_date_coverage_of_closed|name_coverage|total_rows`),`order`,`limit`,`offset`.
- **response**: `major,category,dataset,total_rows,active_rows,phone_coverage,geo_coverage,admin_dong_coverage,address_coverage,close_date_coverage_of_closed,name_coverage`.
- **예시**: `GET /api/governance/data-quality?sort_by=geo_coverage&order=asc&min_total_rows=100&limit=10` (좌표결측 최악 API — 실측 순서)
```json
{"data":[
 {"dataset":"caregiver_academy","geo_coverage":0.5243,"total_rows":494},
 {"dataset":"door_to_door_sale","geo_coverage":0.6156,"total_rows":35454},
 {"dataset":"pharmacy","geo_coverage":0.6260,"total_rows":22376}],
 "meta":{"source":"d1"},"notes":[]}
```
- **주의**: `min_total_rows` 미지정 시 1행짜리 dataset(실측: resort_complex total_rows=1, geo_coverage 0.0)이 최상단에 옴 — 워스트 위젯은 기본 `min_total_rows=100` 권장.
- **주의**: `close_date_coverage_of_closed` 는 폐업행 0인 dataset에서 NULL → '해당없음'.

#### `GET /api/governance/data-quality/summary` — 서버 집계
- **query**: `group_by`(`major|category`). response: `major,category,dataset_count,avg_phone_coverage,avg_geo_coverage,avg_admin_dong_coverage,weakest_field`.

#### `GET /api/governance/env-facility-operation` — `d1_env_facility_operation`
- **query**: `dataset`(`air_pollution_facility|water_pollution_facility`),`gu_code`,`sort_by`(`facility_rows|avg_operating_days_per_year|avg_operating_hours|with_operating_days`),`order`.
- **response**: `dataset,gu_code,gu,facility_rows,with_operating_days,avg_operating_days_per_year,p50_operating_days,with_operating_hours,avg_operating_hours,p50_operating_hours`.
- **notes**: `["approx:percentile"]`. 수질은 `with_operating_days≈0`.
- **예시**: `GET /api/governance/env-facility-operation?dataset=air_pollution_facility&sort_by=avg_operating_days_per_year&order=desc` (실측 상위: 도봉구 294.6일 · 금천구 293.6일 · 중랑구 292.8일 — 강서구는 214.9일/466시설).
- **주의**: 정렬 desc 실측 1위는 `gu_code='UNK'`(시설 2개, 300.0일) — 랭킹/지도 위젯은 UNK 행 제외+각주, `facility_rows` 소수(예 <10) 행은 `low_sample:true` 회색 처리.

#### `GET /api/governance/env-facility-operation/coverage`
- **query**: `dataset`. response: `dataset,total_facility_rows,total_with_operating_days,days_coverage_ratio,hours_coverage_ratio`. (수질 days_coverage_ratio≈0 경고용)

---

### 3.8 공통 — 차원(dim) 라벨 일괄 제공

#### `GET /api/dims` — 소스: **D1** (`d1_dim_dataset`·`d1_dim_gu`·`d1_dim_dong`·`d1_dim_label`)
- **query**: `kind`(opt, 콤마: `datasets|gu|dongs|labels` — 기본 전체).
- **response**:
```json
{ "datasets":[{"dataset":"general_restaurant","name_ko":"서울시 일반음식점 인허가 정보","name_short_ko":"일반음식점","major":"health","category":"food","sub_category":"restaurant"}],
  "gu":[{"gu_code":"11680","gu":"강남구"}],
  "dongs":[{"admin_dong_code":"1168052100","admin_dong":"논현1동","gu_code":"11680"}],
  "labels":{"major":{"health":"보건"},"category":{"food":"식품"},"sub_category":{"pollution":"수질오염"},"status_code":{"02":"휴업"},"event_type":{"opened":"개업"},"age_band":{"0_lt1y":"1년 미만"}},
  "meta":{"source":"d1","snapshot_at":"..."} }
```
- **캐시**: 총 ~600행(152+26+417+enum 시드)·수십 KB → 장기 캐시(`max-age=86400`), `snapshot_at` 변경 시 무효화. dim 에 없는 미지 코드는 프런트가 **원문 코드 그대로 표시**(fallback — 신규 dataset 추가 직후 깨짐 방지). 필터 사이드바(major/category/dataset 3단·지역 3축)의 옵션 목록도 이 응답으로 구성한다(별도 하드코딩 금지).

---



## 4. 화면 명세 (6종)

> 공통 셸: 좌측 글로벌 필터 사이드바(major/category/dataset 3단, 지역 3축, 기간) + 상단 데이터 기준일(`latest_collected_at`/`snapshot_at`) + 우측 콘텐츠. 경고 배지 3종 표준화 — 🟠 **근사(approx)**, 🟡 **씨앗(seed, 이력 축적중)**, 🔵 **커버리지(coverage)**. `notes` 배열을 배지로 렌더. `low_sample:true` 행/셀은 회색 처리.



> **표기 규칙(라벨)**: 소분류(dataset)의 정식 표기는 PROJECT.md §1 의 `한글(영문)` = `name_ko(short)` — 예: 서울시 일반음식점 인허가 정보(general_restaurant). 공간이 좁은 축 라벨·칩·범례는 `name_short_ko`(예: '일반음식점')만 쓰고 정식명은 툴팁으로. major/category/status_code/event_type/age_band 는 dim 캐시(§3.8)의 한글 라벨로 렌더하며 **영문 key 를 화면에 노출하지 않는다**(정렬·URL 파라미터는 코드 기준 유지). `UNK` 는 '미상(결측)'으로 표기하고 합계 각주(§6-4)와 연동. `uptaenm` 은 원천이 이미 한글 자유문자열(7,644종)이라 매핑 없이 원문 표시.

> **드릴다운 종착지(Phase 1 계약)**: 모든 화면의 드릴다운 최말단은 **집계 grain**(일×업종×지역 / 격자 / 매트릭스 셀 / dataset)이다. 셀·행 클릭이 개별 업소 목록이나 업소 상세로 이어지는 UX 는 **만들지 않는다** — 개별 업소 조회(entity ⋈ detail)는 Phase 2(§0.3). 종착 셀에서는 '해당 조건 집계 상세 테이블'까지만 열고, 업소명(bplcnm)·개별 주소 등 원장 필드를 기대하는 위젯을 두지 않는다. Phase 2 대비 규약 2가지: ① `/api/place/*` 경로 예약(Phase 1 에서 사용 금지), ② 종착 셀의 필터 상태(dataset·gu_code·admin_dong_code·기간·uptaenm)를 그대로 Phase 2 목록 API 파라미터로 넘길 수 있게 필터 상태를 직렬화 가능한 형태로 관리.

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



**현재기간 표시 전략(이원화)** — 시계열·랭킹은 flow(완결 정본)만 쓰고 미완결 구간은 회색/비표시 유지. 단 '지금까지' 수치는 회색 처리로 대신할 수 없으므로 **current(`/api/market-flow/current`) 를 병행**한다. 두 소스를 한 위젯에서 섞어 합산하지 말 것(계약 상이: 완결 append vs 매일 재계산 잠정).

| 위젯 | 타입 | 바인딩 | 인터랙션·드릴다운 |
|---|---|---|---|
| 현재기간 KPI 스트립 | kpi-card×4 | current `period=yesterday,this_week,this_month,this_year` opened/closed/net | 상단 고정. '최신 수집분 기준(실시간 아님)' 고정 각주, 기준일=`source_max_event_date`. 필터(major/category/dataset) 반영 |
| 이번달 잠정치 오버레이 | line 마커 | current `this_month` | monthly 시계열 말단에 **점선·회색 마커**로 잠정치 1점 표시, 툴팁 '진행중·잠정(완결 시 flow 로 확정)'. 토글 가능 |

**경고/상태 추가**: 현재기간 위젯은 `notes:["daily_batch"]` → 배지. 자정 직후(KST) '어제' 카드가 직전 일자를 가리키는지 QA 항목에 포함(상대기간은 서버 조회 시점 계산이므로 클라이언트 캐시 TTL 은 1h 이하).

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
- ✅ 22 gold→D1 매핑표대로 테이블 존재 + **current 계열 2**(agg_license_daily/monthly) + **dim 4**(d1_dim_dataset/gu/dong/label) 존재(§2.1). ✅ `d1_meta` 에 각 source_table row(`source_max_event_date` 컬럼 포함).

**M1 — D1 export 파이프라인**: 직송 15 + 롤업 7 + **current 계열 2**(agg_license_daily 롤링 400일 / agg_license_monthly 전 기간, entity 파생 — status-aggregation-queries §7.3 E1·E2) + **dim 4**(§2.1). 타입 정규화·비율 재산출·전량 교체 스왑.
- ✅ 재실행 2회 후 행수·PK 동일(멱등). ✅ churn 롤업 `churn_rate=closed/stock_start` 재산출값이 원본 합과 일치(±반올림). ✅ flow_monthly 롤업 181,430행 근사. ✅ decimal→REAL, 코드→TEXT, boolean→0/1.
- ✅ agg_license_daily 가 롤링 400일 경계를 준수하고 재실행 2회 후 행수 동일(멱등). ✅ 완결 구간에서 `Σ agg_license_monthly = d1_flow_monthly`(동일 필터 샘플 3건, ±0). ✅ dim 4종 행수(152/26/417/시드 전수).
- ✅ **파이프라인 통합(§1.4)**: `commerce_load_gold` 에 `export_d1` 편입(`dbt_gold → export_d1 → report_gold`), `commerce_load_gold_refresh` 말미에도 동일 태스크. 단독 스케줄 export 없음.
- ✅ **재개(§1.4 재개 계약)**: 재실행 시 R2 export 마커 기준 완료 테이블 skip, 실패 테이블만 재export — 22 중 1개 강제 실패 후 재실행으로 검증.
- ✅ **리포트(`report_gold` 확장 — PROJECT.md §2 표기 정책 준수)**: 섹션 순서 **에러 › 경고 › 성공**(그룹 간 빈 줄), 실패는 `@export_d1` 태스크 명시, 경고=`stale`(직전 스냅샷 서빙 중) 테이블 `◦` 아웃라인 나열, 성공은 개별 나열 없이 "D1 export N/22 · 총 M행 · snapshot_at" 1줄 요약. 정렬 격자는 ASCII 숫자만, 한글 이름은 줄 끝.

**M2 — D1 API(소형)**: survival·geo(non-heatmap)·biz(rollup)·succession·governance 전 엔드포인트.
- ✅ 각 엔드포인트 200 + 스키마 일치. ✅ enum 위반 400, 단건 없음 404. ✅ 페이지네이션·정렬·meta 봉투. ✅ summary 엔드포인트 서버집계(diagonal_ratio 등) 정확.
- ✅ `/api/market-flow/current` 가 period 5종(yesterday/today/this_week/this_month/this_year)을 KST(+9h) 보정 조회시점 계산으로 반환 — 자정(KST) 직후 호출 시 'yesterday' 가 직전 일자를 가리킴. ✅ 응답 meta 에 `source_max_event_date` 포함. ✅ `GET /api/dims`(§3.8) 4종 반환·장기 캐시 헤더.

**M3 — Iceberg API(대용량)**: daily, monthly/detail, churn/detail, uptae(gu), heatmap(iceberg 폴백).
- ✅ daily from/to 없으면 400. ✅ 파티션 프루닝 확인(explain range). ✅ 503 retryable + 캐시. ✅ `yearly=Σmonthly=Σdaily` 정합(동일 필터 샘플 3건).

**M4 — 프런트 화면 6종**: 필터 셸→위젯→드릴다운→경고 배지.
- ✅ 6화면 위젯 전수 바인딩. ✅ 드릴다운(연→월→일, 구→동, 매트릭스 셀). ✅ notes→배지(approx/seed/coverage), low_sample 회색. ✅ 재빌드 윈도우 '준비중' 상태 처리, 미등록 gold graceful. ✅ active vs 누적 혼용 없음(코드리뷰 체크).

**M5 — 검수·최적화**: 캐시 TTL, 접근성, 반응형, 데이터 기준일 노출.
- ✅ 라이트하우스 접근성 통과. ✅ 모바일 가로스크롤 없음. ✅ 모든 화면 `snapshot_at`·`source_max_event_date` 노출, stale(26h 초과, §1.4) 시 경고 배지 렌더.

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
4. **UNK 지역코드**: gu/admin_dong/legal 결측='UNK' 버킷. 지도·지역필터에서 별도 처리(합계 각주). **UNK 실측 비중(축별 상이 — 경고 강도 차등)**: flow_daily 이벤트(cnt) 가중 실측 — `gu_code` UNK **0.6%**(무해), `admin_dong_code`/`legal_code` UNK **각 42.0%**(치명적). 즉 gu 축 위젯은 UNK 각주만으로 충분하나, **dong/legal 축 드릴다운(`/monthly/detail`·`/yearly/detail`·daily 의 dong/legal 필터)은 이벤트의 약 42%가 UNK 로 빠진 부분 모수**다. 해당 응답에는 `notes:["coverage:admin_dong_42pct_unk"]` 를 상시 포함하고, 화면은 dong/legal 축 합계가 gu/전체 축 합계와 일치하지 않음(42% 결측)을 각주로 고지한다. 동 단위 절대량 비교·코로플레스는 이 축으로 만들지 말 것(동 축 정본은 dong_summary/dong_category_matrix 스톡 지표).
5. **churn 근사(seed)**: stock_start=연 단위 문자열 연산 기반 '근사 영업스톡'(분모). 🟠 배지. stock_start=0 → rate NULL. **비율은 롤업 시 합산 불가 → opened/closed/stock_start 합산 후 재산출**.
6. **재빌드 윈도우**: gold 는 정기 --full-refresh 로 재빌드되며 그 짧은 구간엔 조회 불가('Metadata not found') → API 503 building, 위젯 '준비중', 완료 후 자동 정상화. seasonality window=최근 10년 완결연도 근사.
7. **window 상이**: seasonality(10년) vs churn(20년, 2006~2025). 나란히 비교 시 기준연도 각주.
8. **생존 편향**: lifespan=폐업 완결분만(짧게 편향, 🟠 '폐업분 기준'). cohort_survival=편향 없는 정본. 두 수명 3종(cohort/lifespan/status_duration) grain·모수 상이 → 직접 등치 금지.
9. **씨앗 지표(seed)**: status_transition/duration, change_activity 는 이력 축적중. 휴업(02) 원천 0.24%(3,718행) → 02 셀 표본부족, transitions<30 회색. avg_versions≈1 → 절대치보다 상대순위. 🟡 배지.
10. **approx_percentile**: status_duration/lifespan p50/p90, env p50 는 근사 백분위 → 툴팁 '근사'.
11. **상태코드 정규화**: 01~05 + 06(기타)로 dataset별 라벨 이질 통합. dtl 세부 상태와 다름.
12. **LQ 해석**: `lq=구 업종비중/서울 업종비중`. >1=특화. 발산 팔레트 1 중심, 범례 필수. share_in_gu 와 혼동 금지.
13. **active vs 누적**: geo 화면 `active_cnt`(영업 01 스톡) ≠ `business_count`(폐업 포함 누적). **절대 혼용 금지**.
14. **커버리지 각주**: 지오코딩 84%(geo_grid/geocoded_count), 개업일 보유분(opened_last_365d/stock_age_band), 면적 78%(area), 전화 44%(multi_site/phone_succession). 🔵 배지·각주. **면적 커버리지 분모 주석**: '면적 ~78%'는 **detail 원천(전 상태) sitearea 수치 유효율** 실측이고, 화면 모수(영업01 현재버전·detail 보유 40개 dataset) 기준 실측은 **88.6%**(n_with_area 합 270,963 / 해당 dataset active_rows 합 305,748). 화면 배지는 서빙 모수 기준 '면적 보유 약 89%(영업·detail 보유 업종 한정)'로 표기하고, 78%는 원천 유효율 각주로만 유지한다.
15. **succession 근사·비합산**: address(건물단위 주소·window 365d·within_90d·gap≥0) vs phone(전화·주소상이·window 3y·within_1y·gap>0) — 축·시맨틱 상이 → 합산/병합 금지. 분모 없는 절대율 오독 금지. 요약통계만(원장 없음).
16. **decimal 반올림·좌표 double**: 비율 decimal→REAL export 시 반올림 오차 감안(정합 비교 ±ε). 좌표는 double(REAL), 코드는 varchar(TEXT). boolean→0/1.
17. **D1 용량 상한**: 실용 ≪1GB. flow_daily(2.9M)·uptae_mix 원 grain·geo_grid/stock_age_band 세분축은 **D1 금지** → 롤업 파생만. 세부 드릴다운 Iceberg 폴백.
18. **재빌드 중 미등록**: 재빌드 윈도우엔 해당 gold 가 Trino 미등록일 수 있음(D1 export 후엔 무관, Iceberg 폴백만 재빌드 완료 대기). API graceful 503.
19. **lodging 제외·uptae 커버리지(실측)**: uptae_mix 는 uptaenm detail 보유 **37개 dataset·6개 category**(food·livestock·health_medical·hygiene_beauty·culture·industry)만 포함 — lodging(스키마 드리프트) 외에 **pharmacy·animal·optical_dental·environment 도 원천에 업태 필드가 없어 미포함**. `/api/biz-profile/uptae*` 는 미포함 category/dataset 요청 시 빈 배열 + `notes:["coverage:uptae_37datasets"]` 를 반환하고, 화면은 '업태 데이터 없는 업종' 상태로 렌더한다.
20. **env 수질 결측**: water_pollution_facility 가동일수/시간 보유율≈0 → '원천 결측·실측 불가' 고정 경고. 일반 업종 영업시간은 LOCALDATA 원천 필드 부재(payload 0건) → 화면 상단 고지.


21. **Trino 메타 캐시 stale — export 신선도 게이트(실측)**: 재빌드·DROP 직후의 조회/`count(*)`는 **캐시된 이전 메타로 응답해 파손·미반영을 은폐**할 수 있음이 실측됐다(#74 사고 — 삭제 직후 검증 통과, 캐시 만료 후에야 파손 노출). dbt_gold 성공 직후라도 캐시가 이전 세대 포인터를 주면 어제자 데이터를 오늘자 스냅샷으로 export 하게 되므로, export_d1 은 테이블별 SELECT 전에 신선도를 검증한다: ① `SELECT snapshot_id, committed_at FROM "<table>$snapshots" ORDER BY committed_at DESC LIMIT 1` 이 **이번 run 의 dbt_gold 시작 시각 이후**인지 확인 — 아니면 짧은 backoff 후 재확인(N회 초과 시 해당 테이블 export 실패 처리·직전 D1 스냅샷 유지). ② 'Metadata not found' 는 **retryable** 로 분류(재빌드 창 통과 대기) — 즉시 실패시키지 않는다. ③ 추출 행수 = D1 적재 행수 검증 후에만 스왑. 검증은 **새 연결(신규 세션)** 로 수행하고 행수만이 아니라 `latest_collected_at`/dbt 완료 마커(gold 리포트)와 교차 확인 — **단발 조회 성공을 원천 정상의 증거로 삼지 말 것**. 이때 확인한 `snapshot_id`/`committed_at` 이 R2 마커의 `iceberg_snapshot_id`/`gold_built_at` 으로 기록돼(§1.4) "검증한 스냅샷 = export 한 스냅샷"이 감사 가능해진다.
22. **`__dbt_tmp` 물리 잔재 — 자동 삭제 절대 금지(실측 사고 2회)**: dbt `table` materialization 은 매 실행 `<model>__dbt_tmp-<uuid>` 물리 디렉터리를 웨어하우스에 남긴다. 이 orphan 의 자동 삭제는 **두 차례 시도 모두 라이브 gold 11종을 파손**시켜 '자동 삭제 불가'로 결론났다(#74 — 라이브 메타 디렉터리 오판 + 메타 캐시가 파손을 은폐). 서빙 백엔드·export 파이프라인·운영 스크립트 어디에도 웨어하우스 디렉터리 삭제 로직을 넣지 말 것. 용량 감사는 **리포트 전용** 도구 `dags/domains/commerce/scripts/cleanup_orphan_warehouse_dirs.py`(삭제 없음)만 사용하고, 용량이 실제 문제가 되면 전체 재빌드(gold DROP→dbt run) 경로로만 해소한다.
23. **재빌드 윈도우 × export 경합(생산자 측)**: `commerce_load_gold_refresh` 는 트리거 전용이라 06:00 정기 run 과 겹칠 수 있고, 재빌드 중인 gold 를 export 가 읽으면 'Metadata not found' 실패(양호)가 아니라 **이전 세대/부분 상태를 읽어 성공 → 불량 스냅샷이 D1 에 굳는** 최악 경로가 있다(API 503 과 달리 자동 정상화 없음). 규칙: ① export 는 **자기 DAG run 의 dbt_gold 성공 직후에만** 실행 — 임의 시점 단독 트리거 금지(§1.4). ② 두 DAG 의 dbt_gold+export_d1 구간을 **같은 Airflow pool(slots=1)** 로 상호 배제 — 각 DAG 의 `max_active_runs=1` 은 DAG **간** 경합을 못 막는다. ③ 스왑 전 게이트(행수 0 무조건 중단·직전 R2 마커 `d1_row_count` 대비 ±50% 급변 시 스왑 보류)는 §1.4 — 어느 경우든 D1 은 직전 스냅샷 유지(`build_status='stale'`)로 실패가 서빙에 전파되지 않는다.
24. **enum 한글 라벨·status_group 표기 불일치**: 화면 필터·범례·툴팁의 한글은 `d1_dim_label` 정본으로 통일한다 — `status_code` 01=영업 · 02=휴업 · 03=폐업 · 04=취소/말소 · 05=제외/전출 · 06=기타, `event_type` opened=개업 · closed=폐업, `age_band` 0_lt1y=1년 미만 · 1_1to3y=1~3년 · 2_3to5y=3~5년 · 3_5to10y=5~10년 · 4_10to20y=10~20년 · 5_ge20y=20년 이상. gold 가 실어주는 한글 그룹 문자열은 모델 간 표기가 다르다(status_duration `status_group`='영업/정상' vs status_transition `from_group/to_group`='영업') → 화면 표기는 `*_group` 원문이 아니라 **`status_code` 기준 dim 라벨**을 쓰고, `*_group` 은 서버측 그룹핑 키로만 사용한다(라벨 문자열 조인 금지 — §3.1; gold SQL 수정은 비목표 §0.3 준수).

---

## 7. 보안·운영 계약 — API 백엔드·export (CLAUDE.md §20 게이트 적용, 필수)

> 이 서빙 표면(Workers API·Trino 프록시 백엔드·export 스크립트)은 번들 이식형 보안 게이트(dags/domains/commerce/CLAUDE.md §20, `dags/domains/commerce/include/security/`, 레시피 `dags/domains/commerce/docs/security/usage.md`) 적용 대상이다. 공개 read-only 라도 아래를 전부 지킨다. 완료 전 `PYTHONPATH=dags/domains/commerce/include python -m security` 차단(CRITICAL/HIGH) 0 확인.

### 7.1 입력 검증 (모든 엔드포인트)
- **기간 param**: `from/to`(YYYY-MM-DD)는 수신 즉시 `assert_iso_date` 로, `ym/y` 는 `^\d{4}(-\d{2})?$` 정규식으로 검증 → 위반 400. 문자열 사전순 비교(§3.1)의 안전은 이 검증이 전제다.
- **enum param**: major/category/event_type/status_code/age_band/gu_code/period 는 §3.1 화이트리스트 exact match — 미일치 400. `dataset`·`uptaenm` 등 자유 문자열 param 은 `assert_safe_segment` 통과 후에만 사용(캐시 키/경로 재사용 대비).
- **SQL 값**: 전부 드라이버 **파라미터 바인딩**(D1 `.bind()`, Trino 클라이언트 파라미터). 문자열 조립 SQL 금지(정적 점검 `no_sql_text_injection` 대상).
- **SQL 식별자**: `sort`/`group_by`/`metric` 은 param→컬럼명 **고정 매핑 테이블**로만 치환(매핑 밖 400). 동적 식별자를 불가피하게 끼울 땐 `assert_identifier`.

### 7.2 Trino 프록시 (Iceberg 경로)
- Trino HTTP 호출은 `netio.http_request`(timeout 자동 주입·TLS 검증 비활성 차단·예외 마스킹)로만. 타임아웃 명시(권장 connect 5s / read 30s).
- Trino endpoint URL 은 **서버 설정 고정값만** — 클라이언트 입력이 대상 host/포트/카탈로그/스키마에 닿는 경로 금지(SSRF 원천 차단). 설정 로드 시 `assert_url_allowed` 1회 검증.
- 프록시는 §2.2 규칙(범위 필수·LIMIT 상한) 위반 쿼리를 **Trino 도달 전에** 400 반환.

### 7.3 에러 응답 · 로그 redact
- 5xx 응답 body 에 **내부 정보 금지**: Trino DSN/호스트/포트, 스택트레이스, 파일 경로, 실행 SQL 원문 노출 금지. 클라이언트에는 §3.1 고정 포맷(`upstream_unavailable`/`building`)만.
- 서버 측 기록은 `log_exception(exc, where=...)`/`redact()` 경유(마스킹된 단일 라인 JSON). 연결 문자열을 로그에 남길 땐 `mask_dsn` 필수.

### 7.4 rate limit · CORS · 인증
| 항목 | 방침 |
|---|---|
| rate limit | IP 당 분당 상한 — D1 경로 120 rpm · Iceberg 경로 20 rpm(백엔드 보호 목적이라 더 낮게). 초과 `429` + `Retry-After` |
| CORS | `Access-Control-Allow-Origin` 은 프런트 도메인 화이트리스트만(`*` 금지). 허용 메서드 GET 한정 |
| 인증 | 공개 read-only 지표라 최종사용자 토큰은 선택. 단 **Workers→Trino 프록시 백엔드 내부 구간은 시크릿 헤더 상호 인증**(`generate_token` 발급·`constant_time_equals` 비교) — 프록시 백엔드를 공인터넷에 익명 노출 금지 |
| 응답 헤더 | `X-Content-Type-Options: nosniff` · `Content-Type: application/json` 고정 |

### 7.5 백엔드 보호 상한(비용·가용성 — LIMIT 과 별개로 강제)
- **쿼리 타임아웃**: 프록시가 Trino 세션 프로퍼티 `query_max_run_time=30s`(+클라이언트 read timeout 30s)를 강제 — 장기 쿼리의 코디네이터 점유 차단. 타임아웃은 `503 retryable` 로 변환.
- **동시성 상한**: 프록시 전역 동시 Trino 쿼리 세마포어 N≤4. 초과분은 짧은 대기(2s) 후 `503 retryable`(캐시/재시도 유도). Trino 는 서빙과 ELT(06:00 dbt gold 22모델)가 공유하는 단일 인스턴스이므로 서빙 트래픽이 ELT 재빌드와 경합하지 않게 상한 필수.
- **스캔 범위 상한**: daily 는 `from/to` 폭 ≤366일(초과 400 — 더 긴 구간은 monthly/yearly 로 유도), heatmap iceberg 폴백은 bbox 필수. LIMIT 상한(행수)과 범위 상한(스캔량)은 별개 가드다.
- **재빌드 시간대 완충**: 06:00 KST 전후 재빌드 윈도우(§6-6)엔 캐시 서빙을 우선하고 miss 는 `building` 반환 — 재빌드와 대형 조회의 동시 실행은 양쪽 다 악화시킨다.

### 7.6 export 스크립트 보안(CLAUDE.md §20 게이트, 필수)
- 진입점에서 env 적재 직후 `install_security()` 1회 — 이후 로그/stdout/미처리 예외에서 등록 시크릿 자동 마스킹.
- 자격증명(Cloudflare D1 API 토큰·account id, Trino 접속 계정)은 `dags/domains/commerce/.env.commerce`(gitignore) 에 둔다 — **루트 `.env` 금지**. 변수명은 `*_TOKEN`/`*_KEY`/`*_SECRET` 규약(자동 마스킹) 준수, 규약 밖 이름이면 `register_secret()`.
- Trino HTTP·Cloudflare API 호출은 `netio.http_request`(timeout 자동·TLS 검증 비활성 차단·SSRF `url_check`)로만. API 에러 응답/예외를 저장·알림에 싣기 전 `redact()`(at-rest 누출 차단).
- 실행 영수증: 테이블별 `log_event("serve.d1_exported", table=..., rows=..., snapshot_at=..., elapsed_ms=...)` 단일 라인 JSON — 실패는 `log_exception()` 반환 dict 를 그대로 알림(이미 마스킹돼 전송 안전).
- 머지 전 점검: `PYTHONPATH=dags/domains/commerce/include python -m security` 차단(CRITICAL/HIGH) 0.

### 7.7 비용·캐시 예산
- **DB 총량 예산**: D1 DB 전체 목표 ≤50MB(실용 ≪1GB 의 여유 5%). 스왑 직후 총 행수 합계를 `d1_meta` 에 기록하고 예산 초과 시 경보 — export 대상 추가는 PROJECT.md §4.2 표 갱신과 함께만. 테이블별 행수 밴드 게이트는 §1.4.
- **rows_read 과금 절감**: D1 은 읽은 행 수 기준 과금 — §1.3 top-N 프리컷과 §2.1 인덱스는 지연만이 아니라 **비용 절감 수단**이다. 인덱스 없는 풀스캔 허용은 수백~수천행 d1_direct 에 한정하고, d1_flow_monthly(18만 행)급은 반드시 인덱스 경유.
- **캐시 TTL 표준**: 데이터는 일 1회 스냅샷이므로 캐시는 길수록 안전. D1 경로 응답 `Cache-Control: max-age=3600` · Iceberg 프록시 Cloudflare Cache API TTL 1h(§1.2) · `_meta`/build_status 조회 60s(재빌드 상태 반영 지연 최소화) · `/api/dims` max-age=86400(§3.8) · current 계열 클라이언트 캐시 ≤1h(§4.1). 무효화는 TTL 만료에 맡기고 수동 퍼지는 export 실패 복구 시에만.

---



*(끝) — 이 문서의 §1.1 매핑표가 22 gold→API·화면 추적의 단일 소스다. 참고 SQL: `dbt/domains/commerce/models/gold/<table>.sql`, 서빙 쿼리: `dbt/domains/commerce/docs/DB/gold/status-aggregation-queries.md`.*
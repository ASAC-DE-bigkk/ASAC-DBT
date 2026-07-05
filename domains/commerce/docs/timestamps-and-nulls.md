# 타임스탬프 타임존 · 결측치 처리 규약 — dbt/domains/commerce

silver 모델이 다루는 모든 시각 컬럼의 **타임존 실태**와 **결측치(null) 처리 규칙**,
그리고 각 규칙이 **어느 파일의 어느 단계에서** 적용되는지 정리한다.
(조사 근거: ASAC-DAG `dags/domains/commerce/include/bronze/` 적재 코드 실사 — 2026-07-05)

---

## 1. 타임스탬프 타임존 실태 — **KST와 UTC가 혼재한다**

| 컬럼 | 생산자 | 타임존 | 형식/타입 | 근거 |
|---|---|---|---|---|
| `UPDATEDT` (→ `updatedt`, `updatedt_ts`) | 소스(개방 플랫폼 갱신시각) | **KST** (naive) | 문자열, 14자리 `YYYYMMDDHHMMSS` 기대(비정형 가능) | LOCALDATA 표준 — 한국 지자체 데이터는 KST 표기 |
| `LASTMODTS` (→ `lastmodts`, `lastmodts_ts`) | 소스(원천 시스템 최종수정시점) | **KST** (naive) | 문자열, `YYYY-MM-DD HH:MM:SS` 계열 기대(비정형 가능) | 상동 |
| `APVPERMYMD` / `DCBYMD` (인허가일/폐업일) | 소스 | **KST** 의미의 날짜 | 문자열 날짜(형식 비균일 가능) | 상동 |
| `collected_at` | 파이프라인(수집 마커) | **UTC** (naive) | Iceberg `timestamp(6)` | 수집 시 `_utcnow_iso()` 로 기록(`include/bronze/bronze_tasks.py`), 적재 시 `_to_naive_utc()` 로 UTC naive 변환(`include/bronze/warehouse.py`) |
| `observed_date` | 파이프라인(논리 수집일) | **KST** 날짜 | 문자열 `YYYY-MM-DD` | 수집 DAG 가 KST 로 산출 |
| `load_date` | 파이프라인(적재일, bronze 파티션) | **KST** 날짜 | 문자열 `YYYY-MM-DD` | `commerce_load_bronze.resolve_load_date()` 가 KST 로 산출 |
| `bronze_run_id` | 파이프라인(run 식별자) | **KST** 시각 문자열 | `YYYY-MM-DD_HHMMSS_mmm` | `make_bronze_run_id` (KST) |

### 사용 시 주의 (혼재의 귀결)

- **`updatedt_ts`/`lastmodts_ts`(KST)와 `collected_at`(UTC)을 직접 비교·연산하지 말 것.**
  9시간 차이가 그대로 오차가 된다. gold 에서 두 계열을 함께 쓰려면
  `collected_at + interval '9' hour` 로 KST 정렬 후 사용하거나, 한쪽 계열만 쓴다.
- 버전 정렬키(`updatedt_sort, lastmodts_sort, observed_date, collected_at, content_hash`)에서
  `collected_at` 은 **4순위 tie-break** 로만 쓰인다. 같은 키의 행끼리 일관되게 UTC 로 비교되므로
  **순서의 결정성은 유지**된다(절대 시각 해석만 금지).
- source freshness(`models/sources.yml` 의 `loaded_at_field: collected_at`)는 UTC 기준으로
  현재 시각과 비교되므로 정합하다.
- Iceberg/Trino 의 `timestamp(6)` 는 타임존 없는 벽시계 값이다 — 위 표의 타임존은
  **값의 의미**이지 타입에 담겨 있지 않다. 신규 컬럼을 추가할 때 반드시 이 표를 갱신할 것.

---

## 2. 결측치 처리 규약 (v1)

원칙: **원본은 건드리지 않고**(`record_json`·bronze 불변), 파싱된 silver 컬럼에서만 정규화한다.
변경 감지(`content_hash`)는 원본 기준이므로 아래 정규화는 버전 판정에 영향을 주지 않는다.

| 대상 | 규칙 | 결과 |
|---|---|---|
| 파싱 문자열 필드 전부 (`bplcnm`, `trdstategbn`, `trdstatenm`, `dtlstategbn`, `dtlstatenm`, `apvpermymd`, `dcbymd`, `sitetel`, 주소 2종, `X`/`Y`, `lastmodts`) | `nullif(trim(...), '')` — 소스의 빈 문자열/공백을 null 로 | 결측 = null 로 일원화 |
| 소스에 필드 자체가 없는 경우(업종군별 개별 컬럼 등) | `json_extract_scalar` 가 null 반환 | null |
| `updatedt_ts` / `lastmodts_ts` 파싱 실패(비정형) | `try(date_parse(...))` → null | null (원문은 `updatedt`/`lastmodts` 에 보존) |
| 버전 정렬 시 timestamp 결측 | `coalesce(*_ts, epoch)` = `*_sort` 컬럼 | **가장 오래된 것**으로 취급(정렬 전용 — 시각 해석 금지) |
| 주소 정규화(`*_norm`) | `'(' 이후 절단 → 연속 공백 1개 → trim → 빈값 null` | Python 수집측(geocode)과 규칙 동일 유지 필수 |
| `district` 미매칭(서울 외/주소 결측) | `regexp_extract` 미매칭 → null | null |
| 좌표 `X`/`Y` 의 `0`·자릿수 오류 등 **품질 불량값** | **보존**(null 처리하지 않음) | 좌표 품질 판정은 Step 8 geocode 파이프라인(bbox 검증·`location_quality`)의 책임 |

미정(후속 결정 필요): `DCBYMD`(폐업일) 등 날짜 문자열의 형식 통일(`date` 형변환) 여부 —
현재는 문자열 그대로 두고 gold 에서 필요 시 변환한다.

---

## 3. 어디에서 처리되는가 (파일 · 단계)

모든 규칙은 dbt 모델 한 곳에서 적용된다 — [models/silver/silver_license_history.sql](../models/silver/silver_license_history.sql):

| CTE | 하는 일 |
|---|---|
| `publishable` → `bronze` | 발행 게이트(manifest `SUCCESS`+`is_publishable`) 통과 run 만 유입 |
| `parsed` | `record_json` 에서 공통 필드 추출 + **결측 규약 v1**(`nullif(trim(...),'')`) + `updatedt_ts` 파싱 |
| `normalized` | `lastmodts_ts` 파싱 + 주소 정규화 + `district` 파생 |
| `keyed` | 주소 키 2종 + 정렬 전용 `updatedt_sort`/`lastmodts_sort`(결측=epoch) |
| `ordered` → `deduped` | 암묵 버전 정렬키로 인접 중복 제거 |

`silver_license_current`([models/silver/silver_license_current.sql](../models/silver/silver_license_current.sql))는
history 를 재파싱하지 않고 정렬 최상위 1행만 선택하므로, 결측 규칙은 history 한 곳에만 존재한다.
불변식 검증: [tests/](../tests/) 4종 (`dbt test`).

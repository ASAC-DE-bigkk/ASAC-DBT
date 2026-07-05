# 타임스탬프 타임존 · 결측치 처리 규약 — dbt/domains/commerce

silver 모델이 다루는 모든 시각 컬럼의 **타임존 정책**과 **결측치(null) 처리 규칙**,
그리고 각 규칙이 **어느 파일의 어느 단계에서** 적용되는지 정리한다.
(조사 근거: ASAC-DAG `dags/domains/commerce/include/bronze/` 적재 코드 실사 — 2026-07-05.
타임존 정책 UTC 일원화 확정 — 2026-07-06 사용자 결정.)

---

## 1. 타임존 정책 — **silver 의 timestamp 는 전부 UTC(naive)로 일원화**

국제표준(저장=UTC, 표시=로컬) 정렬 — silver 적재 시점에 KST 원문 시각을 UTC 로 변환한다.
원문 문자열은 감사용으로 그대로 보존한다.

| 컬럼 | 원천 의미 | silver 처리 | 결과 |
|---|---|---|---|
| `updatedt` / `lastmodts` (문자열) | 소스 KST 원문 (`YYYYMMDDHHMMSS` / `YYYY-MM-DD HH:MM:SS` 계열) | **무변환 보존**(감사·재처리용) | KST 원문 |
| `updatedt_ts` / `lastmodts_ts` | 위 원문의 파싱 시각 | 파싱 후 **`- interval '9' hour`** (KST → UTC) | **UTC** timestamp |
| `updatedt_sort` / `lastmodts_sort` | 버전 정렬키 | 위 UTC 값의 결측=epoch 치환(정렬 전용) | UTC 기준 정렬 |
| `collected_at` | 파이프라인 수집 시각 — 수집 마커가 `_utcnow_iso()` 로 **처음부터 UTC 기록** (`include/bronze/bronze_tasks.py` → `warehouse._to_naive_utc()`) | **무보정 통과** | **UTC** timestamp |
| `observed_date` / `load_date` / `APVPERMYMD` / `DCBYMD` | KST **달력 날짜**(시간 정보 없음) | 변환 **불가·비대상** — 그대로 보존 | KST 날짜 |
| `bronze_run_id` | KST 실행시각 문자열(식별자) | 식별자로만 사용(시각 연산 금지) | KST 문자열 |

### 사용 시 주의

- **`collected_at` 에 +9h 를 더하지 말 것** — "KST 보다 9시간 빠져 보이는" 것은 UTC 라서이며
  이미 정책상 정답이다. +9h 는 이중 보정이 된다.
- **모든 timestamp 가 UTC 로 통일**됐으므로 `updatedt_ts` ↔ `collected_at` 직접 비교·연산 가능.
- **KST 벽시계로 보려면** 조회/서빙 시점에 `+ interval '9' hour` (한국은 DST 없음 — 고정 오프셋).
- **일별 집계 주의(gold)**: KST 하루와 UTC 하루는 경계가 다르다(00:00~09:00 구간).
  일 단위 분석은 KST 날짜 컬럼(`observed_date`/`load_date`)을 쓰거나,
  `date(ts + interval '9' hour)` 로 KST 날짜를 만들어 묶을 것 — `date(ts)` (UTC 날짜) 금지.
- source freshness(`models/sources.yml` 의 `loaded_at_field: collected_at`)는 UTC 기준으로
  현재 시각과 비교되므로 정합하다(변경 없음).
- Iceberg/Trino 의 `timestamp(6)` 는 타임존 없는 벽시계 값이다 — "UTC" 는 **값의 의미**이지
  타입에 담겨 있지 않다. 신규 시각 컬럼 추가 시 반드시 UTC 로 변환하고 이 표를 갱신할 것.
- 서빙 DB 적재 시(후속): `timestamptz` 타입이면 UTC 로 명시 적재(`AT TIME ZONE 'UTC'`),
  표시 변환은 애플리케이션/BI 계층의 몫.

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
| `parsed` | `record_json` 에서 공통 필드 추출 + **결측 규약 v1**(`nullif(trim(...),'')`) + `updatedt_ts` 파싱·**UTC 변환(-9h)** |
| `normalized` | `lastmodts_ts` 파싱·**UTC 변환(-9h)** + 주소 정규화 + `district` 파생 |
| `keyed` | 주소 키 2종 + 정렬 전용 `updatedt_sort`/`lastmodts_sort`(결측=epoch) |
| `ordered` → `deduped` | 암묵 버전 정렬키로 인접 중복 제거 |

`silver_license_current`([models/silver/silver_license_current.sql](../models/silver/silver_license_current.sql))는
history 를 재파싱하지 않고 정렬 최상위 1행만 선택하므로, 결측 규칙은 history 한 곳에만 존재한다.
불변식 검증: [tests/](../tests/) 4종 (`dbt test`).

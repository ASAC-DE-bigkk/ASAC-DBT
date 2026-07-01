# Shared dbt contract guide

이 문서는 ASAC-DBT 도메인별 dbt 프로젝트에서 공통으로 지켜야 할
contract, macro, test 기준을 정리한다. 목적은 모든 도메인을 한 프로젝트로
합치는 것이 아니라, 각 도메인 PR이 같은 품질 기준으로 검토되도록 만드는 것이다.

## 현재 구조

- 각 도메인은 독립 dbt project다.
  - 예: `domains/culture`, `domains/population`, `domains/weather`, `domains/traffic`
- 각 도메인의 `dbt_project.yml`은 자기 `macros/`, `models/`, `tests/`만 본다.
- 따라서 지금 단계에서 `domains/weather/macros`의 macro를 `domains/traffic`이 바로
  import해서 쓰는 구조는 아니다.
- 공통 dbt package를 만들려면 `packages.yml`, package repo/path, 실행 이미지 반영,
  각 도메인 project의 dependency resolution까지 함께 정해야 한다.

결론: 지금은 shared package를 바로 만들기보다, 먼저 아래 계약 기준을 문서화하고
도메인별 macro/test 이름과 의미를 맞춘다. shared package는 팀 합의 후 별도 이슈로
진행한다.

## 공통 contract 원칙

### Source contract

Bronze source는 최소한 다음 컬럼을 계약으로 드러낸다.

| 컬럼 | 의미 | 권장 test |
|---|---|---|
| `source_id` | 원천 식별자 | `not_null`, `accepted_values` |
| `request_id` | API 요청 단위 식별자 | `not_null` |
| `raw_object_key` | R2 raw object lineage | `not_null` |
| `payload_hash` | raw payload fingerprint | 가능하면 `not_null` |
| `collected_at` | ingest time | `not_null`, source freshness |
| `dag_run_id` | Airflow run lineage | `not_null` |
| 원천 event time 구성 필드 | 예: `base_date/base_time`, `occr_date/occr_time` | `not_null` |
| API success code | 예: `result_code` | `not_null`, success row filter |

도메인별 특수 컬럼은 source contract에 설명을 남긴다. 예를 들어 TOPIS
`grs80tm_x/y`는 WGS84 위경도가 아니라 GRS80 TM 좌표임을 명시해야 한다.

### Time contract

Silver 모델은 시간 컬럼을 다음 역할로 분리한다.

| 역할 | 예시 | 설명 |
|---|---|---|
| event time | `occurred_at`, `forecast_at` | 원천 이벤트 또는 예보 대상 시각 |
| issued time | `issued_at` | 예보/공표 시각이 따로 있을 때 사용 |
| ingest time | `collected_at` | 파이프라인이 수집한 시각 |
| bucket time | `time_bucket` | Gold 집계 단위 |

규칙:

- raw 문자열을 Silver에서 timestamp로 표준화한다.
- 변환 실패 가능성이 있는 필드는 `try_cast`, `case`, `regexp_like` 등으로 실패 row를
  명시적으로 다룬다.
- `event_time`과 `ingest_time`을 섞어 쓰지 않는다.
- freshness는 기본적으로 `collected_at` 기준이다.

### Grain and dedup contract

Silver 모델은 grain을 모델 설명 또는 test 이름으로 드러낸다.

예:

- weather: `place_id, nx, ny, issued_at, category, forecast_at`
- traffic current-state: `source_record_id`
- culture location daily: `location_key, activity_date`

규칙:

- dedup 기준은 PR 본문과 model/test에 둘 다 남긴다.
- `row_number()`로 최신 row를 고르는 경우 `order by`에 tie-breaker를 둔다.
  - 예: `collected_at desc, raw_object_key desc, request_id desc`
- 시계열 이력을 보존해야 하는 상품에서 단순 source id 최신 1건 dedup을 쓰지 않는다.

### Coverage and completeness contract

Coverage test는 "데이터가 있음"만 보지 말고 기대 범위 대비 실제 범위를 비교한다.

예:

- weather: 최신 `issued_at` 기준 distinct grid count가 기대 grid 수 이상인지 확인
- traffic: 최신 `dag_run_id` 전체 request audit 묶음에서
  `sum(row_count) >= max(list_total_count)`인지 확인
- population: 주요 city/area가 비어 있지 않은지 확인

규칙:

- 최신 단일 `collected_at` row만 보는 test는 page 단위 수집과 맞지 않을 수 있다.
- request/page가 여러 개면 `dag_run_id` 기준으로 묶는다.
- 정상 zero-row 응답은 incident row table이 아니라 request audit table로 검증한다.

## Macro 기준

### 지금 유지할 것

도메인별 timestamp parser는 당분간 domain-local macro로 유지한다.

이유:

- KMA, TOPIS, 문화 데이터의 날짜/시간 형식이 서로 다르다.
- 억지로 하나의 parser에 옵션을 늘리면 macro가 복잡해지고 검토가 어려워진다.
- 현재 repo 구조상 도메인별 dbt project가 macro를 직접 공유하지 않는다.

권장 이름:

| 패턴 | 예시 |
|---|---|
| `<source>_timestamp(date_col, time_col)` | `kma_timestamp`, `topis_timestamp` |
| `<source>_<domain>_normalizer(...)` | 좌표/상태/코드 정규화가 필요할 때 |

### 공통화 후보

아래는 바로 구현하지 않고 shared package 설계 이슈에서 검토한다.

| 후보 | 이유 |
|---|---|
| generic `grain_unique` test | 여러 도메인이 `group by ... having count(*) > 1`를 반복 |
| generic `not_empty` test | Gold/Silver 빈 테이블 검증 반복 |
| generic `counts_match` test | Silver/Gold row/raw object count 비교 반복 |
| generic freshness/coverage helper | source별 threshold와 coverage 기준 표준화 |

## PR checklist

dbt PR은 최소한 아래를 본문에 적는다.

- Source table: `catalog.schema.table`
- Target table: `catalog.schema.table`
- Event time 컬럼
- Ingest time 컬럼
- Dedup/grain 기준
- Freshness 또는 coverage test 여부
- `dbt parse`, `dbt run`, `dbt test` 결과
- 다른 도메인 모델 삭제/변경 diff가 없는지 여부
- downstream 영향 또는 blast radius

## 적용 상태

현재 열린 PR 기준:

- weather PR #26
  - KMA timestamp parser는 `kma_timestamp` domain-local macro로 유지한다.
  - grid coverage test는 최신 `issued_at` 기준 distinct grid count를 본다.
- traffic PR #27
  - TOPIS timestamp parser는 `topis_timestamp` domain-local macro로 유지한다.
  - request audit coverage test는 최신 `dag_run_id` 전체 page 묶음을 본다.

## 후속 이슈 후보

shared package는 다음 조건을 만족할 때 별도 이슈로 진행한다.

- 최소 3개 이상 도메인에서 같은 SQL test 패턴이 반복된다.
- package 적용이 Airflow/dbt 실행 이미지에 반영되는 방법이 정해진다.
- 각 도메인 PR에서 package dependency 변경을 감당할 수 있다.
- `dbt deps`, `dbt parse`, `dbt test`를 CI 또는 Airflow 컨테이너에서 검증할 수 있다.

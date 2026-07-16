# Traffic Quality Gold 설계

## 목적과 승인 범위

Traffic Gold를 서로 다른 분석 질문에 답하는 정확히 5개의 제품으로 게시한다.

| Model | Status | Primary question | Grain |
| --- | --- | --- | --- |
| `gold_traffic_incident_current_by_admin_dong_hourly` | existing | 고정한 현재 Traffic snapshot을 정본 행정동별로 안전하게 게시할 수 있는가 | `admin_dong_code × hour_at` |
| `gold_traffic_incident_x_flow` | existing | 고정한 incident에 flow를 붙여도 incident cardinality가 보존되는가 | `source_record_id` |
| `gold_traffic_incident_collection_coverage_5m` | new | 실제로 물질화된 request-audit 증거는 수집 5분 구간별로 어떤 상태인가 | `source_id × coverage_window_at_utc` |
| `gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily` | new | 현재 snapshot의 incident 중 expected-clear 증거가 있는 비율과 source-provided 예상 간격은 발생일·행정동별로 어떤가 | `profile_day × mapping_bucket` |
| `gold_traffic_incident_spatial_mapping_quality_daily` | new | 현재 snapshot의 incident 공간 매핑 성공과 실패 원인은 발생일·행정동 bucket별로 어떤가 | `quality_day × mapping_bucket` |

`gold_traffic_incident_summary`는 support-only relation이며 위 5개 ship set에 포함하지 않는다.

## 이력에서 보존할 의도

| Evidence | Preserved intent |
| --- | --- |
| `350fc46e` / [`gold_traffic_incident_current_by_admin_dong_hourly.sql`](../../../../models/traffic/transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.sql) | current-hour 제품은 `traffic_snapshot_dag_run_id`로 고정한 snapshot만 소비하고, 행정동 이름·구·revision은 `asac_axes.dim_admin_dong`에서 다시 stamp한다. |
| `8c46fcdf` / [`manifest_state.sql`](../../../../macros/manifest_state.sql) | append-only manifest는 status를 먼저 거르지 않는다. source/run별 최신 유효 상태를 `latest_manifest_run_state(...)`로 선택한 뒤 status와 publishability를 판정해 과거 SUCCESS가 되살아나는 것을 막는다. |
| `f59542c4`, `8c46fcdf` / [`silver_seoul_traffic_incident.sql`](../../../../models/traffic/transform/silver/silver_seoul_traffic_incident.sql) 및 [`silver_seoul_traffic_incident_current.sql`](../../../../models/traffic/transform/silver/silver_seoul_traffic_incident_current.sql) | history와 current Silver는 transform invocation이 받은 exact incident run에 고정된다. 새 daily 제품도 이 current relation을 통해 같은 pin을 상속한다. |
| `b6a06a12` / [`gold_traffic_incident_x_flow.sql`](../../../../models/traffic/transform/gold/gold_traffic_incident_x_flow.sql) | incident가 driving relation이며 flow miss는 유효 incident를 제거하지 않는다. |
| `ede5d2b9`, `8c46fcdf` / [`gold_traffic_incident_summary.sql`](../../../../models/traffic/transform/gold/gold_traffic_incident_summary.sql) | summary는 raw history가 아니라 고정 current snapshot의 작은 집계이며 latest effective manifest contract를 따른다. 이번 변경은 계산을 바꾸지 않고 support-only로만 재분류한다. |
| `eeaa6135`, `b7b0fb46` / [`silver_seoul_traffic_incident.sql`](../../../../models/traffic/transform/silver/silver_seoul_traffic_incident.sql) | `occurred_at`과 `expected_clear_at`은 KST source date/time에서 파싱한다. GRS80 TM source 좌표 존재 여부와 WGS84 변환·boundary 결과는 서로 다른 증거다. |

이 의도를 지키기 위해 기존 두 제품과 support-only summary의 SQL을 재설계하지 않는다. 새 제품은 현재 source와 Silver가 실제로 제공하는 열만 사용한다.

## 확인된 입력 계약

### Request audit와 manifest

`traffic_bronze.seoul_traffic_incident_request_audit`에는 다음 물질화된 요청 증거가 있다.

- identity/lineage: `request_id`, `source_id`, `dag_run_id`, `raw_object_key`, `payload_hash`
- page/request: `start_index`, `end_index`, `request_params_json`
- response: `http_status`, `result_code`, `result_msg`, `list_total_count`, `row_count`
- time: `collected_at`, `load_date`

`latest_manifest_run_state(...)`는 source/run별 latest effective row와 `manifest_status`, `is_publishable`, row/object counts, failure reason, event time을 제공한다. R2 object listing이나 Airflow schedule/run ledger는 dbt source로 제공되지 않는다.

### Pinned current incident Silver

`silver_seoul_traffic_incident_current`는 고정한 publishable incident run의 다음 열을 상속한다.

- identity/time: `source_record_id`, `source_id`, `dag_run_id`, `occurred_at`, nullable `expected_clear_at`, `collected_at`
- source coordinates: `source_location_quality`, `grs80tm_x`, `grs80tm_y`
- converted/mapped coordinates: nullable `longitude`, `latitude`, `admin_dong_code`

`occurred_at`은 Silver에서 필수다. `expected_clear_at`은 TOPIS가 유효한 expected-clear date/time을 주지 않으면 null이다. 따라서 daily 제품의 day는 `occurred_at`의 KST calendar date를 사용한다. expected-clear date를 day grain으로 쓰면 missing expected-clear evidence가 제품에서 사라지므로 사용하지 않는다.

## 공통 계약

- `current_by_admin_dong_hourly`, `x_flow`, expected-clearance profile, spatial quality는 transform invocation의 pinned current snapshot을 사용한다.
- collection coverage는 특정 snapshot var에 고정하지 않는다. 물질화된 audit history를 driving evidence로 사용하고 각 audit의 run을 source/run별 latest effective manifest state에 결합한다.
- manifest를 사용하는 모든 SQL은 `latest_manifest_run_state(...)`를 먼저 적용한 뒤 status를 판정한다.
- daily 제품의 `mapping_bucket`은 정본에 exact join된 `admin_dong_code` 또는 `__UNMAPPED__`다.
- `mapping_bucket = '__UNMAPPED__'`이면 `admin_dong_code`, `admin_dong`, `gu_code`, `gu`, `admin_dong_revision_date`는 모두 null이다.
- 정본 bucket의 명칭·구·revision은 `asac_axes.dim_admin_dong`에서 stamp한다. Silver의 이름 열을 게시 stamp로 self-copy하지 않는다.
- 모든 count는 bigint이며 ratio는 `incident_count`를 분모로 하는 double이다. 분모가 0인 row는 만들지 않는다.
- support-only summary와 recovery relation은 5-product inventory에서 제외한다.

## 제품별 설계

### 1. `gold_traffic_incident_current_by_admin_dong_hourly`

기존 SQL과 계약을 유지한다. 한 행은 canonical `admin_dong_code × hour_at` cell이며, `incident_count = 0`은 complete evidence에서만 허용한다. `quality_state`는 complete, complete_zero, missing, partial, api_failure, current_mismatch, spatial_mapping_incomplete를 구분한다.

### 2. `gold_traffic_incident_x_flow`

기존 SQL과 incident-driving left join을 유지한다. flow가 없어도 incident row는 남고 `flow_match_status`만 `missing_flow`가 된다. incident와 flow는 각각의 pinned run var를 사용한다.

### 3. `gold_traffic_incident_collection_coverage_5m`

이 제품은 scheduled collection SLO가 아니라 **물질화된 snapshot/request-audit 관측 제품**이다.

- driving relation: `traffic_bronze.seoul_traffic_incident_request_audit`
- grain: `source_id × coverage_window_at_utc`
- `coverage_window_at_utc`: audit `collected_at`을 UTC-naive 5분 경계로 내림한 값
- constant: `evidence_scope = 'materialized_snapshot_only'`
- counts: materialized requests, distinct requests, duplicate requests, distinct raw objects, audited rows, successful requests, API-failed requests, invalid-contract requests
- run evidence: observed run count, latest-effective-manifest matched run count, SUCCESS+publishable run count, terminal failure run count, non-publishable run count
- state precedence: `manifest_missing`, `api_failure`, `manifest_not_publishable`, `materialized_partial`, `materialized_zero`, `materialized_consistent`

`api_failure`는 audit의 명시적 non-2xx 또는 non-`INFO-000`에서만 판정한다. generic manifest failure reason은 API failure로 확대 해석하지 않고 `manifest_not_publishable`로 분류한다.

이 모델은 실제 audit row가 존재하는 window만 만든다. landing하지 않은 schedule slot, Airflow가 만들지 않은 run, audit가 전혀 없는 5분 구간은 표현하지 않으며 row count 0의 synthetic window도 생성하지 않는다. 따라서 이 제품으로 scheduled-slot availability, missed schedule, R2 landing SLO를 주장할 수 없다. manifest의 run-level expected rows/objects도 5분 window에 임의 배분하지 않는다.

### 4. `gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily`

이 제품은 pinned current snapshot에 남아 있는 incident를 `cast(occurred_at as date)`로 묶는다. history 전체나 종료된 episode의 실제 지속시간을 나타내지 않는다.

- grain: `profile_day × mapping_bucket`
- `profile_day`: incident 발생시각 `occurred_at`의 KST calendar date
- `mapping_bucket`: canonical code 또는 `__UNMAPPED__`
- `incident_count`: bucket의 모든 current incident, expected-clear evidence가 없는 incident도 포함
- `expected_clearance_present_count`: `expected_clear_at is not null`
- `expected_clearance_missing_count`: `expected_clear_at is null`
- `expected_clearance_usable_count`: `expected_clear_at >= occurred_at`
- `expected_clearance_invalid_count`: `expected_clear_at < occurred_at`
- ratios: 위 네 count 중 present/missing/usable/invalid를 `incident_count`로 나눈 값
- lead metrics: usable row에 한해 `date_diff('minute', occurred_at, expected_clear_at)`의 min/avg/max
- state: no evidence, invalid-only evidence, partial evidence, complete evidence를 명시적으로 구분

lead metric은 TOPIS가 제공한 **expected-clearance lead interval**이며 실제 해결시간이나 관측 duration이 아니다. `expected_clear_at`이 null인 incident를 grain에서 제거하지 않으므로 missing-evidence ratio를 계산할 수 있다.

### 5. `gold_traffic_incident_spatial_mapping_quality_daily`

이 제품도 pinned current snapshot을 발생일로 묶는다.

- grain: `quality_day × mapping_bucket`
- `quality_day`: `cast(occurred_at as date)`
- `mapping_bucket`: canonical code 또는 `__UNMAPPED__`
- canonical bucket: `admin_dong_code`와 canonical stamp가 non-null
- unmapped bucket: `admin_dong_code`와 canonical stamp가 null
- mutually exclusive counts: `mapped_incident_count`, `source_coordinate_missing_count`, `wgs84_conversion_or_bbox_miss_count`, `boundary_match_missing_count`, `canonical_admin_miss_count`

분류 우선순위는 canonical match, source coordinate missing, WGS84 conversion/bbox miss, boundary match missing, canonical dimension miss 순서다. 다섯 count의 합은 `incident_count`와 같아야 한다. 이를 통해 원천 좌표 부재를 boundary 실패와 섞지 않고, source coordinate는 있었지만 WGS84가 없어진 경우와 boundary/canonical join 실패도 분리한다.

## 테스트 및 inventory 전이

- metadata-only existing classification test는 Task 1에서 GREEN이 된다.
- exact five metadata inventory와 physical SQL inventory는 세 새 model/YAML entry가 모두 생길 때까지 의도적으로 RED다.
- 각 새 모델은 grain/semantic test와 source reconciliation test를 가진다.
- compile-only 검증은 synthetic run var를 사용할 수 있다.
- warehouse를 읽고 쓰는 `dbt run`과 `dbt test`는 실제 dev latest-effective SUCCESS+publishable incident/flow run ID만 사용한다.

## Blast Radius

- 변경 가능 경로: `domains/traffic_weather/models/traffic/**`, `domains/traffic_weather/tests/traffic/**`, `domains/traffic_weather/docs/traffic/**`
- 새 warehouse relation: Traffic schema의 새 Gold table 3개뿐이다.
- 기존 SQL 동작: current-hour, x-flow, support-only summary SQL은 변경하지 않는다.
- read-only dependency: 기존 `asac_axes.dim_admin_dong`과 `asac_axes.seoul_admin_dong_boundary`를 읽지만 common relation을 생성·수정하지 않는다.
- 제외: common, weather, package, DAG, selector, profile, project root, production schema/catalog 변경
- consumer impact: 새 relation과 metadata/docs 추가뿐이며 기존 relation의 column/grain을 바꾸지 않는다.

## Rollback

1. 세 새 Gold SQL과 해당 singular tests 및 `_gold.yml` entry를 제거한다.
2. existing two-product metadata와 summary support-only 분류 및 Traffic docs를 이전 상태로 되돌린다.
3. 검증에 사용한 isolated dev `TRAFFIC_SCHEMA`에서 세 새 relation만 drop한다.
4. 기존 current-hour, x-flow, summary relation은 drop/rebuild하지 않는다.

Rollback은 Traffic domain 안에서 끝나며 common/weather/package/DAG/project-root rollback이나 production write가 필요하지 않다.

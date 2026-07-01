# Traffic dbt contract guide

이 문서는 traffic 도메인 dbt PR에서 지켜야 할 source, time, grain,
coverage 계약을 정리한다. 공용 package보다 도메인별 계약을 먼저 정착시키는 것을
목표로 한다.

## 적용 범위

- 도메인: `domains/traffic`
- 원천: Seoul TOPIS AccInfo
- Bronze source: `{{ source('traffic_bronze', 'seoul_traffic_incident') }}`
- Bronze request-audit source: `{{ source('traffic_bronze', 'seoul_traffic_incident_request_audit') }}`
- Bronze table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_seoul_traffic_incident`
- Bronze audit table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_seoul_traffic_incident_request_audit`
- Silver model: `silver_seoul_traffic_incident`
- Gold model: `gold_traffic_incident_summary`

## Source contract

`domains/traffic/models/sources.yml`은 아래 기준을 기본 계약으로 둔다.

### `seoul_traffic_incident`

- 공통 요청/수집 정보: `request_id`, `source_id`, `raw_object_key`,
  `result_code`, `collected_at`, `dag_run_id`는 `not_null`.
- `source_id`는 `seoul_traffic_incident`로 고정 accepted_values.
- TOPIS 사건 id `acc_id`, 일시 `occr_date/occr_time`는 `not_null`.
- 위치계 관련 필드 `grs80tm_x`, `grs80tm_y`는 원천 좌표라 WGS84 위경도로 보지 않는다.

### `seoul_traffic_incident_request_audit`

- `request_id`/`source_id`는 `not_null`.
- 페이지 제어 정보 `start_index`, `end_index`, `list_total_count`, `row_count`는
  `not_null`.
- `raw_object_key`, `result_code`, `collected_at`, `dag_run_id`는 `not_null`.
- zero-row 응답은 이 audit 테이블이 기록해야 하며, Silver empty를 허용하는지 판단할 때
  직접 사용하지 않는다.

## Time contract

traffic 도메인은 `topis_timestamp`를 이용해 시간을 분리한다.

| 역할 | 컬럼 | 생성 규칙 |
|---|---|---|
| event time | `occurred_at` | `topis_timestamp(occr_date, occr_time)` |
| expected clear time | `expected_clear_at` | `topis_timestamp(exp_clr_date, exp_clr_time)` |
| ingest time | `collected_at` | DAG 수집 시각 |
| bucket time | `time_bucket` | `date_trunc('hour', occurred_at)` |

HHMM/HHMMSS 혼재 가능성을 고려해 실패/누락 파싱값은 실패 row로 분리하거나
필터링 대상에 넣는다.

## Silver grain and dedup

`silver_seoul_traffic_incident` grain은 아래 id 기반이다.

```text
acc_id
```

중복은 최신 값을 다음 우선순위로 선택한다.

```text
collected_at desc, raw_object_key desc, request_id desc
```

`result_code = 'INFO-000'`인 경우만 Silver 적재 대상.
`acc_id`가 null이거나 `occurred_at`이 null인 행은 제외한다.

`source_coordinate_system`은 고정 `GRS80_TM`으로 기록해 downstream 좌표 오해를 방지한다.

## Coverage and completeness

traffic는 request/page 단위의 수집 특성 때문에 단일 row 기반의 coverage가 오도될 수 있다.
`assert_traffic_audit_covers_latest_total_count`는 다음 지표를 함께 본다.

- `parsed_row_count = sum(row_count)`
- `list_total_count = max(list_total_count)`
- `max_end_index = max(end_index)`

정합성은 `latest dag_run_id` 기준으로
`parsed_row_count >= list_total_count`와 `max_end_index >= list_total_count`를
기본 합격 조건으로 둔다.

## Gold contract

`gold_traffic_incident_summary`는 source/time 요약 모델이다.

- `source_id`는 unique.
- `row_count`, `raw_object_count`, `source_coordinate_row_count`,
  `missing_source_coordinate_row_count`는 null 허용 불가.
- `first_occurred_at`, `last_occurred_at`, `last_collected_at`는 null 허용 불가.
- 좌표 존재율은 `source_location_quality`를 통해 추적한다.

## PR checklist

traffic dbt PR 본문에는 최소한 아래 항목을 남긴다.

- Source table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_seoul_traffic_incident`
- Audit table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_seoul_traffic_incident_request_audit`
- Target table: `iceberg_dev.traffic.silver_seoul_traffic_incident`
- Target table: `iceberg_dev.traffic.gold_traffic_incident_summary`
- Event time 컬럼: `occurred_at`
- Issued/예보시간 컬럼: 없음(incident 기준)
- Ingest time 컬럼: `collected_at`
- Dedup/grain 기준
- request-audit coverage test 실행 여부
- `dbt parse`, `dbt run`, `dbt test` 결과
- 타 도메인 모델 삭제/변경 diff가 없는지 확인

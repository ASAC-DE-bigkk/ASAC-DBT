# Traffic dbt contract guide

이 문서는 traffic 도메인 dbt PR에서 지켜야 할 source, time, grain,
coverage 계약을 정리한다. 시간/공간 공통축은 `asac_axes` package를 기준으로 한다.

## 적용 범위

- 도메인: `domains/traffic`
- 원천: Seoul TOPIS AccInfo
- Bronze source: `{{ source('traffic_bronze', 'seoul_traffic_incident') }}`
- Bronze request-audit source: `{{ source('traffic_bronze', 'seoul_traffic_incident_request_audit') }}`
- Bronze table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_seoul_traffic_incident`
- Bronze audit table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_seoul_traffic_incident_request_audit`
- Silver model: `silver_seoul_traffic_incident`
- Current Silver model: `silver_seoul_traffic_incident_current`
- Gold model: `gold_traffic_incident_summary`

## Source contract

`domains/traffic/models/sources.yml`은 아래 기준을 기본 계약으로 둔다.

### `seoul_traffic_incident`

- 공통 요청/수집 정보: `request_id`, `source_id`, `request_params_json`,
  `raw_object_key`, `payload_hash`, `http_status`, `result_code`, `result_msg`,
  `collected_at`, `load_date`, `dag_run_id`는 `not_null`.
- `source_id`는 `seoul_traffic_incident`로 고정 accepted_values.
- TOPIS 사건 id `acc_id`, 일시 `occr_date/occr_time`는 `not_null`.
- 위치계 관련 필드 `grs80tm_x`, `grs80tm_y`는 원천 좌표라 WGS84 위경도로 보지 않는다.

### `seoul_traffic_incident_request_audit`

- `request_id`/`source_id`는 `not_null`.
- 페이지 제어 정보 `start_index`, `end_index`, `list_total_count`, `row_count`는
  `not_null`.
- `request_params_json`, `raw_object_key`, `payload_hash`, `http_status`, `result_code`,
  `result_msg`, `collected_at`, `load_date`, `dag_run_id`는 `not_null`.
- zero-row 응답은 이 audit 테이블이 기록해야 하며, Silver empty를 허용하는지 판단할 때
  직접 사용하지 않는다.

## Time contract

traffic 도메인은 `asac_axes.kst_at_from_parts`를 이용해 시간을 분리한다.

| 역할 | 컬럼 | 생성 규칙 |
|---|---|---|
| source event time | `occurred_at` | `asac_axes.kst_at_from_parts(occr_date, occr_time)` |
| common event time | `event_at` | `occurred_at` alias for cross-domain joins |
| expected clear time | `expected_clear_at` | `asac_axes.kst_at_from_parts(exp_clr_date, exp_clr_time)` |
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
공통 공간축은 `asac_axes.tm_to_wgs84_relation('standardized', 'grs80tm_x', 'grs80tm_y')`
(레이어드 변형 — 인라인 `tm_to_wgs84`는 이 모델에서 표현식 폭발로 Trino
`QUERY_EXCEEDED_COMPILER_LIMIT`를 유발, 2026-07-07 장애)로 `longitude`/`latitude`를
만들고, `asac_axes.seoul_admin_dong_boundary`와 point-in-polygon 조인해
`admin_dong_code`, `gu_code`, `admin_dong`, `gu`를 노출한다. source 좌표가 없거나
서울 bbox guard 밖이거나 경계 단순화 때문에 매칭되지 않는 경우 행정동 축은 NULL일 수
있으며, coverage test로 비율을 감시한다.

Silver materialization은 `incremental` + `merge`를 사용한다. unique key는 output grain인
`source_record_id`(`acc_id`)이고, incremental run에서는 이미 반영된 `collected_at`의
최댓값에서 30분을 뺀 구간만 bronze에서 다시 읽는다. lookback 구간의 같은 사고 row를
다시 읽어도 ranked CTE가 최신 1건만 남기므로 merge 결과는 멱등이다. 테이블을 drop한 뒤
바로 재실행하면 R2/Data Catalog eventual consistency 때문에 `is_incremental()` 판단이
어긋날 수 있으므로, full refresh가 필요하면 `dbt run --full-refresh`를 우선 사용한다.

incremental tmp relation은 `views_enabled=false`로 **테이블**로 생성한다. R2 Data
Catalog가 `__dbt_tmp` 뷰 생성에 409 AlreadyExists(리스트/exists에는 안 보이는 유령
레코드)를 반환한 2026-07-07 장애의 재발을 차단하고, merge 소스를 물질화된 테이블
스캔으로 단순화하기 위함이다. `on_table_exists='drop'`은 population silver 선례를 따른다.

`silver_seoul_traffic_incident_current`는 transform DAG가
`traffic_snapshot_dag_run_id`로 고정한 complete publishable manifest run에 포함된 행만
남기는 current snapshot table이다. 기존 Silver는 재처리·이력 추적을 위한 incremental
latest-by-acc 상태를 유지하고, current snapshot과 Gold는 API에서 사라진 사고가 계속
노출되지 않도록 고정된 complete run을 기준으로 한다. `assert_silver_traffic_latest_publishable_record`
역시 history Silver와 같은 pinned run만 검증하며, transform이 소비하지 않은 5분 Bronze
중간 run을 watermark로 섞어 요구하지 않는다. 해당 원본 이력은 Bronze에 그대로 보존한다.

`assert_traffic_current_pinned_publishable_run`은 고정 run의 유효 Bronze `acc_id` 집합과
current `source_record_id` 집합을 양방향으로 비교하고, current의 모든 행이 같은 run을
가리키는지 확인한다. 고정 run이 publishable manifest에 없으면 실패하며, 유효 Bronze와
current가 모두 0행인 정상 zero-incident snapshot은 통과한다. 수집과 transform 사이의
스케줄 경합은 correctness anchor를 live latest로 바꾸지 않고 freshness만 별도로 판정한다.
고정 run이 최신 publishable 네 번째 이하일 때 current에 행이 있거나 더 최신 publishable
run에 유효 Bronze 행이 있으면 실패한다. 연속 zero-incident run만 새로 쌓인 경우에는
정상 zero snapshot을 stale로 처리하지 않는다.

## Snapshot recovery contract

과거 Bronze snapshot의 계약 위반을 재현·검증할 때는 canonical incremental Silver나
운영 Gold를 다시 빌드하지 않는다. recovery는 다음 세 table만 사용한다.

- `recovery_silver_seoul_traffic_incident`: `traffic_snapshot_dag_run_id`가 가리키는
  `SUCCESS + is_publishable` manifest run의 Bronze만 직접 읽어 같은 `acc_id` dedup 규칙을
  적용한다. 이 table은 incident row와 함께 `is_snapshot_marker=true`인 1개 marker row를 같은
  CTAS로 기록한다. marker는 incident가 아니므로 분석/Gold 집계에서는 반드시 제외한다.
  이 원자적 marker 덕분에 유효한 zero-incident snapshot도 실제로 Silver가 만든 run ID를 남긴다.
- `recovery_traffic_snapshot_metadata`: Silver marker만 읽는 완료 anchor다. Silver가 실패하거나
  중단되면 이후 요청 snapshot으로 advance하지 않으므로, stale empty Silver를 새 empty snapshot으로
  잘못 검증하지 않는다.
- `recovery_gold_traffic_incident_summary`: recovery Silver만 집계하고
  `snapshot_dag_run_id`를 결과에 남긴다.

입력 run이 없거나 publishable이 아니면 recovery Silver/metadata는 0행이 되고,
`assert_recovery_silver_traffic_snapshot_matches_bronze`가 `missing_pinned_run`으로 실패한다.
이 test는 요청 run, Silver marker에서 읽은 metadata, 선택된 Bronze incident record를 양방향 비교한다.

dev에서의 명시적 실행 순서는 다음과 같다. 이 경로는 recovery table만 갱신하며
`silver_seoul_traffic_incident`, `silver_seoul_traffic_incident_current`,
`gold_traffic_incident_summary`를 변경하지 않는다.

```bash
dbt run --select recovery_silver_seoul_traffic_incident \
  --vars '{"traffic_snapshot_dag_run_id": "<publishable-bronze-run-id>"}' \
  --target dev --no-partial-parse
dbt run --select recovery_traffic_snapshot_metadata \
  --vars '{"traffic_snapshot_dag_run_id": "<publishable-bronze-run-id>"}' \
  --target dev --no-partial-parse
dbt test --select recovery_traffic_snapshot_metadata recovery_silver_seoul_traffic_incident \
  assert_recovery_silver_traffic_snapshot_matches_bronze \
  --vars '{"traffic_snapshot_dag_run_id": "<publishable-bronze-run-id>"}' \
  --target dev --no-partial-parse
dbt run --select recovery_traffic_snapshot_metadata recovery_silver_seoul_traffic_incident \
  recovery_gold_traffic_incident_summary \
  --vars '{"traffic_snapshot_dag_run_id": "<publishable-bronze-run-id>"}' \
  --target dev --no-partial-parse
dbt test --select recovery_traffic_snapshot_metadata recovery_silver_seoul_traffic_incident \
  recovery_gold_traffic_incident_summary assert_recovery_gold_traffic_counts_match_silver \
  --vars '{"traffic_snapshot_dag_run_id": "<publishable-bronze-run-id>"}' \
  --target dev --no-partial-parse
```

recovery table은 운영 Current/Gold가 아니며, 해당 snapshot 조사와 수동 recovery의 작업
증적이다. 생성·보존 기간과 정리 실행은 후속 Airflow recovery DAG가 기록·관리한다.

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

`gold_traffic_incident_summary`는 current snapshot 기준 source/time 요약 모델이다.

- `source_id`는 unique.
- `row_count`, `raw_object_count`, `source_coordinate_row_count`,
  `missing_source_coordinate_row_count`는 null 허용 불가.
- `first_occurred_at`, `last_occurred_at`, `last_collected_at`는 정상 zero-incident
  snapshot에서는 null일 수 있다.
- 좌표 존재율은 `source_location_quality`를 통해 추적한다.
- 현재 Gold summary는 table materialization을 유지한다. Silver 전체를 읽어 source 단위
  1행으로 집계하는 작은 모델이라 incremental로 부분 집계하면 stale count 위험이 더 크다.

## PR checklist

traffic dbt PR 본문에는 최소한 아래 항목을 남긴다.

- Source table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_seoul_traffic_incident`
- Audit table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_seoul_traffic_incident_request_audit`
- Target table: `iceberg_dev.traffic.silver_seoul_traffic_incident`
- Target table: `iceberg_dev.traffic.silver_seoul_traffic_incident_current`
- Target table: `iceberg_dev.traffic.gold_traffic_incident_summary`
- Event time 컬럼: `occurred_at`
- Common event time 컬럼: `event_at`
- Issued/예보시간 컬럼: 없음(incident 기준)
- Ingest time 컬럼: `collected_at`
- Spatial axis 컬럼: `longitude`, `latitude`, `admin_dong_code`, `gu_code`
- Dedup/grain 기준
- Incremental unique key / lookback 기준
- request-audit coverage test 실행 여부
- `dbt parse`, `dbt run`, `dbt test` 결과
- 타 도메인 모델 삭제/변경 diff가 없는지 확인

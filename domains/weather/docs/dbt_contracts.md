# Weather dbt contract guide

이 문서는 weather 도메인 dbt PR에서 지켜야 할 source, time, grain,
coverage 계약을 정리한다. 공용 package를 바로 만들기보다, weather 도메인 안에서
현재 KMA 단기예보 모델의 검토 기준을 명확히 남기는 것이 목적이다.

## 적용 범위

- 도메인: `domains/weather`
- 원천: KMA `getVilageFcst`
- Bronze source: `{{ source('weather_bronze', 'kma_vilage_fcst') }}`
- Bronze table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_kma_vilage_fcst`
- Silver model: `silver_kma_vilage_fcst`
- Gold model: `gold_weather_forecast_summary`

## Source contract

`domains/weather/models/sources.yml`은 KMA Bronze table을 다음 기준으로 선언한다.

| 컬럼 | 의미 | 계약 |
|---|---|---|
| `request_id` | API 요청 단위 식별자 | `not_null` |
| `source_id` | 원천 식별자 | `not_null`, `kma_vilage_fcst` |
| `place_id` | 서울 격자/장소 식별자 | `not_null` |
| `base_date`, `base_time` | KMA 발표 기준 일자/시각 | `not_null` |
| `nx`, `ny` | KMA 격자 좌표 | Silver grain 및 coverage 기준 |
| `category` | 예보 항목 | `not_null` |
| `fcst_date`, `fcst_time` | 예보 대상 일자/시각 | `not_null` |
| `fcst_value` | 원천 예보 값 | `not_null` |
| `result_code` | KMA 응답 성공 코드 | `not_null`, 성공값 `00` |
| `raw_object_key` | R2 raw object lineage | `not_null` |
| `collected_at` | 수집 시각 | `not_null`, freshness 기준 |

Bronze DAG는 `total_count`가 실제 parsed item 수보다 큰 partial 응답을 성공으로
처리하지 않아야 한다. dbt는 성공적으로 publish된 Bronze table을 읽는다는 전제에서
Silver/Gold 품질 계약을 검증한다.

## Time contract

weather 도메인은 시간을 다음 역할로 분리한다.

| 역할 | 컬럼 | 생성 기준 |
|---|---|---|
| issued time | `issued_at` | `base_date + base_time` |
| forecast event time | `forecast_at` | `fcst_date + fcst_time` |
| ingest time | `collected_at` | DAG 수집 시각 |
| bucket time | `time_bucket` | `date_trunc('hour', forecast_at)` |

`issued_at`과 `forecast_at`은 domain-local macro인 `kma_timestamp`로 만든다.
KMA 날짜/시간 형식이 다른 도메인과 다르므로, 지금 단계에서는 공용 timestamp macro로
빼지 않는다.

## Silver grain and dedup

`silver_kma_vilage_fcst`의 grain은 아래 조합이다.

```text
place_id, nx, ny, base_date, base_time, category, fcst_date, fcst_time
```

Silver는 `result_code = '00'`인 row만 사용하고, `issued_at`과 `forecast_at`이
생성되지 않는 row는 제외한다. 중복 row는 아래 우선순위로 최신 1건을 선택한다.

```text
collected_at desc, raw_object_key desc, request_id desc
```

이 기준은 forecast 시계열의 각 발표/예보시각/항목별 최신 snapshot을 만들기 위한
계약이다. 발표 이력 전체를 보존하는 모델이 필요하면 별도 Silver 모델로 분리한다.

## Coverage and freshness

weather coverage는 "row가 존재하는지"가 아니라 "최신 발표시각에서 서울 격자 범위를
충분히 커버하는지"를 본다.

- test: `assert_silver_kma_vilage_fcst_grid_coverage`
- 기준: 최신 `issued_at`의 distinct `nx:ny` 수
- 기본 기대값: `ASK_SEOUL_REPORT_EXPECTED_KMA_GRIDS`, default `80`
- freshness 기준: `collected_at`
  - warn: 30 hours
  - error: 48 hours

이 테스트가 실패하면 최신 KMA 수집이 서울 전체 격자를 충분히 포함하지 못했거나,
Bronze publish 기준과 dbt 실행 시점 사이에 데이터가 비어 있는 상태로 봐야 한다.

## Gold contract

`gold_weather_forecast_summary`는 source-level 요약 모델이다.

- `source_id`는 unique 해야 한다.
- `row_count`, `raw_object_count`는 null이면 안 된다.
- `first_forecast_at`, `last_forecast_at`, `last_collected_at`은 null이면 안 된다.
- Gold에서 처음으로 raw 날짜/시간 파싱이나 dedup 기준을 만들지 않는다.

## PR checklist

weather dbt PR 본문에는 최소한 아래를 남긴다.

- Source table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_kma_vilage_fcst`
- Target table: `iceberg_dev.weather.silver_kma_vilage_fcst`
- Target table: `iceberg_dev.weather.gold_weather_forecast_summary`
- Event time 컬럼: `forecast_at`
- Issued time 컬럼: `issued_at`
- Ingest time 컬럼: `collected_at`
- Dedup/grain 기준
- Grid coverage test 실행 여부
- `dbt parse`, `dbt run`, `dbt test` 결과
- 다른 도메인 모델 삭제/변경 diff가 없는지 여부

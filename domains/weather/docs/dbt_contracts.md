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
- Place dimension: `dim_weather_place`
- User-facing forecast mart: `gold_weather_forecast_by_place`

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
| `payload_hash` | raw payload fingerprint | `not_null` |
| `request_params_json` | API key를 제외한 재현 가능한 요청 조건 | `not_null` |
| `http_status` | gateway HTTP status | `not_null` |
| `result_msg` | KMA 응답 메시지 | `not_null` |
| `total_count`, `item_count` | API total과 parsed item count | `not_null` |
| `collected_at` | 수집 시각 | `not_null`, freshness 기준 |
| `load_date`, `dag_run_id` | 적재 파티션 후보와 Airflow run lineage | `not_null` |

Bronze DAG는 `total_count`가 실제 parsed item 수보다 큰 partial 응답을 성공으로
처리하지 않아야 한다. dbt는 성공적으로 publish된 Bronze table을 읽는다는 전제에서
Silver/Gold 품질 계약을 검증한다.

## Time contract

weather 도메인은 시간을 다음 역할로 분리한다.

| 역할 | 컬럼 | 생성 기준 |
|---|---|---|
| issued time | `issued_at` | `base_date + base_time` |
| forecast event time | `forecast_at` | `fcst_date + fcst_time` |
| common event time | `event_at` | `forecast_at` alias for cross-domain joins |
| ingest time | `collected_at` | DAG 수집 시각 |
| bucket time | `time_bucket` | `date_trunc('hour', forecast_at)` |

`issued_at`과 `forecast_at`은 공용 package `asac_axes`의
`kst_at_from_parts`로 만든다. KMA 원천 컬럼(`base_date/base_time`,
`fcst_date/fcst_time`)은 보존하고, cross-domain 시간 조인은 `event_at`을 우선 사용한다.

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

## Place mapping contract

`weather_place_grid_mapping` seed는 KMA 격자 위경도 가이드의 서울특별시 행정동 row를
weather 도메인 안으로 고정한 장소-격자 계약이다.

| 컬럼 | 의미 | 계약 |
|---|---|---|
| `place_id` | weather mart에서 쓰는 표준 장소 식별자 | `seoul_admd_<행정구역코드>`, unique |
| `place_name` | 사용자에게 보여줄 기본 장소명 | 행정동명 |
| `alias_names` | 사용자 질의 alias 후보 | `|`로 구분한 문자열 |
| `gu`, `admin_dong` | 서울 자치구와 행정동 | `not_null` |
| `latitude`, `longitude` | KMA 가이드의 행정동 대표 위경도 | `not_null` |
| `nx`, `ny` | KMA 단기예보 격자 | `not_null`, Bronze 수집 grid 안에 있어야 함 |
| `mapping_method` | 매핑 출처/방식 | `kma_admin_dong_grid_20260325` |
| `grid_distance_m` | 실제 POI와 grid 대표점 거리 | 현재는 계산하지 않아 null 허용 |
| `source_admin_code` | KMA 가이드의 행정구역코드 | `not_null` |
| `admin_dong_code` | 행안부 10자리 canonical 행정동 코드 | `source_admin_code`와 동일 |
| `gu_code` | 행안부 5자리 canonical 자치구 코드 | `admin_dong_code` 앞 5자리 |

`dim_weather_place`는 이 seed를 타입 캐스팅한 weather 전용 place dimension이다. 공통
`dim_place`를 먼저 만들지 않고 weather 안에 둔 이유는, KMA 예보의 authoritative 단위가
장소명이 아니라 `nx`, `ny` 격자이기 때문이다. 다른 도메인과 결합할 공통 place 계약은
이 모델을 검증한 뒤 별도 공통 이슈에서 승격한다.

주요 hotspot alias는 행정동 row에 보강한다.

| alias | 표준 행정동 | 비고 |
|---|---|---|
| `홍대`, `홍대입구`, `홍대입구역` | 마포구 서교동 | 상권 질의 alias |
| `건대`, `건대입구`, `건대입구역` | 광진구 화양동 | 상권 질의 alias |
| `강남`, `강남역` | 강남구 역삼1동 | 역세권 질의 alias |
| `성수`, `성수동` | 성동구 성수1가제2동 | 상권 질의 alias |
| `여의도`, `여의도역` | 영등포구 여의동 | 업무/핫플레이스 질의 alias |
| `서울역` | 중구 회현동 | 역세권 질의 alias |
| `시청`, `서울시청`, `시청역` | 중구 소공동 | 공공/역세권 질의 alias |
| `종각`, `종각역` | 종로구 종로1.2.3.4가동 | 역세권 질의 alias |
| `용산`, `용산역` | 용산구 한강로동 | 역세권 질의 alias |
| `신촌`, `신촌역` | 서대문구 신촌동 | 상권 질의 alias |
| `가로수길` | 강남구 신사동 | 상권 질의 alias |
| `고속터미널`, `고속터미널역` | 서초구 반포4동 | 역세권 질의 alias |
| `DDP`, `동대문디자인플라자` | 중구 광희동 | 관광/핫플레이스 alias |
| `코엑스`, `삼성역` | 강남구 삼성1동 | 업무/핫플레이스 alias |

행정동명이 여러 구에서 충돌하는 경우가 있다. 현재 `신사동`은 관악구와 강남구에 모두
존재하므로 alias 중복 테스트의 허용 목록으로 관리하고, 상권 alias인 `가로수길`처럼
사용자 질의 의도가 더 좁은 이름은 별도 alias로 둔다.

서울시 실시간 도시데이터 121장소는 KMA forecast 대체재가 아니다. 해당 source를 쓰더라도
hotspot 현황이나 혼잡도 enrichment로 분리하고, weather forecast mart의 예보 값은 계속
KMA grid forecast에서만 온다.

## Gold contract

`gold_weather_forecast_summary`는 source-level 요약 모델이다.

- `source_id`는 unique 해야 한다.
- `row_count`, `raw_object_count`는 null이면 안 된다.
- `first_forecast_at`, `last_forecast_at`, `last_collected_at`은 null이면 안 된다.
- Gold에서 처음으로 raw 날짜/시간 파싱이나 dedup 기준을 만들지 않는다.

`gold_weather_forecast_by_place`는 사용자 질의용 최신 예보 mart다.

```text
place_id, forecast_at, category
```

위 조합이 mart grain이다. 같은 `place_id`, `forecast_at`, `category`에 여러 발표시각이
존재하면 아래 순서로 최신 1건을 선택한다.

```text
issued_at desc, collected_at desc, raw_object_key desc, request_id desc
```

이 mart는 `silver_kma_vilage_fcst`의 `nx`, `ny`를 `dim_weather_place`의 `nx`, `ny`와
조인한다. 따라서 한 KMA grid에 여러 행정동이 매핑될 수 있으며, 이는 KMA 격자 예보를
장소 질의로 펼치는 의도된 중복이다. Silver 원천 grain 자체는 바꾸지 않는다.

## PR checklist

weather dbt PR 본문에는 최소한 아래를 남긴다.

- Source table: `iceberg_dev.<ASK_SEOUL_SCHEMA>.bronze_kma_vilage_fcst`
- Target table: `iceberg_dev.weather.silver_kma_vilage_fcst`
- Target table: `iceberg_dev.weather.gold_weather_forecast_summary`
- Target table: `iceberg_dev.weather.dim_weather_place`
- Target table: `iceberg_dev.weather.gold_weather_forecast_by_place`
- Event time 컬럼: `forecast_at`
- Common event time 컬럼: `event_at`
- Issued time 컬럼: `issued_at`
- Ingest time 컬럼: `collected_at`
- Dedup/grain 기준
- Grid coverage test 실행 여부
- Place mapping seed row count와 주요 alias coverage test 실행 여부
- `dbt parse`, `dbt run`, `dbt test` 결과
- 다른 도메인 모델 삭제/변경 diff가 없는지 여부

# Weather freshness SLO 환경 계약 설계

## 목표

Weather dbt source freshness가 DAG reliability report와 같은 환경변수와 기본값을 해석하고, raw YAML이 아니라 dbt resolved manifest로 그 결과를 검증한다.

## 결정

- 기본값은 warn 240분, error 360분이다. 기존 4시간·6시간의 의미는 바꾸지 않고 minute 단위로 정규화한다.
- 환경변수는 `ASK_SEOUL_REPORT_WEATHER_FRESHNESS_WARN_MINUTES`와 `ASK_SEOUL_REPORT_WEATHER_FRESHNESS_ERROR_MINUTES`를 사용한다.
- source-level `weather_bronze.freshness`에만 적용한다. 모델 SQL, incremental lookback, repair, table grain은 변경하지 않는다.
- 테스트는 YAML 문자열 계약과 isolated project의 `dbt deps`·`dbt parse --no-partial-parse` 결과를 모두 확인한다. 로컬 dbt가 없으면 resolved-manifest 테스트는 skip하고 컨테이너 런타임에서 수행한다.

## 경계와 검증

- 변경 파일은 `domains/weather/**`에 한정한다.
- Traffic·다른 도메인의 코드, schema, table, raw object를 변경하지 않는다.
- `warn < error`를 기본과 override 모두에서 검증한다.
- dev에서 parse만 수행하며 `dbt run`, `--full-refresh`, prod write는 수행하지 않는다.

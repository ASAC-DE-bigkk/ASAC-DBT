# Weather 대표 Gold(W-A1) 물리 계약·의미 구조 완전 승격 pilot 설계

- 이슈: ASAC-DBT #312
- 브랜치: `feat/312-weather-current-wide-public-gold-contract`
- 대상 모델: `gold_weather_current_wide_by_admin_dong` (W-A1, `domains/traffic_weather/models/weather/transform/gold/`)

## 1. 배경

도메인별 dbt YAML 정적 비교에서 weather·traffic은 컬럼 설명(539/539)이 가장 강하지만 dbt 네이티브 model contract는 0개, exposure는 0개였다. Citydata·Commerce는 물리 타입·`contract.enforced`가 더 잘 적용되어 있고, Culture·Commerce는 exposures로 실제 소비자가 연결되어 있다. 결론은 "설명을 더 쓰는 것"이 아니라 "후보 Gold를 실제 서빙 제품으로 승격하는 절차"가 부족하다는 것이었다.

리포에는 이미 이 절차를 위한 자산이 갖춰져 있다.

- 계약 vocabulary: `domains/traffic_weather/contracts/weather/docs/public-gold-ai-contract-v1.md`
- 검증 엔진: `domains/traffic_weather/contracts/engine/`(schema lint → manifest validate → catalog compare 3단계, pytest 스위트 포함)
- 완성 예시: `gold_weather_forecast_by_admin_dong.yml` — v1 vocabulary의 7개 구조 key(`time`/`space`/`metrics`/`joins`/`quality`/`lineage`/`lifecycle`)를 전부 채운 유일한 모델. 단, 이 모델조차 `contract_status: dev_pending`이고 dbt 네이티브 `contract: {enforced: true}`는 없다 — 팀 전체가 아직 물리 계약을 건 모델이 하나도 없다는 뜻이다.

flagship 4개(T-A1/W-A1/T-X1/W-X4, DL-016 결정) 중 실제로 빌드되어 존재하는 건 W-A1뿐이다. 이 pilot은 W-A1을 첫 완전 승격 사례로 만들어 나머지 flagship·전체 24개 카탈로그에 반복 가능한 패턴을 남긴다.

## 2. 스코프

**포함**
1. `_gold.yml`의 `gold_weather_current_wide_by_admin_dong` 항목에 7개 구조 key + `primary_key`/`column_order`/컬럼별 `data_type`·`semantic_role`·`null_meaning` 완전 기입.
2. `dim_admin_dong` 직접 참조 재조정 테스트 3종 신설.
3. `config.contract: {enforced: true}` 네이티브 dbt 물리 계약 최초 적용.
4. `visibility`/`contract_status`/`exposure_status`를 실제 상태로 정직하게 명시.

**제외 (후속 이슈)**
- `api_route`/`product_id`/`sample_request`/`sample_response`/`license` 등 서빙 제품 필드 — 실제 API가 없는 상태에서 계약 vocabulary에 없는 필드를 임의로 추가하면 v1 문서의 "안전한 추론 경계" 원칙과 export safety 검사 대상이 아닌 즉흥 key가 생긴다. v1.1 확장은 별도 설계.
- 실제 dbt `exposures.yml` 등록 — 실 소비자가 없으므로 `exposure_status: none_no_live_consumer`를 명시하는 것 자체가 정직한 현재 상태 기록이다. 라이브 exposure를 미리 등록하지 않는다(v1 문서 4장 publication 원칙).
- 나머지 flagship 3개(T-A1/T-X1/W-X4) — 아직 미빌드, 별도 이슈.

## 3. 왜 `dim_admin_dong` 직접 참조가 필요한가

W-A1은 `gold_weather_forecast_by_admin_dong`(이미 `dim_admin_dong`과 조정 완료, stamp 보유)만 소비하고 `dim_admin_dong`을 직접 참조하지 않는다. 그런데 W-A1의 SQL은 `max(admin_dong) as admin_dong` 등 `group by admin_dong_code, forecast_at`로 pivot하면서 공간 stamp 컬럼(`admin_dong`/`gu_code`/`gu`/`admin_dong_revision_date`)을 재집계한다. v1 문서는 `space.enabled: true`에 "model의 직접 `dim_admin_dong` dependency"를 요구하는데, 이는 문서 형식만 맞추라는 게 아니라 — pivot 단계가 상위에서 이미 검증된 stamp를 실제로 훼손하지 않았는지 재검증하라는 뜻으로 해석한다.

따라서 소스 모델(`gold_weather_forecast_by_admin_dong`)의 3개 재조정 테스트 패턴(`admin_stamp_exact`/`admin_revision_exact`/`admin_join_reconciles`)을 W-A1에도 그대로 적용해, `dim_admin_dong`을 `ref()`하는 독립 테스트 노드로 pivot 후 stamp 정확성을 검증한다. SQL 모델 자체(`gold_weather_current_wide_by_admin_dong.sql`)는 변경하지 않는다 — 테스트만 추가한다.

## 4. `_gold.yml` 목표 형태 (요약)

`gold_weather_forecast_by_admin_dong.yml`과 동일한 구조를 따르되 W-A1의 실제 grain·컬럼에 맞춘다.

- `primary_key: [product_row_id]`, `column_order`: SQL `select` 순서 그대로 28개 컬럼(`product_row_id` … `published_at`)
- `time.roles`: `forecast_at`(event), `issued_at`(issue), `published_at`(publication) — W-A1에는 `collected_at`이 없으므로 소스 모델과 달리 3개 role만 선언
- `space`: 소스 모델과 동일한 `source_chain`(`iceberg_dev.common.bronze_admin_dong_master` → `asac_axes.dim_admin_dong`), `canonical_key: admin_dong_code`, `revision_field: admin_dong_revision_date`, `stamp_fields` 5종, 신규 `reconciliation_tests` 3개
- `joins.admin_dong_dimension`: 소스 모델 패턴 재사용, `reconciliation_test: assert_gold_weather_current_wide_by_admin_dong_admin_join_reconciles`
- `metrics`: `temp_c`/`humidity_pct`/`wind_ms`/`wind_dir_deg`/`precip_prob_pct`/`pcp_mm`/`pcp_lower_mm`/`pcp_upper_mm`/`sno_cm` 등 실제 수치 컬럼에 `unit`/`aggregation`/`zero_meaning`/`null_meaning` 선언 (소스 모델은 `metrics: {}`였으나 W-A1은 WIDE라 실제 metric 컬럼이 노출되므로 채운다)
- `quality.state_fields`: `pcp_representation`/`sno_representation`을 소스 모델의 `value_representation` 7-state taxonomy와 동일한 allowed_values로 선언 (구현 시 `weather_wide_pivot()` 매크로의 실제 값 도메인을 재확인)
- `lineage.source_relations`: `model.asac_seoul.gold_weather_forecast_by_admin_dong`, `model.asac_axes.dim_admin_dong`; identifiers 5-class는 소스 모델과 동일 컬럼 매핑(`raw_object_key`/`request_id`/`dag_run_id`는 W-A1 SQL에 없으므로 — 구현 시 실제 select list 재확인, 없으면 `relation_level_only: true`로 선언)
- `lifecycle.status: active`
- `visibility: published_producer`, `contract_status: dev_pending`, `exposure_status: none_no_live_consumer`

**구현 시 확인 필요 항목 (설계 시점 미확정)**:
- W-A1 SQL select list에 `raw_object_key`/`request_id`/`dag_run_id`/`source_id`가 없다 — lineage identifiers의 `raw`/`request`/`run` class를 `relation_level_only: true`로 선언할지, 아니면 소스에서 끌어와 컬럼을 추가할지는 컬럼 추가가 스코프 밖(SQL 불변 원칙)이므로 **relation_level_only로 선언**한다.
- `pcp_representation`/`sno_representation`의 실제 값 도메인은 `weather_wide_pivot()` 매크로 확인 후 확정.

## 5. 검증 계획

1. 로컬(도커 불필요): `contracts/engine`의 schema lint → manifest validate 단계와 `python -m pytest -q contracts/engine/tests`.
2. dev 스택(elt-infra-*, `docker exec elt-infra-airflow-scheduler-1 ... dbt build --select gold_weather_current_wide_by_admin_dong --target dev`)에서 `contract: enforced` 물리 빌드 성공 확인 — dbt는 선언된 `data_type`이 실제 relation과 다르면 빌드를 실패시키므로 이것이 물리 계약의 실제 증거다.
3. 신규 재조정 테스트 3종 PASS.
4. `contracts/engine/compare_public_gold_catalog.py`로 catalog.json과 선언 비교(가능하면).

## 6. 리스크

- `contract: enforced`를 걸었을 때 선언한 `data_type`이 Trino/Iceberg 실제 물리 타입과 다르면 빌드가 즉시 실패한다 — 이는 의도된 안전장치이며, 실패 시 실제 catalog 타입을 확인해 선언을 맞춘다(SQL을 임의로 캐스팅해 맞추지 않는다).
- 이 pilot은 "24개 중 1개"이므로 나머지 flagship 3개(T-A1/T-X1/W-X4)가 이번 승격 패턴을 그대로 따를 수 있는지는 실제로 빌드된 후에만 검증 가능하다 — 이번 PR 범위 밖.

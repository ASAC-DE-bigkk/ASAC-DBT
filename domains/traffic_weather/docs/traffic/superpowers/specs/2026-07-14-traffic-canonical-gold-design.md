# Traffic canonical current-hour Gold 설계

> 경로 주의(2026-07-15): 이 문서는 구현 당시 경로를 보존한 이력이다. 현재 dbt project root는 `domains/traffic_weather`이며 실행 가능한 최신 경로는 이 project의 `README.md`와 `docs/{traffic,weather}/dbt_contracts.md`를 따른다.

## 목적

최신 transform 시작 시 고정한 complete publishable Traffic snapshot을 사용자용
`admin_dong_code × hour_at` mart로 게시한다. 정상 zero-incident와 evidence 부재,
partial, API failure, current reconciliation 실패, 공간 mapping 실패를 구분하며,
`incident_count = 0`은 complete evidence가 있을 때만 허용한다.

## 기존 의도

- `6dfc0b44`, `2d725901`, `53b57f32`: correctness anchor는 live latest가 아니라
  `traffic_snapshot_dag_run_id`로 고정한 run이다. freshness는 별도 계약이다.
- `ede5d2b9`: current는 고정 snapshot에서 사라진 사고를 남기지 않고 정상 empty를 허용한다.
- `c0663ba2`: recovery relation과 marker는 운영 current/Gold와 격리한다.
- `b26cc63d`: freshness는 incident/request-audit가 아니라 manifest에만 적용한다.
- `b7b0fb46`, `eeaa6135`: TOPIS 좌표는 GRS80 TM이며 Silver에서 변환·boundary 후보를 만들지만,
  공개 행정동 명칭과 revision은 `asac_axes.dim_admin_dong`에서 다시 stamp해야 한다.

기존 `gold_traffic_incident_summary`와 recovery 모델은 수정하지 않는다.

## 검토한 대안

1. 사고가 있는 행정동만 sparse 집계: 가장 작지만 정상 zero와 missing을 구분하지 못한다.
2. snapshot status와 hourly mart를 별도 공개 relation으로 분리: row meaning은 명확하지만
   사용자가 항상 두 relation을 결합해야 한다.
3. canonical 행정동 scaffold에 nullable count와 명시적 quality state를 함께 둔다.

3번을 채택한다. 모든 행은 같은 시점에 평가한 행정동 cell이며, 증거가 불완전한 경우 count를
null로 두므로 0으로 오해할 수 없다.

## relation과 시간 의미

모델명은 `gold_traffic_incident_current_by_admin_dong_hourly`다. `current`를 이름에 넣어
발생시각별 history나 episode 집계로 오해하지 않게 한다.

- `status_observed_at`: 선택 run의 최신 manifest event를 KST로 변환한 시각. manifest가 없으면
  dbt 평가 시각을 사용한다.
- `hour_at`: `date_trunc('hour', status_observed_at)`인 제품 평가 bucket이다. `occurred_at`이나
  `collected_at`을 대신하지 않는다.
- `snapshot_as_of_at`: complete publishable evidence가 성립할 때만 채우는 snapshot 기준시각이다.
- `published_at`: relation을 계산한 dbt invocation의 KST 시각이다.

table materialization으로 최신 평가 hour만 게시한다. 과거 hourly 시계열은 이 모델의 계약이 아니다.

## 데이터 흐름

1. `traffic_snapshot_dag_run_id`에 해당하는 manifest의 최신 event를 선택한다.
2. 같은 run의 request-audit에서 HTTP/result code, reported total, parsed rows, page end를 집계한다.
3. 같은 run의 valid Bronze incident ID와 current Silver ID를 양방향 비교한다.
4. current의 `admin_dong_code`를 후보 key로만 사용해 `asac_axes.dim_admin_dong`에 exact join하고,
   이름·구·revision·centroid를 Silver에서 self-copy하지 않는다.
5. canonical 426개 행정동 scaffold에 mapped current count를 left join한다.
6. snapshot 전체 quality state가 complete일 때만 `coalesce(count, 0)`을 허용한다.

출력 핵심 컬럼은 `product_row_id`, `admin_dong_code`, `hour_at`, canonical five-field stamp,
`incident_count`, `has_incident`, `quality_state`, `snapshot_as_of_at`, `status_observed_at`,
`published_at`, `snapshot_dag_run_id`, `source_id`, audit/reconciliation evidence다.

## quality state

- `complete`: non-zero complete snapshot이며 current·canonical reconciliation이 모두 완료됨.
- `complete_zero`: complete snapshot의 reported/parsed/current incident가 모두 0임.
- `missing`: 선택 run의 manifest 또는 필수 request-audit evidence가 없음.
- `partial`: publishable/row/page completeness가 충족되지 않음.
- `api_failure`: audit의 HTTP 또는 TOPIS result code가 성공 기준을 충족하지 않음.
- `current_mismatch`: expected Bronze incident ID와 current Silver ID의 양방향 차이가 있음.
- `spatial_mapping_incomplete`: current incident 하나 이상이 canonical dim에 결합되지 않음.

`incident_count`와 `has_incident`는 `complete|complete_zero`에서만 non-null이다. complete snapshot의
개별 행정동 0은 유효하고, 나머지 상태의 0은 금지한다.

## 검증 설계

- Python RED/GREEN: pinned run, current ref, canonical dim ref, 상태 branch, 기존 summary/recovery 격리.
- dbt graph: 신규 singular test의 model dependency를 fresh manifest에서 검사.
- data tests: natural/surrogate grain, canonical stamp/revision, 행정동 scaffold completeness,
  expected↔target reconciliation, zero guard, fan-out 회귀.
- dev: 고유 `TRAFFIC_SCHEMA`, `threads=1`, 최신 publishable run 고정, deps/parse/compile/run/test,
  기존 summary 및 recovery 회귀, Trino final query.
- negative fixture: 격리 source/target schema에서 complete-zero, missing, partial, API failure를 각각
  실행해 zero/null/state를 확인한다.

## freshness와 범위 blocker

Issue #172의 Traffic-owned env/resolved-manifest 구현 `ee93147f`를 보존한다. 다만 dev의
`domains/weather/tests/test_source_freshness_slo.py`에 남은 Traffic raw-YAML assertion 제거는
`domains/weather/**` 수정 금지와 동시에 만족할 수 없다. 다른 도메인은 변경하지 않고 PR에
blocker로 기록한다.

## episode 결정

episode는 이번 범위에서 만들지 않는다. 현 Silver는 `acc_id`별 최신 행만 보존하므로 snapshot별
observation history, `acc_id` 재사용 분리, disappearance/return 규칙, 실제 `ended_at`이 없다.
`expected_clear_at`은 source 예상시각일 뿐 실제 종료가 아니므로 후속 observation/episode 계약이
승인되기 전에는 episode를 추론하지 않는다.

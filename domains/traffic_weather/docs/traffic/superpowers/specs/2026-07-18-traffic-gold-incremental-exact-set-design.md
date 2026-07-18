# Traffic Gold history incremental·current exact-set 분리 설계

- 상태: 사용자 검토 요청
- 기준 이슈: [ASAC-DBT #257](https://github.com/ASAC-DE-bigkk/ASAC-DBT/issues/257)
- 기준 branch: `feat/257-traffic-gold-incremental-exact-set`
- 사용자 선택: A — current exact-set 의미 유지, history 모델만 우선 증분화
- 대상 환경: dev

## 1. 결론

Traffic Gold 21개를 하나의 materialization 정책으로 다루지 않는다.

- Flow history 4개: affected-key incremental로 전환한다.
- Incident collection coverage 1개: history 후보이지만 mutable manifest change detection이 준비될 때까지 table로 보류한다.
- Incident current/exact 16개: 1차 hotfix에서 table replacement를 유지한다.

테스트 296개도 삭제하지 않는다. 매 transform의 publish gate 236개와 hourly/daily/deploy full assurance를 분리하고, 하루 한 번 전체 296개가 모두 실행되도록 한다.

## 2. 과거 대응 전략과 유지할 의도

GitHub와 git history에서 이미 반영된 전략은 이번 설계의 출발점이다.

### 2.1 ASAC-DBT #55 / PR #60

Traffic Silver는 append history를 매번 재생성하지 않고 incremental merge로 전환됐다.

- unique key: source native identity 기반
- late arrival 보호: `collected_at` 30분 lookback
- Gold summary는 당시 stale count를 피하기 위해 의도적으로 table 유지

즉 기존 결정은 “incremental은 항상 옳다”가 아니라 history와 current aggregate의 삭제 의미를 구분한 것이다.

### 2.2 PR #70

Trino/Iceberg incremental MERGE를 안정화하면서 다음 계약이 추가됐다.

- `views_enabled=false`
- `on_table_exists='drop'`
- 임시 view 대신 table 경로 사용
- compiled MERGE SQL을 약 73 KiB에서 9.6 KiB로 축소

이번 Flow incremental도 이 제약을 유지한다. dbt-trino 기본값만 믿고 `__dbt_tmp` view를 다시 만들지 않는다.

### 2.3 current snapshot disappearance

현재 snapshot에서 사라진 incident가 target에 stale row로 남지 않는 의미는 이후 issue #139와 current Silver/Gold 계약에서 더 강해졌다.

- `silver_seoul_traffic_incident_current`는 pinned publishable run의 정확한 집합이다.
- canonical Gold는 missing/extra current id를 양방향 비교한다.
- complete snapshot에서만 zero-fill하고 incomplete/mismatch는 null/quality state로 드러낸다.
- cross-domain Gold도 incident를 driving relation으로 보존한다.

plain incremental merge는 source에서 사라진 key를 삭제하지 못하므로 이 의미를 깨뜨린다. 사용자 선택 A에 따라 current 계열은 table replacement를 유지한다.

## 3. 현재 21개 Gold 분류

### 3.1 History incremental 1차 대상

| Model | Grain | 현재 source | 결정 |
| --- | --- | --- | --- |
| `gold_traffic_flow_link_latest` | `link_id` | Flow Silver history | incremental merge |
| `gold_traffic_flow_change_latest` | `link_id` | Flow Silver history | affected-link incremental |
| `gold_traffic_flow_congestion_hotspots_hourly` | `(hour_at, link_id)` | Flow Silver history | affected-hour incremental |
| `gold_traffic_flow_link_time_profile` | `(link_id, kst_day_of_week, kst_hour)` | Flow Silver history | affected-profile incremental |

Flow Silver는 이미 `(link_id, dag_run_id)` unique key와 30분 lookback을 가진 incremental ledger다. Gold는 이 ledger를 source of truth로 사용한다.

### 3.2 History이지만 2차 보류

`gold_traffic_incident_collection_coverage_5m`는 landed request-audit history를 집계하지만 단순 append 모델이 아니다.

- grain: `(source_id, coverage_window_at_utc)`
- schedule lattice가 아니라 실제 audit row가 있는 window만 존재
- latest effective manifest status와 publishability를 다시 결합
- resolver의 COALESCED event가 과거 window 상태를 바꿀 수 있음

audit의 `collected_at` watermark만 보면 과거 manifest 변경을 놓친다. manifest `event_at` 기반 dirty-window Change Interface가 없으므로 1차에서는 table을 유지한다.

### 3.3 Current/exact 16개

다음은 pinned current snapshot, current anchor 또는 exact current aggregate다.

- `gold_traffic_incident_active_latest`
- `gold_traffic_incident_clearance_horizon_latest`
- `gold_traffic_incident_clearance_watchlist`
- `gold_traffic_incident_current_by_admin_dong_hourly`
- `gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily`
- `gold_traffic_incident_spatial_mapping_quality_daily`
- `gold_traffic_incident_summary`
- `gold_traffic_incident_type_mix_latest`
- `gold_traffic_incident_x_citydata_crowding_current_hourly`
- `gold_traffic_incident_x_citydata_live_context_current`
- `gold_traffic_incident_x_commerce_business_exposure_current`
- `gold_traffic_incident_x_culture_activity_daily`
- `gold_traffic_incident_x_culture_event_schedule_daily`
- `gold_traffic_incident_x_flow`
- `gold_traffic_incident_x_transit_hourly`
- `gold_traffic_incident_x_weather_current_hourly`

이 모델들은 1차에서 `materialized='table'`을 유지한다. 이름의 `daily`/`hourly`는 grain이지 실행 cadence나 append history를 의미하지 않는다.

## 4. 공통 incremental Module

Flow 모델마다 changed-scope와 affected key SQL을 복사하지 않는다. Traffic Flow 전용 macro/ephemeral Module이 transform invocation의 pinned Flow run을 Change Interface로 사용한다.

```text
traffic_flow_changed_rows(traffic_flow_snapshot_dag_run_id)
traffic_flow_changed_links(traffic_flow_snapshot_dag_run_id)
traffic_flow_changed_hours(traffic_flow_snapshot_dag_run_id)
traffic_flow_changed_profile_keys(traffic_flow_snapshot_dag_run_id)
```

공통 계약은 다음과 같다.

- initial/full-refresh: 전체 Silver history
- incremental: Airflow resolver가 고정해 dbt var로 전달한 `traffic_flow_snapshot_dag_run_id`의 Silver rows
- source identity: `(link_id, dag_run_id)`
- empty/missing pinned run id는 기존 optional Flow 계약이며 incremental source를 empty로 만들어 target no-op
- non-empty pinned run id가 전달됐는데 대응 Silver changed rows가 없으면 fail closed
- nullable/duplicate affected key는 preflight 실패
- `views_enabled=false`, `on_table_exists='drop'`
- incremental source row가 비어 있으면 target을 변경하지 않는 no-op
- replay는 같은 pinned run id를 다시 계산해 멱등 수렴
- backfill은 대상 run id를 명시적으로 pin하며 latest live run을 자동 추측하지 않음

Silver의 기존 30분 `collected_at` lookback은 그대로 유지한다. Gold는 target에 없는 처리 watermark를 임의로 만들지 않고, 이미 resolver/Silver가 공유하는 pinned run identity를 재사용한다. 이를 통해 `observed_at`과 `collected_at`을 섞어 late arrival를 놓치는 오류를 피한다.

`SnapshotPair.flow_run_id=None`과 `dbt_snapshot_variables()`가 Flow var를 생략하는 기존 동작은 유지한다. Incident-only 또는 stale-Flow transform에서는 Silver Flow에 새 row가 들어오지 않으므로 Flow Gold 4개도 기존 target을 그대로 유지한다. target이 없는 initial/full-refresh는 var 유무와 관계없이 보존된 Silver history 전체에서 relation을 만든다. `gold_traffic_incident_x_flow`의 incident-driving left join과 `missing_flow` 의미도 바꾸지 않는다.

## 5. 모델별 설계

### 5.1 `gold_traffic_flow_link_latest`

#### 계약

- unique key: `link_id`
- 최신 순서: `observed_at`, `raw_object_key`, `request_id`
- target에서 link가 사라지는 current-snapshot 모델이 아니라 관측 history의 latest state

#### incremental path

1. pinned Flow run의 Silver rows에서 changed `link_id`와 candidate rows를 읽는다.
2. changed link의 기존 target row와 candidate rows를 union한다.
3. 기존 deterministic ordering으로 한 row를 선택한다.
4. `unique_key='link_id'` MERGE로 update/insert한다.

늦게 도착했지만 기존 latest보다 오래된 row는 target을 되돌리지 않는다. 더 최신이거나 tie-break에서 우선하는 row만 갱신한다.

### 5.2 `gold_traffic_flow_change_latest`

#### 계약

- unique key: `link_id`
- 각 link의 latest observation과 바로 이전 observation의 차이
- prior가 없으면 `no_prior_observation`

#### incremental path

1. pinned Flow run에서 changed link를 구한다.
2. changed link에 대해서만 Silver history를 다시 읽는다.
3. deterministic ordering으로 latest와 previous를 재계산한다.
4. link별 한 row만 MERGE한다.

late row가 기존 latest와 previous 사이에 들어오면 previous 값이 바뀔 수 있으므로 단순히 새 row와 target latest만 비교하지 않는다. 1차 구현은 correctness를 위해 changed link의 history를 재계산한다.

Flow snapshot이 매번 거의 모든 link를 touch해 이 query가 여전히 broad scan이 되면 canary 결과를 근거로 2-row state relation을 별도 설계한다. serving model에 숨은 mutable state를 임의로 추가하지 않는다.

### 5.3 `gold_traffic_flow_congestion_hotspots_hourly`

#### 계약

- unique key: `(hour_at, link_id)`
- hour별 각 link의 마지막 관측 1개
- 모든 관측 link를 게시하고, top 10 여부만 `hotspot_state`로 분류
- rank와 `observed_link_count`는 hour partition 전체에 의존

#### incremental path

1. pinned Flow run Silver의 KST `hour_at`을 affected hour로 구한다.
2. affected hour의 Silver rows 전체에서 link별 latest를 다시 고른다.
3. affected hour 전체의 rank/count를 다시 계산한다.
4. `(hour_at, link_id)` MERGE로 모든 affected rows를 갱신한다.

top 10 row만 target에 두는 모델이 아니므로 정상 append history에서는 순위 밖으로 밀린 row 삭제가 필요하지 않다. 향후 upstream correction/delete가 도입되면 affected-hour exact replacement가 필요하며, 그 전까지 deletion을 추측하지 않는다.

### 5.4 `gold_traffic_flow_link_time_profile`

#### 계약

- unique key: `(link_id, kst_day_of_week, kst_hour)`
- sparse cell 유지
- count/avg/min/max와 first/last 관측

#### incremental path

1. pinned Flow run Silver에서 affected profile key를 구한다.
2. 해당 key에 속하는 Silver history 전체를 다시 집계한다.
3. affected key만 MERGE한다.

평균을 target 평균과 새 평균만으로 합치는 구현은 overlap/replay에서 double count 위험이 있으므로 채택하지 않는다. 성능이 부족하면 source identity를 보존하는 중간 rollup ledger를 별도 설계한다.

## 6. Iceberg/dbt-trino 안전장치

- 모든 incremental model은 `views_enabled=false`를 유지한다.
- 기존 relation이 잘못된 table/view type이면 `on_table_exists='drop'` 계약을 유지한다.
- incremental temp source의 grain duplicate를 MERGE 전에 fail closed한다.
- single-key MERGE에서 과거 Citydata duplicate insert 사례가 있으므로 `link_latest`와 `change_latest`는 shadow에서 duplicate canary를 필수로 한다.
- relation을 drop한 직후 같은 invocation에서 `is_incremental()`을 신뢰하지 않는다.
- dev에서만 schema 격리 후 검증하며 prod catalog/schema를 쓰지 않는다.

Weather W2의 affected-key preflight와 single MERGE/delete-sentinel macro는 2차 current exact-set incremental의 precedent로만 사용한다. 1차 current model에 복사해 넣지 않는다.

## 7. selector와 테스트 cadence

### 7.1 실제 inventory

현재 scheduled Traffic transform이 선택하는 dbt test는 약 294개가 아니라 296개다.

| Phase | Count |
| --- | ---: |
| availability | 1 |
| Bronze source contract | 70 |
| `asac_axes` seed contract | 7 |
| `dim_admin_dong` | 3 |
| Silver | 42 |
| Gold | 173 |
| 합계 | 296 |

완료 run artifact 세 세트에서 모두 296 pass가 확인됐다.

### 7.2 cadence 결정

테스트를 지우거나 전부 nightly로 미루지 않는다. 가장 보수적인 분리는 다음과 같다.

| Tier / cadence | Count | 구성 |
| --- | ---: | --- |
| 모든 transform `GATE` | 236 | availability 1 + source 70 + Silver 42 + Gold fast 123 |
| KST hour의 첫 성공 시도 `HOURLY` | 256 | GATE + coverage 비-key 20 |
| KST day의 첫 성공 시도 `FULL` | 296 | 전체 portfolio: Gold 추가 30 + axes/admin 10 |

매-run Gold fast 123에는 다음 correctness gate를 남긴다.

- public canonical Gold grain/key
- current snapshot 양방향 reconciliation
- 426-dong scaffold와 zero/null guard
- pinned Citydata snapshot lineage
- Weather no-hindsight와 anchor preservation
- x_flow incident preservation
- coverage/clearance/spatial의 key, unique, accepted state, 핵심 singular reconciliation

Bronze source 70개는 history scan 비용이 있지만 현재 metadata contract gate다. selected Incident/Flow run만 동등하게 검사하는 row-scoped fast gate가 생기기 전에는 매-run에서 빼지 않는다.

Gold 123개의 count breakdown은 다음과 같이 고정하고 `dbt ls --resource-type test` artifact로 검증한다.

| Gold gate group | Count |
| --- | ---: |
| canonical public Gold | 25 |
| summary count gate | 8 |
| x_flow incident-preservation | 8 |
| pinned Citydata snapshot | 20 |
| Weather no-hindsight/anchor | 18 |
| 13개 serving relation key `not_null + unique` | 26 |
| coverage/clearance/spatial key·state·reconciliation | 18 |
| 합계 | 123 |

분류를 column 이름 추측에 맡기지 않는다. repo-tracked `contracts/traffic_gold_test_cadence.yml`을 test portfolio의 Canonical Inventory로 추가한다.

- 각 entry는 dbt manifest `unique_id`, test type(generic/singular), owner model, tier를 가진다.
- `gate` 123개, `hourly_extension` 20개, `daily_extension` 30개를 정확히 열거한다.
- axes 7개와 admin 3개는 `full_static`으로 별도 열거한다.
- 한 test는 정확히 한 최소 tier에 속한다. 상위 selector는 하위 tier의 union이다.
- premerge가 실제 manifest와 inventory의 missing/extra/duplicate를 양방향 비교한다.
- 새 Gold test가 추가됐는데 tier가 없으면 CI를 실패시키며 임의로 gate나 daily에 넣지 않는다.

최초 inventory는 현재 완료 run의 296-pass manifest에서 추출하고, 사람이 group 의미를 검토한 뒤 tracked file로 고정한다. 구현자가 위 count breakdown만 보고 123개를 임의 선택하지 않는다.

### 7.3 selector Interface

backward compatibility를 위해 기존 `ask_seoul_traffic_transform_gold`는 full selector로 유지한다. 다음 selector를 추가한다.

- `ask_seoul_traffic_transform_gold_models`
- `ask_seoul_traffic_transform_gold_gate_tests`
- `ask_seoul_traffic_transform_gold_hourly_tests`
- `ask_seoul_traffic_transform_gold_full_tests`

generic test는 `_gold.yml`과 serving Gold YAML의 개별 test `config.tags`에 tier tag를 부여한다. singular test는 SQL 상단 `config(tags=[...])`에 같은 tag를 둔다. selector는 `resource_type=test`, 기존 Traffic Gold tag, tier tag의 intersection으로 정의해 model node가 test selector에 섞이지 않게 한다.

- gate selector manifest count: 123
- hourly selector manifest count: 143, gate 123을 포함
- full selector manifest count: 173

CI/premerge는 full selector와 모든 named selector가 non-empty인지 확인하는 데 그치지 않고 위 exact count도 검증한다. Airflow의 같은 Traffic transform이 cadence tier에 맞는 selector를 사용한다. hourly/full assurance가 실패하면 명시적 task failure와 알림을 남기며 full test를 삭제한 것으로 취급하지 않는다.

hourly의 추가 20개는 materialized Gold의 비-key column contract지만 별도 test-only DAG를 만들지 않는다. FULL에는 source/current 양방향 reconciliation이 포함되므로 모든 tier를 현재 Traffic transform의 Gold build 직후 같은 pinned Incident/Flow/Citydata variables로 실행한다. Gold build→test 사이 Bronze write 금지 fence는 GATE/HOURLY/FULL에서 동일하다.

axes/admin 10개는 FULL tier에서만 기존 selector로 실행한다. GATE/HOURLY에서는 Airflow phase가 명시적 success no-op을 기록해 downstream dependency를 깨지 않는다. 첫 transform, ledger read 실패, KST day 첫 성공 시도는 FULL로 fail closed한다.

## 8. shadow parity canary

기존 table relation을 즉시 덮어쓰지 않는다.

### 8.1 준비

- 기존 table model: 기준 relation으로 계속 serving
- 신규 incremental model: 격리된 dev shadow schema 또는 `_shadow` alias
- 같은 pinned variables와 같은 Silver source 사용

### 8.2 검증 cycle

1. initial full build: old table과 shadow를 양방향 `EXCEPT`, row count, unique grain으로 비교
2. identical replay: 같은 input을 다시 실행하고 shadow가 수렴하는지 확인
3. normal new snapshot: affected key만 변경되고 parity가 유지되는지 확인
4. late arrival: 오래된 `observed_at`이지만 새로운 `collected_at` row로 latest/change/profile/hourly 의미 확인
5. duplicate/replay: 같은 `(link_id, dag_run_id)`가 결과를 중복시키지 않는지 확인
6. optional Flow: `flow_run_id=None`인 incremental invocation이 Flow Gold target을 변경하지 않고 incident/x_flow의 `missing_flow` 계약을 유지하는지 확인

최소 세 live cycle과 모든 fixture가 통과해야 serving relation을 incremental implementation으로 승격한다.

### 8.3 parity 판정

각 모델에서 다음이 모두 0이어야 한다.

- old `EXCEPT` shadow
- shadow `EXCEPT` old
- grain duplicate
- expected row count 차이

floating aggregate는 무조건 tolerance를 넓히지 않는다. 기존 `round(..., 2)` 이후 게시값을 비교한다.

## 9. rollback

- Flow model config를 `materialized='table'`로 되돌린다.
- 기존 full Gold selector로 dev relation을 재생성한다.
- current/exact 16개와 coverage table은 rollback 대상이 아니며 그대로 둔다.
- shadow relation은 검증 증거를 기록한 뒤 dev schema에서만 제거한다.
- prod relation drop/full-refresh는 별도 승인 없이는 실행하지 않는다.

selector cadence에 문제가 있으면 Airflow hot path를 기존 full selector로 되돌린다. 테스트 파일 자체는 삭제하지 않으므로 correctness gate를 즉시 복구할 수 있다.

## 10. 완료 조건

- Flow 4개가 명시적 grain과 affected-key incremental 계약을 가진다.
- current/exact 16개와 coverage 1개가 table replacement를 유지한다.
- 동일 입력 재실행이 중복 row를 만들지 않는다.
- normal, replay, late arrival에서 old/new 양방향 parity가 0이다.
- Gold run wall time과 Trino processed input이 기존 full rebuild 대비 감소한다.
- 매-run 236개, 첫 run/hour 256개, 첫 run/day 296개가 같은 pinned transform fence에서 실행된다.
- existing full selector와 CI/premerge contract가 유지된다.
- `views_enabled=false`, dev-only target, secret 비출력 계약을 유지한다.
- run id, model별 시간, affected key 수, row count, parity, table 영향을 `LessonRun.md`에 기록한다.

## 11. 후속 설계 후보

1차 canary 뒤에만 다음을 검토한다.

- manifest `event_at` Change Interface를 이용한 coverage affected-window incremental
- Weather W2식 delete-sentinel을 재사용한 current exact-set scoped reconciliation
- Flow latest/change를 위한 last-two state Module
- broad Bronze source 70개를 대체할 row-scoped fast contract gate
- Iceberg snapshot expiration/compaction과 metadata maintenance

## 12. 범위 밖

- current snapshot 의미 축소
- exact test tolerance 추가
- 21개 전체를 plain merge incremental로 변환
- production full-refresh/drop
- source retention 정책 변경
- Gold grain 또는 public column 의미 변경

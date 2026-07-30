# Weather/Traffic prod bootstrap 및 cross-domain source 정렬 설계

## 목적

ASAC-DAG의 prod runtime이 발행한 publishable Weather Bronze snapshot을
`iceberg.weather`의 W1/W2 canonical 모델로 최초 변환할 수 있게 한다. 동시에
Weather/Traffic이 Citydata를 읽는 물리 스키마를 환경별 계약에 맞추고, 현재 prod에
존재하는 Commerce Gold를 정규 Weather Gold 실행 범위에 복구한다.

## 변경하지 않을 경계

- `--full-refresh` 금지, incremental merge grain, snapshot pin, W2 repair evidence 검증은 유지한다.
- Weather W1 candidate/seed도 canonical prod와 pinned snapshot 조합에서만 추가 허용한다.
- Citydata·Culture·Transit·Commerce 코드와 테이블은 수정하거나 실행하지 않는다.
- prod 최초 생성은 `iceberg.weather`와 `iceberg.weather_traffic_bronze`의 canonical 조합에만 허용한다.
- 비밀값과 `.env*`는 코드·문서·테스트에 넣지 않는다.

## 현재 문제

`weather_w1_initial_build_guard()`는 최초 relation 생성 시 isolated
`iceberg_dev` smoke 또는 bounded DEV repair만 허용한다. 정상 prod DAG는
publishable Bronze asset에서 `weather_snapshot_dag_run_id`를 검증·고정해 dbt에
전달하지만, 가드가 prod 경로를 표현하지 않아 최초 W1 생성이 compile 단계에서 막힌다.

Weather/Traffic의 Citydata source는 기본값이 `seoul_citydata`로 고정돼 있다.
Citydata의 현재 물리 계약은 dev=`iceberg_dev.seoul_citydata`,
prod=`iceberg.citydata`이므로 prod에서 존재하지 않는 스키마를 조회한다.

정규 Weather transform은 Commerce Gold가 없던 시점의 임시 selector를 계속 사용한다.
현재 `iceberg.commerce.gold_license_dong_summary`가 존재하므로 임시 제외 사유가
해소됐다.

## 설계

### W1 prod 최초 생성

기존 isolated smoke와 bounded DEV repair 허용은 그대로 둔다. W1 observation/grid,
static bridge seed와 bridge model에 다음 조건을 모두 만족하는
`prod_snapshot_bootstrap` 경로를 공통으로 추가한다.

- `target.name == 'prod'`
- `target.database == 'iceberg'`
- `ASK_SEOUL_SCHEMA == 'weather_traffic_bronze'`
- `WEATHER_SCHEMA == 'weather'`
- `weather_snapshot_dag_run_id`가 비어 있지 않음

정상 DAG는 Bronze asset metadata를 검사하고 manifest의 publishability를 확인한 뒤
해당 변수를 전달한다. 따라서 별도 운영 플래그를 남기지 않고 최초 생성과 이후
incremental 실행이 같은 asset-triggered 경로를 사용한다. `--full-refresh`는 계속
즉시 실패한다.

prod의 static bridge가 없는 최초 1회에는 정규 W2 DAG를 열기 전에 동일한 pinned
snapshot 변수를 사용해 `ask_seoul_weather_w1_inputs` seed,
`ask_seoul_weather_transform_common_admin` model,
`ask_seoul_weather_w1_bridge` model/test를 순서대로 실행한다. 정규 W2 DAG는 이
정적 자산을 매 snapshot마다 재작성하지 않고 기존 소유 경계를 유지한다.

### Citydata source 해석

Weather와 Traffic source YAML 모두 다음 기본값을 사용한다.

```jinja
{{ env_var('SEOUL_CITYDATA_SCHEMA', 'citydata' if target.name == 'prod' else 'seoul_citydata') }}
```

논리 source와 테이블 계약은 유지하고 물리 스키마만 target에 따라 선택한다.
`SEOUL_CITYDATA_SCHEMA` override도 유지해 격리 검증을 지원한다.

### Weather Gold 범위

Airflow Weather transform의 Gold run/test selector를
`ask_seoul_weather_transform_gold`로 복구한다. 다른 도메인을 쓰지 않고, Weather
소유 cross-domain leaf가 published source를 읽어 `weather` 스키마에 쓰는 구조다.
임시 `without_commerce` selector 정의는 현재 소비자가 없어 제거한다.

## 실패 처리

- prod canonical 조합이나 snapshot pin이 하나라도 다르면 기존 compiler error로 차단한다.
- Citydata relation이 없으면 dbt source/model 실행이 명시적으로 실패한다.
- cross-domain 계약 실패를 성공으로 삼키지 않는다.
- prod canary 전 모든 Weather/Traffic DAG를 pause 상태로 유지하고 OOM을 모니터링한다.

## 완료 검증

- 새 prod bootstrap 계약 테스트가 변경 전 실패하고 변경 후 통과한다.
- pinned prod snapshot으로 W1 seed/bridge compile이 성공하고 snapshot 미제공 시 실패한다.
- Weather/Traffic Citydata source 테스트가 환경별 기본값을 검증한다.
- Weather DAG 테스트가 전체 Gold selector 사용을 검증한다.
- 관련 Python test, `dbt parse`, selector `dbt ls`, Python compile, `git diff --check`가 통과한다.
- 실제 prod canary는 커밋된 feature revision 배포 후 safe-trigger/asset 순서로 별도 수행한다.

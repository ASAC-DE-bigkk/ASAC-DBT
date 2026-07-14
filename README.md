# ASK Seoul Traffic/Weather monoproject

이 root는 Traffic과 Weather를 하나의 dbt graph로 해석하는 실행 진입점이다. 모델 의미나
phase 목록을 이 문서에 복제하지 않고, 아래 source of truth부터 읽는다.

## 시작 파일

- graph/path/group 설정: [`dbt_project.yml`](dbt_project.yml)
- Airflow가 사용하는 named selector: [`selectors.yml`](selectors.yml)
- Traffic 모델·tag index: [`models/traffic/README.md`](models/traffic/README.md)
- Weather 모델·tag index: [`models/weather/README.md`](models/weather/README.md)
- public Gold 계약 CLI: [`contracts/engine/README.md`](contracts/engine/README.md)

## Named selectors

각 selector는 같은 이름의 tag를 감싸므로 새 tagged resource는 DAG 코드나 Python registry를
수정하지 않아도 해당 phase에 포함된다. contract gate만 source tag와 generic test 유형의
교집합이다.

| Domain | Selector | 책임 |
| --- | --- | --- |
| Traffic | `ask_seoul_traffic_transform_source` | Bronze source 계약 리소스 |
| Traffic | `ask_seoul_traffic_transform_availability` | source availability singular test |
| Traffic | `ask_seoul_traffic_transform_asac_axes` | 공통축 seed |
| Traffic | `ask_seoul_traffic_transform_asac_axes_contract` | 공통축 seed 계약 |
| Traffic | `ask_seoul_traffic_transform_common_admin` | canonical 행정동 model |
| Traffic | `ask_seoul_traffic_transform_silver` | scheduled Silver model/test |
| Traffic | `ask_seoul_traffic_transform_gold` | scheduled Gold model/test |
| Traffic | `ask_seoul_traffic_recovery_silver` | recovery Silver |
| Traffic | `ask_seoul_traffic_recovery_metadata` | recovery metadata anchor |
| Traffic | `ask_seoul_traffic_recovery_gold` | recovery Gold |
| Traffic | `traffic_transform_contract_gate` | Bronze source generic tests |
| Weather | `ask_seoul_weather_transform_source` | Bronze source 계약 리소스 |
| Weather | `ask_seoul_weather_transform_asac_axes` | 공통축 seed |
| Weather | `ask_seoul_weather_transform_common_admin` | canonical 행정동 model |
| Weather | `ask_seoul_weather_transform_place_mapping` | place mapping seed |
| Weather | `ask_seoul_weather_transform_silver` | scheduled Silver model/test |
| Weather | `ask_seoul_weather_transform_gold` | scheduled Gold model/test |
| Weather | `ask_seoul_weather_transform_place_mart` | place mart model/test |
| Weather | `ask_seoul_weather_w1_inputs` | W1 bridge input seeds |
| Weather | `ask_seoul_weather_w1_bridge` | W1 bridge model/test |
| Weather | `weather_transform_contract_gate` | Bronze source generic tests |

## Graph 경계

- [`packages/asac_axes`](packages/asac_axes)는 `packages.yml`의 local package이며 공용
  행정축 resource를 이 graph에 제공한다.
- cross-domain 소비는 producer가 `access: public`일 때만 package-qualified
  `{{ ref('asac_seoul', '<public_model>') }}`를 사용한다. 다른 domain의 Silver나
  내부 Gold를 참조하지 않는다.
- Airflow DAG는 모델 이름 목록이나 파일 경로를 복제하지 않고 root의 `tags/selectors`만
  호출한다. phase membership은 `dbt_project.yml`의 폴더 설정이 소유한다.
- `domains/` 아래 다른 domain 디렉터리는 이 graph의 model/seed/test/macro path에 포함되지
  않는다. 현재 root graph의 도메인 resource는 `models/traffic`과 `models/weather`뿐이다.

## Read-only graph 확인

fresh target을 사용하고 Traffic recovery var를 항상 명시한다.

```bash
dbt deps --project-dir . --profiles-dir .
dbt parse --project-dir . --profiles-dir . --target dev --no-partial-parse \
  --target-path target/contract-parse \
  --vars '{"traffic_snapshot_dag_run_id":"contract-parse"}'
```

실제 dev run/test에는 synthetic 값 대신 publishable Bronze DAG run id를 사용한다.

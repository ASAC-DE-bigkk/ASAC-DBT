# ASK Seoul Traffic/Weather monoproject

Traffic와 Weather를 하나의 dbt project, manifest, `ref()` graph로 관리하는 도메인
Module이다. 저장소의 다른 도메인은 이 project에 포함하지 않는다.

## AI가 읽는 순서

1. graph와 folder ownership: [`dbt_project.yml`](dbt_project.yml)
2. Airflow 실행 Interface: [`selectors.yml`](selectors.yml)
3. CI 실행 Module: [`workflows/premerge_gate.py`](workflows/premerge_gate.py)
4. Traffic 모델 index: [`models/traffic/README.md`](models/traffic/README.md)
5. Weather 모델 index: [`models/weather/README.md`](models/weather/README.md)
6. 공통 계약 engine: [`contracts/engine/README.md`](contracts/engine/README.md)
7. 도메인 운영 계약: [`docs/traffic/dbt_contracts.md`](docs/traffic/dbt_contracts.md),
   [`docs/weather/dbt_contracts.md`](docs/weather/dbt_contracts.md)

## 소유 경계

- `domains/traffic_weather`가 이 dbt project의 유일한 root다.
- [`../../packages/asac_axes`](../../packages/asac_axes)는 저장소 공용 local package다.
- `.github/workflows/traffic-weather-monoproject-premerge-gate.yml`만 GitHub discovery를
  위해 저장소 root에 남는 CI adapter다.
- `domains/citydata`, `commerce`, `culture`, `transit`의 파일은 이 project가 소유하거나
  탐색하지 않는다.

```text
domains/traffic_weather/
├── dbt_project.yml, profiles.yml, packages.yml, selectors.yml
├── models/{traffic,weather}
├── tests/{traffic,weather}
├── macros, seeds, analyses
├── contracts/{engine,traffic,weather}
├── workflows
└── docs/{traffic,weather,superpowers}
```

## 실행 Interface

Airflow는 raw tag, model 이름, 파일 경로를 넘기지 않고 `selectors.yml`의 named
selector만 호출한다. phase membership은 `dbt_project.yml`의 folder `tags/selectors`가
소유하므로 tagged resource를 추가해도 DAG 변경이 필요 없다.

cross-domain 소비는 producer가 `access: public`일 때만 package-qualified
`{{ ref('asac_seoul', '<public_model>') }}`를 사용한다. 다른 domain의 Silver나 내부
Gold는 직접 참조하지 않는다.

## Read-only graph 확인

아래 명령은 이 디렉터리에서 실행한다. Traffic recovery parse에는
`traffic_snapshot_dag_run_id`를 명시한다.

```bash
dbt deps --project-dir . --profiles-dir .
dbt parse --project-dir . --profiles-dir . --target dev --no-partial-parse \
  --target-path target/contract-parse \
  --vars '{"traffic_snapshot_dag_run_id":"contract-parse"}'
```

실제 dev run/test에는 synthetic 값 대신 publishable Bronze DAG run id를 사용한다.

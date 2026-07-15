# Traffic·Weather 클린 아키텍처 구현 기록

> 상태: feature branch 구현과 로컬 계약 검증을 완료했다. 이 문서는 ASAC-DBT #189,
> ASAC-DAG #358, ASK-Seoul #25의 설계·구현 이력을 보존하며, 실행 중인 체크리스트로
> 사용하지 않는다. dev 데이터 실행, 세 저장소 PR 통합, 재배포는 아직 남아 있다.

이 작업은 `Traffic`과 `Weather` 소유 파일, 두 도메인이 공유하는 dbt graph/계약만
변경한다. 다른 도메인의 파일과 실행 의미는 변경하지 않는다. 별도 표기가 없는 경로는
`domains/traffic_weather/` 기준이다.

## 최종 구조

```text
ASAC-DBT/
├── .github/workflows/          # GitHub discovery adapter
├── packages/asac_axes/         # 저장소 공용 package
└── domains/
    ├── traffic_weather/        # Traffic·Weather 단일 dbt project
    │   ├── analyses/
    │   ├── contracts/{engine,traffic,weather}/
    │   ├── docs/{traffic,weather,superpowers}/
    │   ├── macros/
    │   │   ├── generate_schema_name.sql
    │   │   └── weather/
    │   ├── models/
    │   │   ├── groups.yml
    │   │   ├── traffic/
    │   │   └── weather/
    │   ├── seeds/weather/
    │   ├── tests/{traffic,weather}/
    │   ├── workflows/          # domain-owned pre-merge Module
    │   ├── dbt_project.yml
    │   ├── profiles.yml
    │   ├── packages.yml
    │   ├── package-lock.yml
    │   ├── selectors.yml
    │   └── pytest.ini
    └── <other>/                # 무변경
```

외부 interface는 다음 네 가지다.

1. project directory에서 실행하는 `python -m contracts.engine.<command>`:
   schema/manifest/catalog 계약 검증
2. `dbt <run|test|ls> --project-dir domains/traffic_weather --selector <name>`:
   phase membership
3. `ref()`와 `group/access`: logical lineage와 공개 model interface
4. invocation별 `target-path`의 `manifest.json`, `run_results.json`: 실행 증거

## 1. 공통 계약 engine — 구현 완료

최종 구현은 다음 책임으로 나뉜다.

- `contracts/engine/**`: 두 도메인이 공유하는 schema/manifest/catalog 계약 구현과 테스트
- `contracts/{traffic,weather}/docs/**`: 도메인별 공개 Gold 계약
- `contracts/traffic/scripts/validate_singular_test_dependency_manifest.py`: Traffic에만
  필요한 singular dependency policy
- `workflows/premerge_gate.py`: scope, `dbt deps`, fresh parse, 모든 named selector의
  non-empty 검증, Python 계약 테스트를 순서대로 소유하는 단일 pre-merge Module
- `.github/workflows/traffic-weather-monoproject-premerge-gate.yml`: 위 Module을 발견하고
  호출하는 저장소 root adapter

초기 계획에 있던 Traffic 전용
`run_traffic_manifest_premerge_gate.py`는 최종 구조에서 유지하지 않았다. 공통 실행 순서는
`workflows/premerge_gate.py`로 통합했고 Traffic 전용 singular validator만 남겼다. 두 도메인에
복제되어 있던 engine 구현과 `test_validate_public_gold_manifest.py`도
`contracts/engine/`의 단일 구현·테스트 surface로 통합했다.

project directory 기준 검증 명령은 다음과 같다.

```powershell
python -m pytest contracts/engine/tests contracts/traffic/tests workflows/tests -q -p no:cacheprovider
python -m compileall -q contracts workflows
```

## 2. Traffic·Weather 단일 dbt graph — 구현 완료

아래는 구현 당시의 이동 기록이다. 화살표 양쪽은 모두 저장소 root 기준 경로다.

- `domains/traffic/models/**` → `domains/traffic_weather/models/traffic/**`
- `domains/weather/models/**` → `domains/traffic_weather/models/weather/**`
- `domains/traffic/tests/**` → `domains/traffic_weather/tests/traffic/**`
- `domains/weather/tests/**` → `domains/traffic_weather/tests/weather/**`
- `domains/weather/macros/**` → `domains/traffic_weather/macros/weather/**`
- `domains/weather/seeds/**` → `domains/traffic_weather/seeds/weather/**`
- 두 도메인의 계약과 문서 → `domains/traffic_weather/contracts/{traffic,weather}/`와
  `domains/traffic_weather/docs/{traffic,weather}/`

최종 graph에는 다음 결정을 반영했다.

- project/profile 이름은 `asac_seoul`로 고정한다.
- `generate_schema_name.sql`은 `asac_axes`, Traffic, Weather, control relation을 각각
  소유 schema로 보낸다.
- `static_parser: false`와 certificate validation은 domain-owned project가 소유한다.
- `asac_axes`는 `ASAC_AXES_SCHEMA`의 canonical relation으로 공유한다.
- 기존 resource 이름은 유지하고 dependency 판정은 manifest의 project metadata와
  `ref()`를 사용한다.
- 다른 `domains/*` project는 이동하거나 수정하지 않는다.

저장소 root 기준 로컬 검증 명령은 다음과 같다.

```powershell
dbt deps --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather
dbt parse --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather `
  --target dev --no-partial-parse --target-path target/contract-parse
dbt ls --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather `
  --selector ask_seoul_traffic_transform_silver --output json
dbt ls --project-dir domains/traffic_weather --profiles-dir domains/traffic_weather `
  --selector ask_seoul_weather_transform_silver --output json
```

## 3. named selector가 phase membership을 소유 — 구현 완료

- 각 scheduled model은 정확히 하나의 phase tag를 가진다.
- phase tag의 model membership은 서로 겹치지 않는다.
- DAG-owned singular test는 실행 phase tag를 직접 가진다.
- Airflow는 raw tag, model 이름, test 이름, 파일 경로가 아니라 named selector만 호출한다.
- Weather W1/W2 전용 model은 normal transform phase에 포함되지 않는다.
- Traffic source/axes exact gate membership은 DAG literal이 아니라 manifest policy가
  검증한다.

이 계약은 실제 소유 테스트인 `contracts/engine/tests/test_monoproject_architecture.py`와
`workflows/tests/test_premerge_gate.py`에서 검증한다.

## 4. schema YAML 분할 — 구현 완료

과거의 `domains/traffic/models/schema.yml`과 `domains/weather/models/schema.yml`은 다음
원칙에 따라 project 내부의 작은 파일로 분할했다.

- domain별 source는 `models/{traffic,weather}/sources.yml`이 소유한다.
- 공개 Gold model은 SQL 옆의 `<model>.yml`이 전체 interface를 설명한다.
- 작은 model family는 `_silver.yml`, `_gold.yml`, `_recovery.yml`처럼 응집된 파일이
  소유한다.
- model 선언은 정확히 한 YAML에만 존재하며 YAML anchor/alias는 사용하지 않는다.
- 각 domain README가 source, selector, published interface, 핵심 invariant를 연결한다.

## 5. DAG와 manifest handoff — interface 구현 완료, 통합 대기

ASAC-DAG #358의 Traffic·Weather adapter는 model/test 이름을 전달하지 않고 phase selector와
invocation identity만 전달한다.

```text
dag_id + run_id + task_id + try_number
        ↓
invocation target/log path
        ↓
dbt ls non-empty preflight
        ↓
dbt run 또는 dbt test
        ↓
manifest/run_results 검증 및 선택적 dbt-ol emission
```

Weather와 Traffic은 서로 import하지 않는다. 각 domain adapter가 같은 invocation
interface를 구현하고, 공통 membership과 lineage는 dbt graph가 소유한다. 이 interface의
feature branch 구현은 끝났지만 세 저장소 PR 통합과 Airflow 재배포는 별도 단계다.

## 6. 검증 상태와 남은 작업

완료한 로컬 검증:

- 다른 domain 경로가 변경되지 않았는지 diff scope 검사
- `dbt deps`와 fresh `dbt parse`
- 선언된 named selector 25개의 non-empty 결과
- fresh manifest를 사용하는 Python 계약 테스트: 199 passed, 13 skipped
- Windows에서 symlink capability가 없는 경우 해당 capability test만 skip

통합 전 남은 검증:

- dev schema에서 phase별 `run`/`test` 실행
- 기존 relation 이름과 row count 비교
- 같은 snapshot/run 재실행을 통한 idempotency 확인
- DBT → DAG → ASK-Seoul 순서의 PR CI와 최종 smoke flow 확인

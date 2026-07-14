# Traffic·Weather 클린 아키텍처 구현 계획

> 이 계획은 ASAC-DBT #189, ASAC-DAG #358, ASK-Seoul #25를 함께 구현한다. 현재 작업에서는 `Traffic`과 `Weather` 소유 파일, 그리고 두 도메인의 공통 dbt graph/계약 파일만 변경한다. 다른 도메인의 파일과 실행 의미는 변경하지 않는다.

## 목표 구조

```text
ASAC-DBT/
├── dbt_project.yml
├── profiles.yml
├── packages.yml
├── selectors.yml
├── contracts/
│   └── engine/                 # 한 번 구현하고 두 도메인이 호출하는 계약 Module
├── macros/
│   ├── generate_schema_name.sql
│   └── weather/
├── models/
│   ├── groups.yml
│   ├── traffic/
│   └── weather/
├── seeds/weather/
├── tests/traffic/
├── tests/weather/
└── domains/<other>/            # 무변경
```

외부 interface는 다음 네 가지뿐이다.

1. `python -m contracts.engine.<command>`: schema/manifest/catalog 계약 검증
2. `dbt --project-dir <repo-root> --selector <name>`: phase membership
3. `ref()`와 `group/access`: logical lineage와 공개 model interface
4. invocation별 `target-path`의 `manifest.json`, `run_results.json`: 실행 증거

## Task 1: 공통 계약 engine

**Files**

- Create/Move: `contracts/engine/**`
- Modify/Delete: `domains/traffic/contracts/scripts/{artifact_io,lint_schema_contract_source,validate_public_gold_manifest,compare_public_gold_catalog}.py`
- Modify/Delete: `domains/weather/contracts/scripts/{artifact_io,lint_schema_contract_source,validate_public_gold_manifest,compare_public_gold_catalog}.py`
- Move: 두 도메인의 중복 `test_validate_public_gold_manifest.py`를 `contracts/engine/tests/`의 단일 test surface로 통합
- Keep: Traffic 전용 manifest pre-merge runner와 singular dependency policy
- Modify: Traffic/Weather 계약 문서와 `.github/workflows/traffic-weather-monoproject-premerge-gate.yml`

**TDD**

1. 공통 module import, 두 도메인 manifest 수용, Windows symlink capability skip을 검증하는 테스트를 먼저 추가한다.
2. 새 테스트가 module 부재 또는 capability 처리 부재로 실패하는 것을 확인한다.
3. Weather 구현의 `approved_revision_date`와 production-size JSON limit을 canonical implementation으로 이동한다.
4. Traffic `space` metadata를 같은 interface에 맞춘다.
5. 도메인 복제 implementation과 복제 tests를 삭제한다.
6. Linux에서는 symlink 안전성 테스트가 실행되고, 권한 없는 Windows에서는 해당 테스트만 skip되는지 확인한다.

**Verify**

```powershell
python -m pytest contracts/engine/tests domains/traffic/contracts/tests -q -p no:cacheprovider
python -m compileall -q contracts/engine domains/traffic/contracts
```

## Task 2: Traffic/Weather 단일 dbt graph

**Files**

- Create: `dbt_project.yml`, `profiles.yml`, `packages.yml`, `selectors.yml`
- Create: `macros/generate_schema_name.sql`, `models/groups.yml`
- Move: `domains/traffic/models/**` → `models/traffic/**`
- Move: `domains/weather/models/**` → `models/weather/**`
- Move: `domains/traffic/tests/*.sql` → `tests/traffic/**`
- Move: `domains/weather/tests/*.sql` → `tests/weather/**`
- Move: `domains/weather/macros/**` → `macros/weather/**`
- Move: `domains/weather/seeds/**` → `seeds/weather/**`
- Preserve: 다른 `domains/*` dbt project 전체

**TDD**

1. root project 이름, 두 group, exact schema generation, unique selector membership을 검증하는 구조 테스트를 먼저 작성한다.
2. 기존 두 project의 model/source/test 이름 집합을 fixture로 기록하고 root graph의 집합과 parity를 검사한다.
3. `target.schema` 하드코딩 테스트를 실패시키고 relation/node-aware schema interface로 바꾼다.
4. `model.traffic.*`, `model.weather.*`, `tests/<file>` 고정을 manifest metadata 기반 해석으로 바꾼다.
5. `asac_axes`는 `ASAC_AXES_SCHEMA`의 한 canonical relation으로 소유하고 두 도메인이 같은 `ref()`를 사용한다.
6. `static_parser: false`와 certificate validation을 root flags로 유지한다.

**Verify**

```powershell
dbt deps --project-dir . --profiles-dir .
dbt parse --project-dir . --profiles-dir . --target dev --no-partial-parse --target-path target/contract-parse
dbt ls --project-dir . --profiles-dir . --select tag:ask_seoul_traffic_transform_silver --output json
dbt ls --project-dir . --profiles-dir . --select tag:ask_seoul_weather_transform_silver --output json
```

### 이번 순차 실행 체크리스트

- [ ] `contracts/engine/tests/test_monoproject_architecture.py`에 root project 부재, split project 잔존, phase selector/tag 부재를 먼저 검증하는 테스트를 추가하고 RED를 확인한다.
- [ ] Docker의 기존 Traffic/Weather split manifest에서 model/source/seed/test 이름 집합을 추출해 이동 전 기준선을 기록한다.
- [ ] `models/{traffic,weather}`, `tests/{traffic,weather}`, `macros/weather`, `seeds/weather`로 `git mv`한다. Python tests도 `tests/{traffic,weather}`로 옮기고 package marker를 둔다.
- [ ] singular SQL은 `tests/<domain>/<workflow>/<phase>/`에 배치한다. root `dbt_project.yml`은 이 phase folder에만 `+tags`를 적용하며 singular test 이름을 열거하지 않는다.
- [ ] root `dbt_project.yml`, `profiles.yml`, `packages.yml`, `package-lock.yml`, `selectors.yml`을 만들고 project/profile 이름을 `asac_seoul`로 고정한다.
- [ ] `macros/generate_schema_name.sql`은 `node.package_name == 'asac_axes'`를 `ASAC_AXES_SCHEMA`로, root FQN의 첫 domain segment를 각각 `TRAFFIC_SCHEMA`와 `WEATHER_SCHEMA`로 보내고 나머지는 `DBT_CONTROL_SCHEMA`를 사용한다.
- [ ] Weather guard는 `weather_schema_name()` helper를 통해 `WEATHER_SCHEMA`를 비교하고, Traffic recovery singular SQL은 `ref()`만 사용한다.
- [ ] Traffic manifest dependency validator는 manifest `metadata.project_name`을 읽어 `model.<project_name>.*`를 판정하며 old `model.traffic.*`를 고정하지 않는다.
- [ ] Docker에서 `dbt deps`, fresh `dbt parse`, 모든 DAG phase `dbt ls` non-empty, singular tag 정확성, W1/W2 normal-tag 배제, 이동 전 resource-name parity를 확인한다.
- [ ] 기본 `python -m pytest` collection으로 Traffic/Weather 동일 basename Python tests가 충돌하지 않는지 확인한다.

## Task 3: tag/selector가 phase membership을 소유

**Files**

- Modify: `models/traffic/**/*.sql`, `models/weather/**/*.sql`
- Modify: `tests/traffic/**/*.sql`, `tests/weather/**/*.sql`
- Create/Modify: `selectors.yml`
- Create: `contracts/engine/tests/test_phase_selectors.py`

**Contract**

- 각 scheduled model은 정확히 하나의 phase tag를 가진다.
- phase tag끼리 model membership이 겹치지 않는다.
- DAG-owned singular test는 실행 phase tag를 직접 가진다.
- named selector는 빈 집합을 반환할 수 없다.
- Weather W1/W2 전용 model은 normal transform phase에 유입되지 않는다.
- Traffic source/axes exact gate membership은 DAG literal이 아니라 manifest policy가 검증한다.

## Task 4: schema YAML 분할

**Files**

- Split: `models/traffic/schema.yml`
- Split: `models/weather/schema.yml`
- Keep: domain별 `sources.yml`
- Create: 공개 Gold model 옆의 `<model>.yml`
- Create: 작은 응집 family용 `_silver.yml`, `_recovery.yml`

**Rules**

- model 선언은 정확히 한 YAML에만 둔다.
- public Gold는 SQL 옆 YAML 하나로 전체 interface를 읽을 수 있어야 한다.
- YAML anchor/alias는 사용하지 않는다.
- 필드 의미를 별도 `docs()` 파일로 과도하게 흩뜨리지 않는다.
- 각 domain index는 100줄 이내에서 source, selector, published interface, 핵심 invariant를 연결한다.

## Task 5: DAG와 manifest handoff

ASAC-DAG #358에서는 model/test 이름을 전달하지 않는다. DAG는 phase selector와 invocation identity만 전달한다.

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

Weather와 Traffic은 서로 import하지 않는다. 각 domain 안의 adapter가 같은 invocation interface를 구현하되, 공통 membership과 lineage는 dbt graph가 소유한다.

## Task 6: 검증과 중단 조건

1. `git diff --name-only`에 다른 domain 경로가 나타나면 즉시 중단한다.
2. Python test, dbt parse, selector parity, manifest contract를 순서대로 검증한다.
3. dev schema에서 phase별 `run`/`test`를 실행하고 기존 relation 이름과 row count를 비교한다.
4. 같은 snapshot/run으로 재실행해 idempotency를 확인한다.
5. Traffic/Weather 외 selector/DAG가 변경되지 않았음을 검사한다.
6. 커밋, push, PR은 사용자 승인 전 실행하지 않는다.

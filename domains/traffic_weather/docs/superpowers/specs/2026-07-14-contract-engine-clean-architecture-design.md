# 계약 Engine 클린 아키텍처 설계

## 목적

`contracts/engine`의 세 canonical 구현을 책임별 private package로 분해한다. 기존 CLI 경로와 명령, 테스트가 소비하는 Python import 이름, 데이터 규칙, 오류 문구, report 정렬, exit code, stdout/stderr, UTF-8 encoding 동작은 바꾸지 않는다.

대상 facade는 다음 세 파일이다.

- `contracts/engine/lint_schema_contract_source.py`
- `contracts/engine/validate_public_gold_manifest.py`
- `contracts/engine/compare_public_gold_catalog.py`

## 보호해야 할 기존 의도

git 이력의 #144 도입과 도메인 분리, Weather canonical safety 변경이 만든 다음 의도를 유지한다.

- YAML linter는 지원하지 않는 문법과 불완전한 scan을 fail-closed로 보고한다.
- manifest validator는 canonical/legacy metadata 충돌을 숨기지 않는다.
- catalog comparator는 선언 검증이 끝나지 않으면 physical proof를 진행하지 않는다.
- report error ordering과 JSON byte 표현은 결정적이어야 한다.
- symlink input/output, input alias, non-finite JSON, 과대 입력을 거부한다.
- CLI는 `PASS=0`, `FAIL=1`, `ERROR=2`를 유지한다.
- stdout/stderr 분리, trailing newline, UTF-8 fallback을 유지한다.
- package import와 `python contracts/engine/<command>.py` direct execution을 모두 유지한다.

## 선택한 구조

engine별 private package를 두고 기존 세 파일은 explicit re-export와 `main()` 호출만 담당하는 facade로 유지한다. wildcard import는 사용하지 않으며 private package의 `__init__.py`는 비워 둔다.

```text
contracts/engine/
├── artifact_io.py
├── lint_schema_contract_source.py
├── validate_public_gold_manifest.py
├── compare_public_gold_catalog.py
├── _schema_contract/
│   ├── __init__.py
│   ├── types.py
│   ├── lexing.py
│   ├── parsing.py
│   ├── descriptions.py
│   ├── resources.py
│   ├── reporting.py
│   ├── repository.py
│   ├── service.py
│   └── cli.py
├── _manifest_contract/
│   ├── __init__.py
│   ├── foundation.py
│   ├── metadata.py
│   ├── publication.py
│   ├── time_rules.py
│   ├── space_rules.py
│   ├── semantic_rules.py
│   ├── lineage_rules.py
│   ├── node_validation.py
│   ├── service.py
│   └── cli.py
└── _catalog_contract/
    ├── __init__.py
    ├── reporting.py
    ├── parsing.py
    ├── comparison.py
    └── cli.py
```

각 facade는 160줄 이하, 내부 모듈과 test module은 500줄 이하를 강제한다. 500줄은 상한이며 일반 책임 모듈은 250~350줄 안팎을 우선한다. 91개 기존 behavior test는 메서드 본문을 바꾸지 않고 semantics/resources/parser/filesystem, core/safety/publication/semantics, validation/evidence/I/O 책임으로 나눈다. CLI subprocess helper는 `cli_fixtures.py`로 분리한다.

## 호환 surface

테스트와 현재 실행 경로가 실제 사용하는 이름만 facade에서 명시적으로 re-export한다.

- linter: `MAX_FILE_BYTES`, `MAX_LINE_COUNT`, `MAX_LINE_LENGTH`, `MAX_SCALAR_LENGTH`, `MAX_NESTING_DEPTH`, `lint_schema_contracts`, `render_report`, `main`
- validator: `MAX_JSON_CONTAINERS`, `validate_manifest`, `render_json`, `main`
- comparator: `compare_public_gold_catalog`, `render_json`, `main`

내부 private helper는 facade 호환 surface로 승격하지 않는다. comparator와 validator 사이의 기존 private helper 의존은 facade가 아니라 private package 내부의 명시적 import로 바꾼다.

## 의존 방향

```text
facade -> own private package
catalog comparison -> manifest service/foundation
manifest metadata -> schema description helpers
schema package -> standard library
all CLI adapters -> artifact_io
```

private package는 세 facade를 import하지 않는다. `_schema_contract`는 다른 engine package를 import하지 않는다. `_manifest_contract`는 schema description helper만 소비하고, `_catalog_contract`는 manifest validation과 JSON shape helper만 소비한다. 이 방향으로 cycle을 막는다.

## 동작 흐름

- schema CLI: 인자 해석 -> repository path 검증/읽기 -> lexical parse -> resource rule -> report -> atomic output/stdout
- manifest CLI: 인자 해석 -> JSON repository adapter -> shape preflight -> node/domain rule -> report/catalog -> atomic output/stdout
- catalog CLI: 인자 해석 -> manifest/catalog JSON adapter -> manifest declaration validation -> catalog parsing/comparison -> report -> atomic output/stdout

각 단계에서 기존 exception을 같은 위치에서 같은 report code/message로 번역한다. 새로운 exception type이나 report field는 추가하지 않는다.

## 테스트 전략

1. architecture RED test로 package layout, facade/internal/test line limit, wildcard 금지, empty `__init__.py`, internal-to-facade import 금지, compatibility export를 고정한다.
2. 기존 91 behavior tests를 engine별 회귀 oracle로 사용하고, 분할 전후 method source hash를 비교한다.
3. engine 하나를 분해할 때마다 해당 behavior module과 CLI encoding test를 실행한다.
4. 마지막에 전체 owned suite, write-free compile, 세 direct CLI subprocess smoke, diff/scope check를 실행한다.

## AI index

- root `README.md`는 Traffic/Weather monoproject 진입점과 graph 경계, 실제 deps/parse 명령만 제공한다.
- `contracts/engine/README.md`는 stable facade와 private 책임, 의존 방향, CLI 호환 규칙만 제공한다.
- 두 파일은 각각 100줄 이하이며 architecture test가 필수 진입점 token을 고정한다.

## 비범위

- Traffic/Weather 모델, schema YAML, seed, macro, `asac_axes` 변경
- 데이터 계약 규칙이나 오류 문구 개선
- report schema 또는 CLI option 추가
- 공통 error/report/filesystem framework 도입
- commit, push, PR 생성

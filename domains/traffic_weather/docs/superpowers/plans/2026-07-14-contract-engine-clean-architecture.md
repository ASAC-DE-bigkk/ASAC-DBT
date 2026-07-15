# 계약 Engine 클린 아키텍처 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task. 각 단계는 checkbox로 추적한다.

**Goal:** 세 canonical 계약 engine과 behavior test를 작은 책임 모듈로 분해하면서 기존 CLI·import·report byte·exit semantics를 그대로 유지한다.

**Architecture:** 기존 세 CLI 파일은 explicit compatibility facade로 남기고 구현은 `_schema_contract`, `_manifest_contract`, `_catalog_contract` private package로 이동한다. 계층 순서는 schema -> manifest -> catalog이고 코드 의존은 catalog -> manifest -> schema 단방향이다. `artifact_io` 외 공통 abstraction은 만들지 않는다.

**Tech Stack:** Python 3, `argparse`, `dataclasses`, `json`, `pytest`, AST architecture tests

## Global Constraints

- 오직 `contracts/engine/**`, root `README.md`, 이 계획/spec, 그리고 별도 승인된 `selectors.yml`만 수정한다.
- 모델, schema YAML, seed, macro, `packages/asac_axes`는 수정하지 않는다.
- 데이터 규칙, 오류 code/message/path, 정렬, report shape, exit code, stdout/stderr, UTF-8 byte를 변경하지 않는다.
- facade는 실제 테스트 소비 이름만 explicit re-export하고 wildcard import를 사용하지 않는다.
- facade는 160줄 이하, 내부 모듈은 500줄 이하이며 책임 모듈은 250~350줄 안팎을 우선한다.
- 모든 `contracts/engine/tests/*.py`는 500줄 이하, root/engine README는 각각 100줄 이하로 유지한다.
- private package `__init__.py`는 비워 둔다.
- 사용자 승인 없는 commit, push, PR은 실행하지 않는다. 아래 모든 commit 단계는 생략한다.

---

### Task 1: Architecture contract를 RED로 고정

**Files:**
- Modify: `contracts/engine/tests/test_engine_architecture.py`

**Interfaces:**
- Consumes: 현재 세 giant facade와 split behavior tests
- Produces: exact package layout, line limit, import boundary, compatibility exports 검사

- [ ] `ENGINE_PACKAGES`, `FACADE_EXPORTS`, `MAX_FACADE_LINES=160`, `MAX_INTERNAL_LINES=500` fixture를 추가한다.
- [ ] AST로 `ImportFrom`의 `*`를 금지하고 facade가 exact 이름을 re-export하는지 검사한다.
- [ ] private module이 세 facade를 import하지 않는지 검사한다.
- [ ] private `__init__.py`가 빈 파일인지 검사한다.
- [ ] targeted test를 실행해 private package 부재와 giant facade line limit 때문에 실패하는지 확인한다.

Run:

```powershell
python -m pytest -q contracts/engine/tests/test_engine_architecture.py -p no:cacheprovider
```

Expected: package/line-size assertions에서 FAIL.

### Task 2: Schema linter 분해

**Files:**
- Create: `contracts/engine/_schema_contract/{__init__,types,lexing,parsing,descriptions,resources,reporting,repository,service,cli}.py`
- Replace: `contracts/engine/lint_schema_contract_source.py`
- Test: `contracts/engine/tests/test_schema_contract_source_linter_{semantics,resources,parser,filesystem}.py`
- Test: `contracts/engine/tests/test_cli_encoding.py`

**Interfaces:**
- Produces: `lint_schema_contracts`, `render_report`, five MAX constants, `main`
- Internal dependency: `types -> lexing -> parsing -> descriptions/resources -> reporting/repository -> service -> cli`

- [ ] 기존 top-level definitions를 다음 책임으로 byte-preserving 이동한다.
  - `types.py`: constants, `Token`, `MapEntry`, `Node`, `ScanError`
  - `lexing.py`: comment/quote/colon/flow/block/tokenize helpers
  - `parsing.py`: scalar decode와 YAML subset parser
  - `descriptions.py`: identifier/placeholder/description evidence
  - `resources.py`: column/resource extraction과 duplicate detection
  - `reporting.py`: error ordering, proof, empty report, renderer
  - `repository.py`: project scope, cross-file duplicate, file discovery
  - `service.py`: `lint_schema_contracts`
  - `cli.py`: parser, output validation, atomic write, `main`
- [ ] facade를 아래 explicit surface만 import하도록 교체한다.

```python
from contracts.engine._schema_contract.cli import main
from contracts.engine._schema_contract.service import lint_schema_contracts
from contracts.engine._schema_contract.reporting import render_report
from contracts.engine._schema_contract.types import (
    MAX_FILE_BYTES,
    MAX_LINE_COUNT,
    MAX_LINE_LENGTH,
    MAX_NESTING_DEPTH,
    MAX_SCALAR_LENGTH,
)
```

- [ ] direct execution fallback은 `_schema_contract...` local package import로 유지한다.
- [ ] linter behavior와 CLI encoding tests를 실행한다.

Run:

```powershell
python -m pytest -q contracts/engine/tests -k "schema_contract_source_linter or cli_encoding" -p no:cacheprovider
```

Expected: 33개 test method 범위 PASS 또는 capability skip만 존재.

### Task 3: Manifest validator 분해

**Files:**
- Create: `contracts/engine/_manifest_contract/{__init__,foundation,metadata,publication,time_rules,space_rules,semantic_rules,lineage_rules,node_validation,service,cli}.py`
- Replace: `contracts/engine/validate_public_gold_manifest.py`
- Test: `contracts/engine/tests/test_public_gold_manifest_{core,safety,publication,semantics}.py`
- Test: `contracts/engine/tests/test_cli_encoding.py`

**Interfaces:**
- Produces: `MAX_JSON_CONTAINERS`, `validate_manifest`, `render_json`, `main`
- Consumes: `_schema_contract.descriptions`의 placeholder/identifier/Hangul helper

- [ ] 정의를 다음 책임으로 이동한다.
  - `foundation.py`: constants, artifact error, JSON preflight, unsafe metadata, proof/report/render
  - `metadata.py`: public/column metadata merge, common scalar/column validation
  - `publication.py`: exposure owner와 publication rule
  - `time_rules.py`, `space_rules.py`: 각 structured rule
  - `semantic_rules.py`: metrics와 quality
  - `lineage_rules.py`: lineage, joins, lifecycle
  - `node_validation.py`: one governed node validation
  - `service.py`: manifest traversal, selector resolution, catalog assembly
  - `cli.py`: JSON input/output adapter와 `main`
- [ ] facade는 다음 explicit surface만 제공한다.

```python
from contracts.engine._manifest_contract.cli import main
from contracts.engine._manifest_contract.foundation import MAX_JSON_CONTAINERS, render_json
from contracts.engine._manifest_contract.service import validate_manifest
```

- [ ] canonical/legacy conflict, production-size limits, report bytes, 0/1/2 exit behavior 회귀 tests를 실행한다.

Run:

```powershell
python -m pytest -q contracts/engine/tests -k "public_gold_manifest or cli_encoding" -p no:cacheprovider
```

Expected: 44개 test method 범위 PASS 또는 capability skip만 존재.

### Task 4: Catalog comparator 분해

**Files:**
- Create: `contracts/engine/_catalog_contract/{__init__,reporting,parsing,comparison,cli}.py`
- Replace: `contracts/engine/compare_public_gold_catalog.py`
- Test: `contracts/engine/tests/test_public_gold_catalog_{validation,evidence,io}.py`
- Test: `contracts/engine/tests/test_cli_encoding.py`

**Interfaces:**
- Produces: `compare_public_gold_catalog`, `render_json`, `main`
- Consumes: `_manifest_contract.foundation`과 `_manifest_contract.service`

- [ ] report/evidence/proof를 `reporting.py`, catalog shape parsing을 `parsing.py`, type/column/order 비교와 orchestration을 `comparison.py`, filesystem/CLI를 `cli.py`로 이동한다.
- [ ] facade는 다음 explicit surface만 제공한다.

```python
from contracts.engine._catalog_contract.cli import main
from contracts.engine._catalog_contract.comparison import compare_public_gold_catalog
from contracts.engine._catalog_contract.reporting import render_json
```

- [ ] catalog comparison과 CLI encoding tests를 실행한다.

Run:

```powershell
python -m pytest -q contracts/engine/tests -k "public_gold_catalog or cli_encoding" -p no:cacheprovider
```

Expected: 18개 test method 범위 PASS 또는 capability skip만 존재.

### Task 5: Behavior test와 AI index 분해

**Files:**
- Create: `contracts/engine/tests/cli_fixtures.py`
- Split: linter 4개, manifest 4개, catalog 3개 behavior module
- Retire: 세 giant behavior module
- Create: `README.md`, `contracts/engine/README.md`
- Modify: `contracts/engine/tests/test_engine_architecture.py`, `test_monoproject_architecture.py`

- [ ] architecture RED로 모든 test module 500줄, README 100줄 상한을 고정한다.
- [ ] 89개 non-CLI method의 이름·본문 hash를 보존해 11개 책임 module로 이동한다.
- [ ] CLI 2개를 포함한 behavior test 총 91개를 AST로 확인한다.
- [ ] root AI index에 monoproject 경계, start file, local `asac_axes`, public `ref()`, DAG selector, deps/parse 예시를 기록한다.
- [ ] engine AI index에 facade/private 책임, 의존 방향, `artifact_io`, 0/1/2와 stdout/stderr/UTF-8 호환을 기록한다.

### Task 6: 통합 검증

**Files:**
- Verify only: `contracts/engine/**`, `selectors.yml`

- [ ] architecture test를 GREEN으로 확인한다.
- [ ] 기존 91 behavior tests와 모든 owned tests를 fresh 실행한다.
- [ ] 모든 engine Python을 write-free `compile()`로 검사한다.
- [ ] 세 facade를 direct subprocess로 실행해 기존 fixture report byte와 exit code를 검사한다.
- [ ] `git diff --check`, modified path allowlist, giant facade 제거, internal file size를 확인한다.
- [ ] selector named gate가 fresh dbt에서 정확히 40개인지 최종 확인한다.

Run:

```powershell
python -m pytest -q contracts tests workflows/tests --ignore=dbt_packages --disable-warnings -p no:cacheprovider
git diff --check HEAD
```

Expected: failure 0, scope 외 신규 변경 0. commit/push는 실행하지 않는다.

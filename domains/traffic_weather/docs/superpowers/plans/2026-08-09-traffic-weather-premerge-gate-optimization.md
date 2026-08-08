# Traffic·Weather pre-merge gate 최적화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fresh dbt manifest를 한 번만 생성해 Traffic Gold cadence selector와 inventory 계약을 fail-closed로 검증하고, collection-state 운영 품질 검증을 public Gold cadence gate에서 분리한다.

**Architecture:** `validate_traffic_gold_test_inventory.py`가 manifest의 test node tag를 직접 읽어 gate/hourly/full selector의 unique-id set을 계산하고 exact baseline과 비교한다. `premerge_gate.py`는 `dbt deps → dbt parse → inventory validator → Python contracts → singular dependency validator`만 실행하며, 반복 `dbt ls`는 실행하지 않는다. selector YAML의 의미는 정적 contract test가 고정한다.

**Tech Stack:** Python 3.11, dbt 1.10, pytest, PyYAML, GitHub Actions

## Global Constraints

- PR·CI·개발 검증의 dbt target은 `dev`만 사용하며 prod 연결·R2·Iceberg write·D1 publish는 수행하지 않는다.
- `validate-traffic-manifest` required check 이름, fresh `dbt parse --no-partial-parse`, 125/145/175 exact cadence baseline은 유지한다.
- selector count는 manifest의 `resource_type == "test"`와 tag set으로 계산하고 `unique_id` set union으로 dbt selector의 dedup 의미를 보존한다.
- collection-state는 public serving Gold가 아닌 control-plane quality이며, Traffic singular test 하나로 검증하고 Traffic Gold cadence inventory에서 제외한다. 제거한 generic 불변식은 shared singular macro가 유지한다.
- root의 `LessonRun.md`, `resume-evidence-log.md`, 사용자 로컬 변경은 stage/commit하지 않는다.

---

## 파일 구조

- Modify: `domains/traffic_weather/contracts/traffic/scripts/validate_traffic_gold_test_inventory.py` — manifest-native selector count, exact baseline 검증, CLI 단순화.
- Modify: `domains/traffic_weather/contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py` — tag 조합, union/dedup, baseline drift를 검증하는 단위 테스트.
- Modify: `domains/traffic_weather/workflows/premerge_gate.py` — `dbt ls` 기반 selector loop 제거 및 manifest validator 호출만 유지.
- Modify: `domains/traffic_weather/workflows/tests/test_premerge_gate.py` — fresh parse 이후 `dbt ls` 없이 동일 fail-closed 순서가 실행되고, 세 cadence selector YAML 정의가 tag/resource_type/union 구조를 유지하는지 검증.
- Modify: `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_collection_slot_state.yml` — public Gold cadence generic test를 제거하고 column 설명만 유지.
- Modify: `domains/traffic_weather/macros/collection_state.sql` — singular assertion에 expected-slot unique, domain, source 불변식을 포함.
- Modify: `domains/traffic_weather/tests/test_collection_state_projection_contract.py` 및 `domains/traffic_weather/tests/weather/transform/gold/assert_gold_weather_collection_slot_state_contract.sql` — 확장 macro signature와 Weather expected domain을 고정.
- Move: `domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_collection_slot_state_contract.sql` → `domains/traffic_weather/tests/traffic/collection_state/assert_gold_traffic_collection_slot_state_contract.sql` — `ask_seoul_collection_state` tag의 control-plane singular test로 유지.

### Task 1: collection-state를 cadence gate에서 분리

**Files:**
- Modify: `domains/traffic_weather/models/traffic/transform/gold/gold_traffic_collection_slot_state.yml`
- Modify: `domains/traffic_weather/macros/collection_state.sql`
- Modify: `domains/traffic_weather/tests/test_collection_state_projection_contract.py`
- Modify: `domains/traffic_weather/tests/weather/transform/gold/assert_gold_weather_collection_slot_state_contract.sql`
- Move: `domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_collection_slot_state_contract.sql` → `domains/traffic_weather/tests/traffic/collection_state/assert_gold_traffic_collection_slot_state_contract.sql`

**Interfaces:**
- Consumes: `collection_slot_state_assertions(ref(...), expected_domain)` macro와 `gold_traffic_collection_slot_state` model.
- Produces: `tag:ask_seoul_collection_state`로 명시 선택 가능한 singular contract test 하나, 그리고 unchanged `125/145/175` Traffic Gold cadence portfolio.

- [x] **Step 1: 현재 selector baseline이 125/145/175인지 확인한다.**

Run: `dbt ls --target dev --selector ask_seoul_traffic_transform_gold_gate_tests --resource-type test --output name --quiet | wc -l` 및 hourly/full selector에 같은 명령

Expected: collection-state 변경 전에는 새 test가 `traffic_gold_gate`로 들어가 baseline보다 1 큰 결과가 재현되거나, 변경 후에는 정확히 `125`, `145`, `175`이다.

- [x] **Step 2: failing manifest inventory 검증을 확인한다.**

Run: `python contracts/traffic/scripts/validate_traffic_gold_test_inventory.py --manifest target/manifest.json --inventory contracts/traffic_gold_test_cadence.yml`

Expected: cadence path 아래의 tier 없는 test 또는 baseline drift가 있으면 non-zero로 실패한다.

- [x] **Step 3: generic tests를 제거하고 singular test를 control-plane path/tag로 이동한다.**

`gold_traffic_collection_slot_state.yml`의 column-level `tests:`를 제거한다. `collection_slot_state_assertions` macro는 window count로 `expected_slot_id` unique를, `expected_domain` 인자로 domain equality를, `source_id is null`으로 기존 generic 불변식을 계속 검증한다. Traffic·Weather singular test는 각각 `'traffic'`, `'weather'`를 전달한다. 이동한 Traffic SQL 파일의 config는 아래처럼 고정한다.

```sql
{{ config(tags=['ask_seoul_collection_state']) }}

{{ collection_slot_state_assertions(ref('gold_traffic_collection_slot_state'), 'traffic') }}
```

- [x] **Step 4: dbt parse와 singular test를 실행한다.**

Run: `dbt parse --target dev --no-partial-parse --target-path target/collection-state-parse` 와 `dbt test --target dev --select tag:ask_seoul_collection_state --vars '{"traffic_snapshot_dag_run_id":"ci__collection-state"}'`

Expected: parse succeeds; test는 data availability에 따라 pass 또는 명시적 upstream/data error로 종료하며, selector/inventory discovery 오류가 발생하지 않는다.

### Task 2: manifest-native selector count를 TDD로 구현

**Files:**
- Modify: `domains/traffic_weather/contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py`
- Modify: `domains/traffic_weather/contracts/traffic/scripts/validate_traffic_gold_test_inventory.py`

**Interfaces:**
- Consumes: `manifest["nodes"][unique_id]`의 `resource_type`, `tags`.
- Produces: `manifest_selector_counts(manifest: object) -> dict[str, int]`; 반환 키는 `EXPECTED_SELECTOR_COUNTS`의 세 selector 이름과 정확히 동일하다.

- [x] **Step 1: failing selector-count unit test를 추가한다.**

`_portfolio_test_nodes()`에서 Gold gate/hourly/daily test에 `ask_seoul_traffic_transform_gold` tag를 함께 부여하고 아래 검증을 추가한다.

```python
def test_manifest_selector_counts_match_exact_cadence_unions(validator) -> None:
    assert validator.manifest_selector_counts(_manifest()) == {
        "ask_seoul_traffic_transform_gold_gate_tests": 125,
        "ask_seoul_traffic_transform_gold_hourly_tests": 145,
        "ask_seoul_traffic_transform_gold_full_tests": 175,
    }
```

추가로 최소 manifest에서 gate+hourly tag를 함께 가진 동일 `unique_id`가 hourly/full에서 한 번만 세어지는 테스트와 `resource_type: model` 노드가 세어지지 않는 테스트를 작성한다.

- [x] **Step 2: 새 unit test가 실패하는지 확인한다.**

Run: `pytest -q contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py -k 'manifest_selector_counts'`

Expected: `AttributeError: module ... has no attribute 'manifest_selector_counts'`.

- [x] **Step 3: unique-id set 기반 selector count 함수를 구현한다.**

`validate_traffic_gold_test_inventory.py`에 다음 contract를 구현한다.

```python
def manifest_selector_counts(manifest: object) -> dict[str, int]:
    nodes = _manifest_nodes(_mapping(manifest, "manifest"))
    tier_ids = {
        tier: {
            unique_id
            for unique_id, node in nodes.items()
            if node.get("resource_type") == "test"
            and TRAFFIC_GOLD_TAG in _node_tags(node, unique_id)
            and GOLD_TIER_TAGS[tier] in _node_tags(node, unique_id)
        }
        for tier in GOLD_TIER_TAGS
    }
    return {
        "ask_seoul_traffic_transform_gold_gate_tests": len(tier_ids["gate"]),
        "ask_seoul_traffic_transform_gold_hourly_tests": len(tier_ids["gate"] | tier_ids["hourly_extension"]),
        "ask_seoul_traffic_transform_gold_full_tests": len(
            tier_ids["gate"] | tier_ids["hourly_extension"] | tier_ids["daily_extension"]
        ),
    }
```

- [x] **Step 4: exact baseline을 fail-closed로 연결한다.**

`validate_inventory()` 시작 시 `actual_selector_counts = manifest_selector_counts(manifest_doc)`를 계산하고, `EXPECTED_SELECTOR_COUNTS`와 다른 경우 `InventoryError("selector counts mismatch: ...")`를 발생시킨다. 외부 `--selector-count` 입력으로 baseline을 우회하지 않도록 CLI argument와 `parse_selector_counts()`를 제거한다.

- [x] **Step 5: validator tests를 실행한다.**

Run: `pytest -q contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py`

Expected: 모든 test가 통과하며, 실제 selector count drift와 tier/tag 오류는 `InventoryError`로 실패한다.

### Task 3: selector YAML static contract와 pre-merge 실행 순서를 갱신

**Files:**
- Modify: `domains/traffic_weather/workflows/premerge_gate.py`
- Modify: `domains/traffic_weather/workflows/tests/test_premerge_gate.py`

**Interfaces:**
- Consumes: `selectors.yml`의 세 named selector, fresh `target/manifest.json`.
- Produces: `run_premerge_gate()`가 `dbt ls`를 전혀 호출하지 않고 inventory validator에 fresh manifest만 넘기는 command sequence.

- [x] **Step 1: failing static selector contract test를 작성한다.**

`workflows/tests/test_premerge_gate.py`의 `test_traffic_gold_cadence_selectors_are_declared()`를 세 exact definition 비교로 확장한다. gate는 `ask_seoul_traffic_transform_gold` + `traffic_gold_gate` + `resource_type:test` intersection, hourly/full은 각 tier intersection의 ordered union을 요구하고 모든 tag 조건은 `indirect_selection: empty`여야 한다.

- [x] **Step 2: failing workflow command-sequence test를 작성한다.**

`test_gate_owns_the_complete_read_only_premerge_sequence()`에서 expected command를 아래로 변경한다.

```text
git diff → dbt deps → dbt parse --no-partial-parse →
validate_traffic_gold_test_inventory.py --manifest ... --inventory ... →
pytest → validate_singular_test_dependency_manifest.py
```

`RecordingRunner`의 `dbt ls` simulation과 empty arbitrary selector test를 제거하고, `assert all(command[:2] != ["dbt", "ls"] for command in commands)`를 추가한다.

- [x] **Step 3: workflow test가 기존 코드에서 실패하는지 확인한다.**

Run: `pytest -q workflows/tests/test_premerge_gate.py`

Expected: 기존 code가 `dbt ls` command를 기록하므로 command-sequence assertion이 실패한다.

- [x] **Step 4: pre-merge workflow를 최소 변경한다.**

`premerge_gate.py`에서 `_selector_names()`와 `validate_named_selectors()`를 삭제한다. `run_premerge_gate()`는 parse 이후 `validate_traffic_gold_test_inventory(..., manifest_path=manifest_path, command_runner=...)`만 호출한다. `validate_traffic_gold_test_inventory()`의 CLI command에서 모든 `--selector-count` argument를 제거한다.

- [x] **Step 5: static/workflow tests를 실행한다.**

Run: `pytest -q workflows/tests/test_premerge_gate.py`

Expected: command sequence는 `dbt ls`가 0회이고 selector YAML drift, manifest count drift, inventory drift는 각각 contract test로 실패한다.

### Task 4: fresh manifest으로 dev-only end-to-end 검증 및 기록

**Files:**
- Modify: `resume-evidence-log.md` (local only; stage 금지)

**Interfaces:**
- Consumes: feature branch base/head SHA와 `dbt` executable.
- Produces: CI와 동일한 read-only pre-merge gate result 및 before/after wall-time evidence.

- [x] **Step 1: focused Python regression suite를 실행한다.**

Run: `pytest -q contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py workflows/tests/test_premerge_gate.py tests/traffic/test_gold_trigger_selectors.py`

Expected: pass; test count와 실행 시간을 기록한다.

- [x] **Step 2: fresh dev manifest과 inventory를 독립 검증한다.**

Run: `dbt deps && dbt parse --target dev --no-partial-parse --target-path target/premerge-optimization --vars '{"traffic_snapshot_dag_run_id":"ci__premerge-optimization","traffic_flow_snapshot_dag_run_id":"ci__premerge-optimization"}' && python contracts/traffic/scripts/validate_traffic_gold_test_inventory.py --manifest target/premerge-optimization/manifest.json --inventory contracts/traffic_gold_test_cadence.yml`

Expected: `PASS: traffic Gold test cadence inventory is valid (239/259/299)`; no prod target or writes.

- [ ] **Step 3: CI-equivalent pre-merge command을 실행한다.**

Run: `python workflows/premerge_gate.py run --repository-root . --project-dir . --target-path target/premerge-optimization-gate --base-sha origin/dev --head-sha HEAD`

Expected: `dbt ls` 없이 successful exit. 실패 시 failure command·stdout/stderr를 보존하고 원인을 수정한 뒤 같은 command를 재실행한다.

- [x] **Step 4: local evidence를 갱신한다.**

`resume-evidence-log.md`의 기존 관련 RE entry에 before 7m10s, after local/CI actual wall time, 제거한 command 수(`dbt ls × 3 → 0`), unchanged 125/145/175 baseline과 `NEEDS_MEASUREMENT` 여부를 기록한다. 이 파일은 절대 stage하지 않는다.

- [x] **Step 5: 정확한 경로만 stage·commit·push한다.**

Run: `git add domains/traffic_weather/contracts/traffic/scripts/validate_traffic_gold_test_inventory.py domains/traffic_weather/contracts/traffic/tests/test_validate_traffic_gold_test_inventory.py domains/traffic_weather/docs/superpowers/plans/2026-08-09-traffic-weather-premerge-gate-optimization.md domains/traffic_weather/macros/collection_state.sql domains/traffic_weather/models/traffic/transform/gold/gold_traffic_collection_slot_state.yml domains/traffic_weather/tests/test_collection_state_projection_contract.py domains/traffic_weather/tests/traffic/collection_state/assert_gold_traffic_collection_slot_state_contract.sql domains/traffic_weather/tests/traffic/transform/gold/assert_gold_traffic_collection_slot_state_contract.sql domains/traffic_weather/tests/weather/transform/gold/assert_gold_weather_collection_slot_state_contract.sql domains/traffic_weather/workflows/premerge_gate.py domains/traffic_weather/workflows/tests/test_premerge_gate.py`

Expected: local-only logs and unrelated user files are excluded; commit after validation uses `perf(traffic): fresh manifest 기반 pre-merge selector 검증` and push updates PR #481.

## Self-review

- Spec coverage: Task 1 separates collection-state ownership; Task 2 keeps exact manifest-native selector/inventory validation; Task 3 locks selector YAML semantics and removes repeated `dbt ls`; Task 4 performs dev-only end-to-end verification, records actual timing, and preserves commit boundaries.
- Placeholder scan: deferred implementation text와 undefined interface가 없다.
- Interface consistency: `manifest_selector_counts(manifest: object)` is introduced and consumed only within the validator; `run_premerge_gate()` retains its existing public CLI and validates through the existing inventory script.

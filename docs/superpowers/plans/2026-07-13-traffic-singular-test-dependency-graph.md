# Traffic Singular Test Dependency Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make traffic singular-test model dependencies deterministic and fail CI/dev verification when a fresh dbt manifest omits them.

**Architecture:** SQL `depends_on` comments provide dbt with explicit graph edges for every normal-transform traffic singular test that uses `ref()`. A small, standalone manifest validator owns the expected test-to-model mapping and validates a caller-supplied fresh artifact. Python tests prove the source declarations and validator behaviour without querying Trino.

**Tech Stack:** dbt Core 1.10, dbt-trino, Python standard library, pytest, JSON manifest v12.

## Global Constraints

- Change only ASAC-DBT traffic test contracts; do not modify Airflow, model SQL, source schemas, schedules, or data.
- Preserve `traffic_snapshot_dag_run_id`, current-vs-history semantics, recovery isolation, and all existing inline `ref()` calls.
- Validate a caller-supplied manifest path; never use a default/stale `target/manifest.json`.
- The validator must exit non-zero for missing test nodes, empty dependency arrays, and missing/unexpected model dependencies.
- Use a fresh `--target-path` and `--no-partial-parse` for runtime integration verification in the dev dbt container.

## Execution Order

Execute the independent units in this order: Task 2 (validator and canonical
mapping), Task 1 (SQL declarations against that mapping), Task 3 (dbt-repo
documentation and integration verification), then Task 4 (review and publish).
The ordering avoids importing a validator module before it exists.

---

### Task 1: Declare and unit-test the SQL graph contract

**Files:**
- Modify: `domains/traffic/tests/assert_gold_traffic_counts_match_silver.sql:1`
- Modify: `domains/traffic/tests/assert_gold_traffic_row_counts_positive.sql:1`
- Modify: `domains/traffic/tests/assert_silver_seoul_traffic_incident_grain_unique.sql:1`
- Modify: `domains/traffic/tests/assert_silver_traffic_admin_axis_consistent.sql:1`
- Modify: `domains/traffic/tests/assert_silver_traffic_admin_axis_coverage.sql:1`
- Modify: `domains/traffic/tests/assert_silver_traffic_event_at_matches_occurred_at.sql:1`
- Modify: `domains/traffic/tests/assert_silver_traffic_latest_publishable_record.sql:1`
- Modify: `domains/traffic/tests/assert_silver_traffic_location_contract.sql:1`
- Modify: `domains/traffic/tests/assert_silver_traffic_uses_publishable_runs.sql:1`
- Modify: `domains/traffic/tests/assert_silver_traffic_wgs84_required_when_source_coordinate_available.sql:1`
- Modify: `domains/traffic/tests/assert_traffic_current_pinned_publishable_run.sql:1`
- Modify: `domains/traffic/tests/test_current_state_contract.py:1-111`

**Interfaces:**
- Consumes: `REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES` from Task 2.
- Produces: source-level evidence that every expected `ref()` has a matching explicit dbt graph comment.

- [ ] **Step 1: Write the failing source-contract test**

  Add this test to `test_current_state_contract.py`; it imports the canonical mapping from the validator instead of duplicating model names:

  ```python
  from domains.traffic.contracts.scripts.validate_singular_test_dependency_manifest import (
      REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES,
  )

  def test_normal_transform_singular_tests_declare_each_model_ref_dependency():
      for filename, model_names in REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES.items():
          sql = (TRAFFIC_DIR / "tests" / filename).read_text(encoding="utf-8")
          for model_name in model_names:
              dependency_comment = f"-- depends_on: {{{{ ref('{model_name}') }}}}"
              inline_ref = f"ref('{model_name}')"
              assert dependency_comment in sql, f"missing {dependency_comment} in {filename}"
              assert inline_ref in sql, f"missing inline {inline_ref} in {filename}"
  ```

- [ ] **Step 2: Run the test to verify it fails before declarations exist**

  Run: `python -m pytest domains/traffic/tests/test_current_state_contract.py -q`

  Expected: FAIL because the mapping module and/or at least one `-- depends_on` comment does not exist.

- [ ] **Step 3: Add the explicit graph comments**

  Prepend one comment per dependency, preserving the inline references and existing comments. The exact mapping is:

  ```text
  assert_gold_traffic_counts_match_silver.sql:
    silver_seoul_traffic_incident_current, gold_traffic_incident_summary
  assert_gold_traffic_row_counts_positive.sql:
    gold_traffic_incident_summary
  assert_silver_seoul_traffic_incident_grain_unique.sql,
  assert_silver_traffic_admin_axis_consistent.sql,
  assert_silver_traffic_admin_axis_coverage.sql,
  assert_silver_traffic_event_at_matches_occurred_at.sql,
  assert_silver_traffic_latest_publishable_record.sql,
  assert_silver_traffic_location_contract.sql,
  assert_silver_traffic_uses_publishable_runs.sql,
  assert_silver_traffic_wgs84_required_when_source_coordinate_available.sql:
    silver_seoul_traffic_incident
  assert_traffic_current_pinned_publishable_run.sql:
    silver_seoul_traffic_incident_current
  ```

  For example, the count test starts:

  ```sql
  -- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
  -- depends_on: {{ ref('gold_traffic_incident_summary') }}
  with silver_counts as (
  ```

- [ ] **Step 4: Re-run the source contract suite**

  Run: `python -m pytest domains/traffic/tests/test_current_state_contract.py -q`

  Expected: PASS, including the new declaration test.

- [ ] **Step 5: Commit the declaration change**

  ```bash
  git add domains/traffic/tests
  git commit -m "fix(traffic): declare singular test dependencies"
  ```

### Task 2: Add a fail-closed fresh-manifest validator

**Files:**
- Create: `domains/traffic/contracts/scripts/validate_singular_test_dependency_manifest.py`
- Create: `domains/traffic/contracts/tests/test_validate_singular_test_dependency_manifest.py`

**Interfaces:**
- Consumes: `--manifest PATH` supplied by an explicit dbt parse target.
- Produces: process exit `0` only when the manifest contains the required graph; exit `1` and test-specific diagnostics otherwise.

- [ ] **Step 1: Write failing validator tests**

  Create tests that dynamically import the validator module and construct a minimal manifest. The valid fixture must include one node per mapped SQL file:

  ```python
  def manifest_with_required_nodes() -> dict[str, object]:
      nodes: dict[str, object] = {}
      for filename, model_names in validator.REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES.items():
          nodes[f"test.traffic.{Path(filename).stem}"] = {
              "resource_type": "test",
              "original_file_path": f"tests/{filename}",
              "depends_on": {
                  "nodes": [f"model.traffic.{model_name}" for model_name in model_names]
              },
          }
      return {"nodes": nodes}
  ```

  Cover four cases: a valid manifest passes; an empty `depends_on.nodes` fails; a required model removed from one test fails; a duplicate node for one `original_file_path` fails. Assert the error text includes the SQL filename and expected/actual node IDs.

- [ ] **Step 2: Run the new tests to verify they fail**

  Run: `python -m pytest domains/traffic/contracts/tests/test_validate_singular_test_dependency_manifest.py -q`

  Expected: FAIL because the validator module does not exist.

- [ ] **Step 3: Implement the validator and CLI**

  Add these stable public elements:

  ```python
  REQUIRED_SINGULAR_TEST_MODEL_DEPENDENCIES: dict[str, tuple[str, ...]] = {
      "assert_gold_traffic_counts_match_silver.sql": (
          "silver_seoul_traffic_incident_current", "gold_traffic_incident_summary",
      ),
      "assert_gold_traffic_row_counts_positive.sql": (
          "gold_traffic_incident_summary",
      ),
      "assert_silver_seoul_traffic_incident_grain_unique.sql": (
          "silver_seoul_traffic_incident",
      ),
      "assert_silver_traffic_admin_axis_consistent.sql": (
          "silver_seoul_traffic_incident",
      ),
      "assert_silver_traffic_admin_axis_coverage.sql": (
          "silver_seoul_traffic_incident",
      ),
      "assert_silver_traffic_event_at_matches_occurred_at.sql": (
          "silver_seoul_traffic_incident",
      ),
      "assert_silver_traffic_latest_publishable_record.sql": (
          "silver_seoul_traffic_incident",
      ),
      "assert_silver_traffic_location_contract.sql": (
          "silver_seoul_traffic_incident",
      ),
      "assert_silver_traffic_uses_publishable_runs.sql": (
          "silver_seoul_traffic_incident",
      ),
      "assert_silver_traffic_wgs84_required_when_source_coordinate_available.sql": (
          "silver_seoul_traffic_incident",
      ),
      "assert_traffic_current_pinned_publishable_run.sql": (
          "silver_seoul_traffic_incident_current",
      ),
  }

  class ManifestDependencyError(ValueError):
      pass

  def validate_manifest(manifest: object) -> None:
      """Raise ManifestDependencyError unless every required singular test has its exact model graph."""

  def main(argv: Sequence[str] | None = None) -> int:
      """Read --manifest JSON, print PASS or a diagnostic, and return 0 or 1."""
  ```

  `validate_manifest` finds `resource_type == "test"` nodes by exact
  `original_file_path == "tests/<filename>"`. It requires exactly one matching
  node, a list-valued non-empty `depends_on.nodes`, and compares only the
  `model.traffic.*` subset as a set to the expected model node IDs. It must
  reject an extra traffic model edge as well as a missing edge. `main` must use
  `argparse`, UTF-8 JSON, and `if __name__ == "__main__": raise SystemExit(main())`.

- [ ] **Step 4: Run unit and CLI tests**

  Run: `python -m pytest domains/traffic/contracts/tests/test_validate_singular_test_dependency_manifest.py -q`

  Expected: PASS; valid artifact returns `0`, each malformed artifact returns `1` without a traceback.

- [ ] **Step 5: Commit the validator**

  ```bash
  git add domains/traffic/contracts/scripts/validate_singular_test_dependency_manifest.py \
          domains/traffic/contracts/tests/test_validate_singular_test_dependency_manifest.py \
          domains/traffic/tests/test_current_state_contract.py
  git commit -m "test(traffic): validate singular test manifest graph"
  ```

### Task 3: Document and execute fresh-artifact integration verification

**Files:**
- Modify: `domains/traffic/docs/dbt_contracts.md`

**Interfaces:**
- Consumes: the validator CLI from Task 2 and a run-specific fresh target path.
- Produces: a reproducible dev-only verification sequence and a concise incident lesson.

- [ ] **Step 1: Add the dbt contract verification procedure**

  Document this exact order, with `<fresh-target>` outside tracked project
  files and a concrete example such as `/tmp/traffic-graph-<timestamp>`:

  ```bash
  dbt deps
  dbt parse --no-partial-parse --target-path <fresh-target> \
    --vars '{"traffic_snapshot_dag_run_id":"<publishable-run-id>"}'
  python domains/traffic/contracts/scripts/validate_singular_test_dependency_manifest.py \
    --manifest <fresh-target>/manifest.json
  dbt test --select gold_traffic_incident_summary \
    assert_gold_traffic_counts_match_silver \
    assert_gold_traffic_row_counts_positive \
    --target-path <fresh-target>-gold-test \
    --vars '{"traffic_snapshot_dag_run_id":"<publishable-run-id>"}'
  ```

  State that the validator is a graph/deployment gate, while the final dbt test
  is a data-contract gate; neither result substitutes for the other.

- [ ] **Step 2: Record the incident boundary in dbt documentation**

  Add a short note to `domains/traffic/docs/dbt_contracts.md`: isolated per-task targets can still
  yield malformed singular-test graphs, so a “full parse” log is not evidence
  that manifest dependencies are valid. Record the exact #164 scope boundary:
  dbt declarations/validation here; Airflow preflight and runtime upgrades
  separately.

- [ ] **Step 3: Run all deterministic tests**

  Run:

  ```bash
  python -m pytest domains/traffic/tests domains/traffic/contracts/tests -q
  ```

  Expected: PASS with no modified tracked files beyond this issue's scope.

- [ ] **Step 4: Run the dev container integration gate**

  Copy or mount this isolated worktree into the existing dev dbt/Airflow
  container without changing its compose mounts. From that copy, run the Step
  1 commands against a new `/tmp/traffic-graph-<timestamp>` target and the
  publishable snapshot used by the failed run. Capture only command summaries,
  status counts, manifest path, and dev catalog/schema; never print secrets.

  Expected: fresh parse succeeds, validator prints PASS, and all eight selected
  Gold tests pass with zero failing rows.

- [ ] **Step 5: Commit documentation and verification record**

  ```bash
  git add domains/traffic/docs/dbt_contracts.md
  git commit -m "docs(traffic): document singular test graph verification"
  ```

### Task 4: Review, publish, and close the issue

**Files:**
- Modify: `docs/superpowers/plans/2026-07-13-traffic-singular-test-dependency-graph.md` (check completed steps only)

**Interfaces:**
- Consumes: all commits and verification evidence from Tasks 1-3.
- Produces: a dev-base PR linked to #164 and a closure update only after merge.

- [ ] **Step 1: Inspect scope and run final checks**

  Run:

  ```bash
  git status --short
  git diff origin/dev...HEAD --check
  python -m pytest domains/traffic/tests domains/traffic/contracts/tests -q
  ```

  Expected: only #164 files changed; diff check and tests pass.

- [ ] **Step 2: Create a Korean PR using the common template**

  Base the PR on `dev`. Use the title:

  ```text
  fix(traffic): singular test 의존성 그래프 누락을 계약으로 차단
  ```

  In the UTF-8 template body, link `Fixes #164`, list the eleven tests, record
  validator negative cases, fresh target path pattern, selected Gold test
  status, no table/schema/data changes, and the explicit out-of-scope runtime
  follow-up.

- [ ] **Step 3: Verify PR metadata and merge eligibility**

  Confirm title/body rendering, `dev` base, diff scope, required checks, and
  absence of unresolved review comments. Merge only after all are green and
  authorization still covers the merge.

- [ ] **Step 4: Merge and close #164**

  After merge, close #164 with the PR link and final validation evidence.
  Notify the user that the parser graph gate is merged; do not claim an
  Airflow preflight or dbt version upgrade was delivered by this issue.

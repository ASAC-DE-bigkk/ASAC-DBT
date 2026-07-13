# Traffic Canonical Current-Hour Gold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 최신 pinned complete Traffic snapshot을 canonical 행정동 × 평가 hour grain으로 게시하고 zero와 불완전 evidence를 fail-closed로 구분한다.

**Architecture:** manifest·request-audit·Bronze/current 양방향 reconciliation으로 snapshot state를 한 번 판정한 뒤 `asac_axes.dim_admin_dong` scaffold에 current count를 결합한다. complete 상태에서만 0을 허용하고 다른 상태는 count null과 명시적 quality state를 게시한다.

**Tech Stack:** dbt-core 1.10.22, dbt-trino 1.10.2, Trino 482, Iceberg dev catalog, pytest 9, Docker/Airflow.

## Global Constraints

- 모든 변경은 `domains/traffic/**` 안에 둔다.
- prod, full-refresh, backfill, destructive delete를 사용하지 않는다.
- `traffic_snapshot_dag_run_id` pinned correctness와 기존 summary/recovery 의미를 유지한다.
- dev output은 고유 `TRAFFIC_SCHEMA`와 `--threads 1`을 사용한다.
- count 0은 complete evidence에서만 허용한다.

---

### Task 1: RED 계약과 graph shape

**Files:**
- Create: `domains/traffic/tests/test_canonical_gold_contract.py`
- Create: `domains/traffic/tests/assert_gold_traffic_current_by_admin_dong_hourly_grain_unique.sql`
- Create: `domains/traffic/tests/assert_gold_traffic_current_by_admin_dong_hourly_snapshot_reconciles.sql`
- Create: `domains/traffic/tests/assert_gold_traffic_current_by_admin_dong_hourly_admin_stamp_exact.sql`
- Create: `domains/traffic/tests/assert_gold_traffic_current_by_admin_dong_hourly_hourly_completeness.sql`
- Create: `domains/traffic/tests/assert_gold_traffic_current_by_admin_dong_hourly_zero_requires_complete.sql`
- Create: `domains/traffic/tests/assert_gold_traffic_current_by_admin_dong_hourly_fanout_reconciles.sql`
- Modify: `domains/traffic/contracts/scripts/validate_singular_test_dependency_manifest.py`
- Modify: `domains/traffic/contracts/tests/test_validate_singular_test_dependency_manifest.py`

**Interfaces:**
- Consumes: planned model `gold_traffic_incident_current_by_admin_dong_hourly`.
- Produces: static and dbt data gates for all required invariants.

- [ ] **Step 1: Write the failing static contract**

Require the model file to exist and contain these exact dependencies:

```python
assert "var('traffic_snapshot_dag_run_id')" in sql
assert "ref('silver_seoul_traffic_incident_current')" in sql
assert "ref('asac_axes', 'dim_admin_dong')" in sql
assert "source('traffic_bronze', 'collection_run_manifest')" in sql
assert "source('traffic_bronze', 'seoul_traffic_incident_request_audit')" in sql
assert "source('traffic_bronze', 'seoul_traffic_incident')" in sql
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest domains/traffic/tests/test_canonical_gold_contract.py -q`

Expected: FAIL because the model does not exist.

- [ ] **Step 3: Add singular SQL gates and validator mappings**

Each test returns violation rows and declares its model refs in `-- depends_on`. The graph validator must expect the new Gold and current model edges; canonical tests also depend on `model.asac_axes.dim_admin_dong` through SQL.

- [ ] **Step 4: Run graph RED**

Run: `dbt parse --target dev --no-partial-parse --vars '{"traffic_snapshot_dag_run_id":"contract-red"}'`

Expected: FAIL because the referenced Gold model is absent.

### Task 2: Minimal canonical Gold implementation

**Files:**
- Create: `domains/traffic/models/gold/gold_traffic_incident_current_by_admin_dong_hourly.sql`
- Modify: `domains/traffic/models/sources.yml`

**Interfaces:**
- Consumes: pinned run var, manifest/audit/Bronze sources, current Silver, canonical dim.
- Produces: one row per canonical admin dong and evaluation hour.

- [ ] **Step 1: Declare manifest evidence columns**

Add `expected_rows`, `actual_rows`, `expected_raw_objects`, `actual_raw_objects`, and `failure_reason` descriptions to the Traffic manifest source without moving freshness off that table.

- [ ] **Step 2: Implement state selection**

Use the ordered predicate below before any count coalesce:

```sql
case
  when manifest_dag_run_id is null or audit_request_count = 0 then 'missing'
  when api_failure_count > 0 then 'api_failure'
  when not (status = 'SUCCESS' and is_publishable) then 'partial'
  when expected_rows is distinct from actual_rows then 'partial'
  when expected_raw_objects is distinct from actual_raw_objects then 'partial'
  when audited_row_count is distinct from expected_rows then 'partial'
  when missing_current_count > 0 or extra_current_count > 0 then 'current_mismatch'
  when unmapped_incident_count > 0 then 'spatial_mapping_incomplete'
  when expected_rows = 0 then 'complete_zero'
  else 'complete'
end as quality_state
```

- [ ] **Step 3: Scaffold and publish counts**

Join mapped current counts to canonical dim and use:

```sql
case when quality_state in ('complete', 'complete_zero')
     then coalesce(mapped_incident_count, 0)
     else cast(null as bigint)
end as incident_count
```

- [ ] **Step 4: Run GREEN static/parse/compile**

Run the Task 1 pytest, then fresh `dbt parse` and `dbt compile --select gold_traffic_incident_current_by_admin_dong_hourly`.

Expected: all exit 0.

### Task 3: Public schema contract

**Files:**
- Modify: `domains/traffic/models/schema.yml`

**Interfaces:**
- Consumes: the exact physical column order from Task 2.
- Produces: public Gold v1 metadata and column tests.

- [ ] **Step 1: Add model metadata**

Declare `visibility: published_producer`, `contract_status: dev_pending`, natural grain, KST time roles, canonical five-field stamp, incident metric zero/null meaning, quality states, run/audit lineage, and the admin-dong many-to-one join test.

- [ ] **Step 2: Parse and validate manifest**

Run:

```text
python domains/traffic/contracts/scripts/validate_public_gold_manifest.py --manifest $ArtifactRoot/parse/manifest.json --resource gold_traffic_incident_current_by_admin_dong_hourly --require-language ko-KR
```

Expected: `status=PASS` for the new resource.

### Task 4: Dev data proof and regressions

**Files:**
- Verify only: `domains/traffic/**`

**Interfaces:**
- Consumes: latest complete publishable run ID and isolated `TRAFFIC_SCHEMA`.
- Produces: dbt/Trino evidence and run_results artifacts.

- [ ] **Step 1: Prepare isolated runtime**

Use the live Airflow dbt venv, mount this worktree into a one-off container, set `DBT_TARGET=dev`, `ASK_SEOUL_SCHEMA=weather_traffic_bronze`, unique `TRAFFIC_SCHEMA`, and `--threads 1`.

- [ ] **Step 2: Required dbt commands**

Run `dbt deps`, fresh parse, target compile, upstream/current/new+existing Gold run, target+Traffic tests, and recovery run/test without `--full-refresh`.

- [ ] **Step 3: Negative state fixtures**

In separate run-scoped source/target schemas, execute complete-zero, missing, partial, and API-failure cases. Assert complete-zero has 426 zero rows and every invalid case has 426 null-count rows with the expected state.

- [ ] **Step 4: Final Trino proofs**

Query grain duplicates, canonical stamp mismatches, expected row count, count reconciliation, zero violations, fan-out, final rows, and query stats.

### Task 5: Documentation, verification, and publish

**Files:**
- Modify: `domains/traffic/docs/dbt_contracts.md`
- Create: `domains/traffic/docs/retrospectives/2026-07-14-traffic-canonical-gold-dev-validation.md`

**Interfaces:**
- Consumes: exact Task 4 outputs.
- Produces: reproducible proxy-cost report and PR evidence.

- [ ] **Step 1: Record evidence**

Record commands, PASS/FAIL/NOT_RUN, run schema, snapshot ID, row counts, wall/Trino time, processed rows/bytes, final rows, retries, and explicitly label them as cost proxies rather than actual cost.

- [ ] **Step 2: Final verification**

Run fresh pytest in Linux, dbt parse/compile/run/test, graph/public contract validators, `git diff --check`, scoped status/diff, and redacted gitleaks or a documented NOT_RUN reason.

- [ ] **Step 3: Commit and draft PR**

Stage only `domains/traffic/**`, commit with Issue #172, push the current branch, and create a UTF-8 template-based Korean draft PR to `dev`. Verify the rendered body with `gh pr view`; do not merge.

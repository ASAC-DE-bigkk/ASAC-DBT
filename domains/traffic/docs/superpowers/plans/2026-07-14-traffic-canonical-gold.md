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
- Create: `domains/traffic/tests/assert_gold_traffic_current_by_admin_dong_hourly_admin_join_reconciles.sql`
- Create: `domains/traffic/tests/assert_gold_traffic_current_by_admin_dong_hourly_hourly_completeness.sql`
- Create: `domains/traffic/tests/assert_gold_traffic_current_by_admin_dong_hourly_product_row_id_reproducible.sql`
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

Each test returns violation rows and declares its model refs in `-- depends_on`. Snapshot reconciliation independently reads the pinned manifest, request audit, Bronze IDs, current relation, and canonical dim; it derives the expected state/evidence rather than trusting Gold's own state. The graph validator requires the exact Traffic-model edge set and separately requires `model.asac_axes.dim_admin_dong` as a subset edge for canonical tests while allowing other source/external nodes.

- [ ] **Step 4: Run graph RED**

Run:

```text
dbt parse --target dev --no-partial-parse --target-path target/contract-red --vars '{"traffic_snapshot_dag_run_id":"contract-red"}'
python contracts/scripts/validate_singular_test_dependency_manifest.py --manifest target/contract-red/manifest.json
```

Expected: bare `dbt parse` may warn about the absent Gold ref and still exit 0. The manifest dependency validator is the graph RED assertion and must exit nonzero because the required singular-test node/edges cannot be present until the Gold model exists.

Observed in an isolated scheduler `/tmp` copy on 2026-07-14 (no relation run/query):

```text
dbt deps
exit 0 — Installed from <local @ ../../packages/asac_axes>

dbt parse ... --target-path target/contract-red-final-review3
exit 0 — WARNING: ... depends on a node named
'gold_traffic_incident_current_by_admin_dong_hourly' ... which was not found

python contracts/scripts/validate_singular_test_dependency_manifest.py \
  --manifest target/contract-red-final-review3/manifest.json
exit 1 — ERROR: assert_gold_traffic_current_by_admin_dong_hourly_admin_stamp_exact.sql:
traffic model dependencies differ; expected
['model.traffic.gold_traffic_incident_current_by_admin_dong_hourly']; actual []

isolated static model-existence contract
exit 1 — missing canonical Gold model

Trino 482 empty-current scalar aggregate probe
1 evidence row, 0 row-level mismatches

scoped local pytest
27 passed

after adding the current Gold model to the same isolated copy
dbt parse + dependency validator: exit 0 / PASS
dbt compile --no-populate-cache --no-introspect \
  --select assert_gold_traffic_current_by_admin_dong_hourly_snapshot_reconciles
exit 0 — compiled without relation execution
```

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

Independently derive the following evidence before any count coalesce:

- latest manifest event count and tie count;
- request count, HTTP/result failures, audited rows, reported total, max page end, raw-object parity;
- valid Bronze incident IDs and current bidirectional/null/duplicate/wrong-run/wrong-source differences;
- canonical dim nonempty/non-null/unique contract and unmapped current incidents.

Use the ordered predicate below:

```sql
case
  when manifest_event_count = 0 then 'missing'
  when latest_manifest_event_count <> 1 then 'partial'
  when clear_api_failure_count > 0 then 'api_failure'
  when terminal_non_api_failure_count > 0 then 'partial'
  when audit_request_count = 0 then 'missing'
  when parity_failure_count > 0 then 'partial'
  when current_mismatch_count > 0 then 'current_mismatch'
  when canonical_failure_count > 0 or unmapped_incident_count > 0
    then 'spatial_mapping_incomplete'
  when expected_incident_count = 0 then 'complete_zero'
  else 'complete'
end as quality_state
```

`clear_api_failure_count`는 audit HTTP/result failure 또는 latest manifest의 정확한 `HttpProblemError in land_seoul_traffic_raw` / `ParseError in land_seoul_traffic_raw`만 포함한다. terminal failure 판정에서는 `nullif(trim(coalesce(failure_reason, '')), '')`로 빈 문자열을 실패에서 제외한다. 현재 DAG `failure_reason`은 예외 class와 task만 저장하고 일부 TOPIS result/pagination/parse 실패를 모두 `RuntimeError`로 기록하므로, ambiguous `RuntimeError`는 `api_failure`로 추정하지 않고 `partial`로 둔다. 정확한 API 분류에는 ASAC-DAG가 redacted `failure_kind`를 구조화해 manifest에 추가하는 후속 계약이 필요하다.

latest manifest tie는 항상 `partial`이지만, 게시 evidence는 모델과 같은 `event_at`, `status`, `is_publishable`, `expected_rows`, `actual_rows`, `expected_raw_objects`, `actual_raw_objects`, `failure_reason`, `dag_run_id`의 `DESC NULLS LAST` 순위 첫 행에서 결정한다. 모든 게시 evidence가 같을 때만 선택 결과도 같으므로 모델과 oracle이 동일한 deterministic tie-break를 유지한다. audit parity는 `request_params_json`, `payload_hash`, `result_msg`, `load_date`, `dag_run_id` 필수값, positive `start_index`, page range, duplicate `(start_index, end_index)`까지 독립 검사한다.

모든 Gold row는 selected latest manifest의 nullable `expected_rows`를 `expected_incident_count`로, audit `row_count` 합계를 `audited_row_count`로, audit 최대 `end_index`를 `max_page_end_index`로, deterministic dedup current가 canonical dim에 exact join되지 않은 행 수를 `unmapped_incident_count`로 동일하게 게시한다. raw current의 null/duplicate/run/source mismatch 검사는 별도로 유지한다. 정상 unique latest에서는 이 값이 곧 unique latest manifest evidence다. `snapshot_as_of_at`은 `complete|complete_zero`에서만 audit의 최신 `collected_at`을 UTC에서 KST로 변환해 게시하고, 나머지 상태에서는 null이다. `status_observed_at`은 manifest event KST 또는 manifest가 없을 때 공통 `published_at`이고, `hour_at`은 그 값의 hour truncation이며 모든 Gold row가 동일한 non-null `published_at`/`hour_at` 한 값을 가져야 한다. current mismatch 증거는 `GROUP BY` 없는 scalar aggregate로 계산하여 current가 비어 있어도 정확히 1행을 유지하고, cross join 양쪽의 동명 컬럼은 relation-qualified reference만 사용한다.

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

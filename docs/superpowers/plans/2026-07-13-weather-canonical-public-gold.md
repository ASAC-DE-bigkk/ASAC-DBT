# Weather Canonical Public Gold and Bounded Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver issue #165 as an additive canonical Weather public Gold plus a fail-closed, bounded, non-destructive DEV repair path.

**Architecture:** Recover validated publishable runs into W1 observation/Grid, then derive the latest admin-dong forecast through an explicit bridge version and the current common dimension. Reconcile Gold with one custom atomic Iceberg MERGE that supports bounded stale deletion, no forecast-lineage downgrade, and latest canonical restamping.

**Tech Stack:** dbt Core 1.10.22, dbt-trino 1.10.2, Trino/Iceberg, Jinja SQL macros, pytest, GitHub Actions.

## Global constraints

- Work only in `domains/weather/` and `docs/superpowers/`.
- Preserve the four legacy compatibility SQL files byte-for-byte.
- Use `iceberg_dev` only; never use prod, full refresh, R2 deletion, or an unbounded shared build.
- Repair window is KST timestamp(6), at most 24 hours, with explicit bridge v1.
- Keep A1 orchestration and generic Traffic recovery out of this branch.

### Task 1: Lock the W2 source contract in failing tests

**Files:**
- Create: `domains/weather/tests/test_weather_w2_contract.py`
- Test: `domains/weather/tests/test_incremental_materialization_contract.py`
- Test: `domains/weather/tests/test_weather_v2_contract.py`

- [ ] Record SHA-256 baselines for the four protected SQL files.
- [ ] Add static tests for exact vars/guards, W1 normal-vs-repair branches, custom strategy shape, one-MERGE/no-pre-delete safety, Gold refs/schema/winner/row-id, public metadata, named tests, docs selectors, and protected hashes.
- [ ] Run the new file and observe RED because W2 artifacts are absent.

### Task 2: Implement fail-closed W2 inputs and evidence validation

**Files:**
- Create: `domains/weather/macros/weather_w2_contract.sql`
- Modify: `domains/weather/macros/weather_v2_contract.sql`
- Modify: `domains/weather/models/silver/silver_kma_vilage_fcst_observation.sql`
- Modify: `domains/weather/models/silver/silver_kma_vilage_fcst_grid.sql`

- [ ] Validate normal/repair mode, exact timestamp(6) vars, 24-hour bound, explicit bridge v1, DEV catalog/schema, and no full refresh.
- [ ] Validate latest manifest state at cutoff and manifest/Bronze row/raw-object completeness before DML.
- [ ] Preserve the normal 30-minute observation/Grid predicates exactly.
- [ ] Add bounded anchor-run observation recovery and Grid anti-downgrade selection.
- [ ] Allow W1 first build only for existing isolated smoke or validated bounded shared DEV repair.
- [ ] Re-run Task 1 tests until the repair contract is GREEN.

### Task 3: Implement the public Gold and atomic reconciliation

**Files:**
- Create: `domains/weather/models/gold/gold_weather_forecast_by_admin_dong.sql`
- Modify: `domains/weather/macros/weather_w2_contract.sql`

- [ ] Configure incremental `weather_w2_reconcile`, natural unique key, schema-change failure, temp table, and full-refresh prohibition.
- [ ] Directly ref Grid, bridge, and `asac_axes.dim_admin_dong`; select only explicit bridge v1 and current exact canonical codes.
- [ ] Produce the exact 27 columns, timestamp(6)-safe `product_row_id`, value semantics, and raw/run/request lineage.
- [ ] Choose one product row using the required four-field winner prefix and stable terminal order.
- [ ] Add incremental current-dimension restamp candidates so every retained target row has the latest canonical descriptive stamp; in repair, keep these candidates outside the stale-delete window only.
- [ ] Generate one atomic MERGE with derived upsert/delete actions, bounded stale deletion, actual-difference no-op behavior, latest canonical restamp, and no forecast-lineage downgrade.
- [ ] Fail before repair MERGE for zero in-window expected rows, null/duplicate expected grain, or duplicate target grain; allow an empty normal temp as a no-op.
- [ ] Run static tests and compile the model in a Linux dbt runtime.

### Task 4: Declare the v1 public contract

**Files:**
- Modify: `domains/weather/models/schema.yml`
- Modify: `domains/weather/contracts/docs/public-gold-ai-contract-v1.md`
- Modify: `domains/weather/docs/dbt_contracts.md`

- [ ] Add all 27 typed columns with Korean descriptions and `config.meta` semantics/nullability.
- [ ] Declare `published_producer`, no live exposure, exact anchor universe, four time roles, canonical five-field stamp, empty metrics, dimension join, seven representation states, lineage, and active lifecycle.
- [ ] Update validator commands to target `gold_weather_forecast_by_admin_dong` and document latest-revision/restamp and 425-current-join caveats.
- [ ] Document repair vars, boundaries, selector, failure behavior, A1 handoff, and DEV evidence fields.
- [ ] Run source linter and a fresh manifest validator; observe and fix any declaration errors.

### Task 5: Add direct-dependency and data reconciliation tests

**Files:**
- Create: `domains/weather/tests/assert_gold_weather_forecast_by_admin_dong_grain_unique.sql`
- Create: `domains/weather/tests/assert_gold_weather_forecast_by_admin_dong_product_row_id_reproducible.sql`
- Create: `domains/weather/tests/assert_gold_weather_forecast_by_admin_dong_latest_grid_record.sql`
- Create: `domains/weather/tests/assert_gold_weather_forecast_by_admin_dong_admin_stamp_exact.sql`
- Create: `domains/weather/tests/assert_gold_weather_forecast_by_admin_dong_admin_revision_exact.sql`
- Create: `domains/weather/tests/assert_gold_weather_forecast_by_admin_dong_admin_join_reconciles.sql`
- Create: `domains/weather/tests/assert_gold_weather_forecast_by_admin_dong_bridge_exclusions_reconcile.sql`
- Create: `domains/weather/tests/assert_gold_weather_forecast_by_admin_dong_repair_reconciles.sql`
- Create: `domains/weather/tests/assert_gold_weather_forecast_by_admin_dong_repair_no_downgrade.sql`

- [ ] Put explicit `-- depends_on:` hints at the top of every singular test that participates in metadata validation.
- [ ] Make the three metadata-named tests depend directly and uniquely on Gold in a fresh manifest.
- [ ] Compare expected and actual full rows in both directions inside the same repair boundary.
- [ ] Keep repair-only assertions empty/no-op in normal mode while still parsing and depending on Gold.
- [ ] Run `dbt parse --no-partial-parse`, inspect manifest dependencies, and run the contract validator.

### Task 6: Prove behavior in isolated/shared DEV

**Files:**
- Modify: `domains/weather/docs/dbt_contracts.md` with non-sensitive evidence only.

- [ ] Copy the branch to the Linux Airflow/dbt runtime and run `dbt deps`, parse, ls exact selector, and compile.
- [ ] Run the Windows-compatible pytest subset and the complete suite in Linux.
- [ ] Run an approved bounded `iceberg_dev.weather` seed/model/test sequence using one complete publishable manifest window; do not full-refresh.
- [ ] Run the identical cutoff a second time and compare row count, grain, winner, canonical stamp, and fingerprint.
- [ ] Verify current dimension coverage truthfully (426 dim, 425 bridge-v1 joins) and record excluded mappings.
- [ ] Generate a real DEV catalog and compare declared column names, types, and order.
- [ ] Mark any fixture-only or A1-owned failure-injection evidence separately as `NOT_RUN`.

### Task 7: Review and publish

- [ ] Run an independent code review for spec compliance, SQL safety, contract truthfulness, and regression risk.
- [ ] Fix all P0/P1 findings and rerun fresh verification: tests, dbt commands, catalog/manifest validators, `git diff --check`, protected hashes, and secret scan.
- [ ] Stage only intended paths, commit with issue reference, push the feature branch, and open a draft PR to `dev` using the shared UTF-8 template.
- [ ] Verify PR Korean text, base/head, commit SHA, changed files, and checks. Leave merge to the user.

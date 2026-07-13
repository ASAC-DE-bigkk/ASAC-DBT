# Weather Incremental Lookback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make both legacy Weather Silver MERGE models replay the last 30 minutes of `collected_at` without changing their grains.

**Architecture:** Reuse the validated lookback macro as a numeric interval only. Preserve MERGE/unique-key behavior, then lock the SQL and documentation contract with source-level regression tests and dev dbt validation.

**Tech Stack:** dbt Core 1.10, dbt-trino, Trino/Iceberg, pytest.

## Global Constraints

- Modify only `domains/weather/` plus this planning artifact.
- No W1 isolated candidate guard is called by the legacy operating models.
- Keep each existing unique key unchanged.
- Use dev target only; do not run full-refresh or prod writes.

### Task 1: Lock the legacy model contract

**Files:**
- Create: `domains/weather/tests/test_incremental_lookback_contract.py`
- Modify: `domains/weather/models/silver/silver_kma_vilage_fcst.sql`
- Modify: `domains/weather/models/silver/silver_weather_forecast_by_admin_dong.sql`

- [ ] Write tests asserting both models call `weather_w1_lookback_minutes()`, use inclusive `>=`, subtract an interval, and retain their exact unique-key declarations.
- [ ] Run the new tests and observe failure because neither legacy model uses the macro.
- [ ] Replace each strict watermark with the macro-backed inclusive replay predicate.
- [ ] Re-run the tests.

### Task 2: Align operating documentation

**Files:**
- Modify: `domains/weather/docs/dbt_contracts.md`

- [ ] Add a failing source-contract assertion for the 30-minute replay policy and legacy-model scope.
- [ ] Update the materialization section to describe both model keys, inclusive 30-minute replay, and explicit repair for arrivals older than the window.
- [ ] Run the contract tests.

### Task 3: Validate and publish

- [ ] Run Weather tests, dbt parse/compile, and scoped dev `dbt run/test` twice.
- [ ] Inspect the selected relations and duplicate-grain tests after the second pass.
- [ ] Commit, push, open a dev-base PR, merge after checks, and close #140 with the evidence.

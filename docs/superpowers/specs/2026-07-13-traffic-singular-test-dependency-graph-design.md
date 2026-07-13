# Traffic singular test dependency graph design

## Context

On 2026-07-13, `traffic_incident_transform` failed in `dbt_test_gold` after
`dbt_run_gold` had completed. The failed task's `manifest.json` recorded empty
`depends_on.nodes` arrays for every traffic singular test. dbt therefore raised
compilation errors for the two selected Gold tests instead of returning failing
data rows:

- `assert_gold_traffic_counts_match_silver` could not resolve its Silver and
  Gold `ref()` dependencies.
- `assert_gold_traffic_row_counts_positive` could not resolve its Gold `ref()`
  dependency.

The same pinned Bronze snapshot passed all eight selected Gold tests when
re-run in a new target directory. The failure is consequently not a Silver or
Gold data-contract violation. It is an intermittent parser/manifest graph
failure that must fail the transform but must also be prevented from reaching
the post-materialization Gold test phase.

The failed task logged `saved manifest not found; starting full parse`, so
turning partial parsing off alone cannot be the corrective action. The runtime
uses dbt-core 1.10.22 and dbt-trino 1.10.2; a runtime version upgrade remains a
separate compatibility project.

## Scope

This ASAC-DBT change makes the dependency graph encoded by traffic singular
tests deterministic and reviewable. It covers every production traffic
singular test that uses `ref()` and is part of the normal transform contract.
It does not change model SQL, Silver/Gold semantics, snapshot selection,
Bronze data, schedules, or recovery-only tests.

Airflow preflight gating and dbt runtime upgrades are explicitly out of scope:
they belong to ASAC-DAG/platform work because this repository cannot make
Airflow invoke an additional command or select a container image version.

## Options considered

1. Disable partial parsing globally. This is not sufficient: the incident
   occurred after dbt chose a full parse in an empty task target. It would also
   add runtime cost without making hidden graph regressions visible in review.
2. Add hints only to the two failed Gold tests. This makes the immediate error
   less likely but leaves the other normal traffic singular tests exposed to
   the same all-tests-empty manifest state.
3. **Recommended: explicit graph declarations plus a manifest contract.**
   Each relevant singular test declares its model dependencies in dbt's
   supported SQL `depends_on` comment, while repository tests verify both the
   declaration and a parsed manifest's exact expected dependencies. This gives
   dbt a deterministic graph input and gives CI/PR verification a fail-closed
   regression signal.

## Design

### Explicit dependency declarations

Add one SQL comment per model dependency before the body of each affected
singular test:

```sql
-- depends_on: {{ ref('gold_traffic_incident_summary') }}
```

The comments retain the existing inline `ref()` calls. They are graph metadata,
not a SQL rewrite, and must match the exact models referenced by the test body.
The affected normal-transform tests and expected model dependency names are:

| Test | Required model dependencies |
| --- | --- |
| `assert_gold_traffic_counts_match_silver` | `silver_seoul_traffic_incident_current`, `gold_traffic_incident_summary` |
| `assert_gold_traffic_row_counts_positive` | `gold_traffic_incident_summary` |
| `assert_silver_seoul_traffic_incident_grain_unique` | `silver_seoul_traffic_incident` |
| `assert_silver_traffic_admin_axis_consistent` | `silver_seoul_traffic_incident` |
| `assert_silver_traffic_admin_axis_coverage` | `silver_seoul_traffic_incident` |
| `assert_silver_traffic_event_at_matches_occurred_at` | `silver_seoul_traffic_incident` |
| `assert_silver_traffic_latest_publishable_record` | `silver_seoul_traffic_incident` |
| `assert_silver_traffic_location_contract` | `silver_seoul_traffic_incident` |
| `assert_silver_traffic_uses_publishable_runs` | `silver_seoul_traffic_incident` |
| `assert_silver_traffic_wgs84_required_when_source_coordinate_available` | `silver_seoul_traffic_incident` |
| `assert_traffic_current_pinned_publishable_run` | `silver_seoul_traffic_incident_current` |

Source-only availability/audit tests and recovery tests are excluded: they do
not contain a model `ref()` in the normal transform graph. They remain covered
by their existing source/data contracts.

### Graph-contract validator

Add a small Python validator owned by the traffic test package. It receives a
dbt `manifest.json` path and validates the fixed mapping above against the
corresponding singular test nodes:

- every mapped test node exists exactly once;
- `depends_on.nodes` is non-empty;
- it contains exactly the expected `model.traffic.<model>` nodes;
- a missing test, an empty array, or an unexpected/missing node raises a
  non-zero error with the test name and expected/actual nodes.

Keep the mapping in one module so the validator and unit tests use the same
declared contract. The validator must not accept an older manifest, discover a
default target path, or silently skip a missing node. Its caller provides the
fresh target artifact explicitly.

### Regression tests and use

The Python contract tests will verify:

1. each mapped SQL test has matching `-- depends_on: {{ ref(...) }}` comments
   and still contains the corresponding inline `ref()`;
2. a representative valid manifest passes the validator;
3. empty, missing, and mismatched dependency graphs fail the validator.

PR and dev verification will generate a new artifact, never reuse Airflow's
previous target:

```text
dbt deps
dbt parse --no-partial-parse --target-path <fresh-target>
python -m domains.traffic.tests.validate_singular_test_manifest \
  --manifest <fresh-target>/manifest.json
```

The final selected Gold `dbt test` remains the data-contract verification. The
new graph validator intentionally classifies a malformed manifest before that
test can be mistaken for a data-quality failure.

## Failure handling

The validator exits non-zero for graph failures and prints the exact singular
test plus expected and actual node IDs. It does not retry, mutate target files,
or query Trino. That makes parser graph defects actionable as deployment/test
contract failures rather than as Gold data failures.

## Acceptance criteria

- All eleven normal-transform singular tests above have correct explicit model
  dependency comments.
- The validator fails closed for missing, empty, or mismatched graph nodes.
- A newly generated no-partial-parse manifest passes the validator.
- The existing traffic Python contract suite and selected dev Gold test pass.
- No Silver/Gold model SQL, schema, or data semantics change.

## Verification and rollback

Run unit tests first, then `dbt deps`, fresh-target `dbt parse
--no-partial-parse`, the manifest validator, and the selected Gold test against
the same dev pinned snapshot. Rollback is limited to reverting the ASAC-DBT
commit: no data migration, state mutation, or runtime configuration change is
introduced.

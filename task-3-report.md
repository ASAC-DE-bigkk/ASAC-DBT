# Task 3 report — dbt documentation and fresh-artifact verification

## Scope

- Added the #164 singular-test dependency graph verification procedure to
  `domains/traffic/docs/dbt_contracts.md`.
- The procedure requires a dev-only, fresh target outside tracked project
  files, a pinned `traffic_snapshot_dag_run_id`, `dbt deps`, a
  no-partial-parse manifest, the manifest validator, and selected Gold tests.
- It distinguishes the manifest validator's graph/deployment gate from the
  Gold tests' data-contract gate, and records the boundary: dbt declarations
  and validation are in #164; Airflow preflight and dbt runtime upgrades are
  separate work.
- No compose, mount, model SQL, schema, or runtime configuration was changed.

## Verification evidence

### Deterministic Python suite

Command run from this checkout:

```bash
python -m pytest domains/traffic/tests domains/traffic/contracts/tests -q
```

Result on the Windows host: 101 passed; 11 failed (with 253 subtests passed).
Every failure occurred before project assertions while tests attempted to
create Windows symlinks and received `WinError 1314` (developer-mode/symlink
privilege unavailable). The failures are in pre-existing public-gold manifest
symlink-safety cases; no assertion identified a traffic graph or documentation
regression. The existing Airflow image does not include `pytest`, so the full
Python suite could not be repeated inside that Linux container.

### Fresh dev dbt artifact

The existing `elt-infra-airflow-scheduler-1` container was used without
changing its compose configuration or mounted checkout. To test this branch
without mutating that mount, a temporary `/tmp/traffic164-dbt` copy received
the branch's traffic test contracts, validator, and documentation. The
temporary dbt targets were `/tmp/traffic164-graph` and
`/tmp/traffic164-gold`.

The pinned publishable Bronze snapshot resolved from the dev manifest was:

```text
scheduled__2026-07-13T08:25:00+00:00
```

Commands (with the temporary traffic project as the dbt working directory):

```bash
dbt deps --target dev --no-use-colors
dbt parse --no-partial-parse --target dev --no-use-colors \
  --target-path /tmp/traffic164-graph \
  --vars '{"traffic_snapshot_dag_run_id":"scheduled__2026-07-13T08:25:00+00:00"}'
python contracts/scripts/validate_singular_test_dependency_manifest.py \
  --manifest /tmp/traffic164-graph/manifest.json
dbt test --select gold_traffic_incident_summary \
  assert_gold_traffic_counts_match_silver \
  assert_gold_traffic_row_counts_positive \
  --target dev --no-partial-parse --no-use-colors \
  --target-path /tmp/traffic164-gold \
  --vars '{"traffic_snapshot_dag_run_id":"scheduled__2026-07-13T08:25:00+00:00"}'
```

Results:

- `dbt deps`: passed; installed local `asac_axes`.
- `dbt parse --no-partial-parse`: passed; wrote a new manifest under
  `/tmp/traffic164-graph`.
- Manifest validator: passed (`traffic singular-test dependency manifest is valid`).
- Selected Gold dbt test: passed, 8/8 tests, 0 warnings and 0 errors. This
  includes both selected singular tests and the Gold model's selected schema
  tests.

The first combined runtime invocation used the repository-root validator path
after changing into the dbt project directory; it failed only because that
relative path did not exist from that working directory. Re-running with the
project-relative validator path above passed against the already fresh
manifest. This did not change source, mounted files, secrets, or warehouse
data.

## Concerns / follow-up

- Enable Windows Developer Mode or grant symlink creation privilege to make
  the complete host Python suite portable; this is an environment limitation,
  not a code-test failure.
- The temporary `/tmp/traffic164-*` paths are container-only test artifacts
  and are not part of the repository or mounted checkout.

# Weather Canonical Public Gold and Bounded Repair Design

## Goal

Publish an additive Weather Gold that other domains can join on the common administrative-dong axis, and provide a bounded DEV repair path that can recover publishable KMA data older than the normal 30-minute lookback without full refresh or lineage downgrade.

The product relation is `gold_weather_forecast_by_admin_dong`. Its natural grain is:

```text
admin_dong_code × forecast_at × category
```

## Protected intent and scope

W1 deliberately introduced observation history, native Grid Silver, and a versioned grid-to-admin-dong bridge as internal candidates while leaving the four legacy compatibility SQL files unchanged. W2 owns the new public grain, latest-issued winner, bidirectional stale reconciliation, and explicit-cutoff no-downgrade repair. This change preserves that split.

The following SQL files remain byte-identical:

- `silver_kma_vilage_fcst.sql`
- `silver_weather_forecast_by_admin_dong.sql`
- `dim_weather_place.sql`
- `gold_weather_forecast_by_place.sql`

Airflow cutoff capture and propagation, writer serialization, task ordering, retry/callback behavior, failure injection, and rollout remain A1 work. Generic Traffic recovery mechanics and destructive full refresh are outside this issue.

## Canonical spatial policy

The Gold SQL directly references all three producer relations:

- `silver_kma_vilage_fcst_grid`
- `bridge_weather_admin_dong_grid`
- `ref('asac_axes', 'dim_admin_dong')`

The bridge supplies the explicit mapping assertion from KMA `nx, ny` to `source_admin_code`. The only accepted active version is `weather_admin_dong_grid_bridge_v1`; lexicographic maximum, recorded time, or revision-label inference is forbidden.

The current `asac_axes.dim_admin_dong` snapshot is authoritative at each execution. Gold joins `bridge.source_admin_code` to that dimension and projects:

```text
admin_dong_code
admin_dong
gu_code
gu
cast(revision_date as date) as admin_dong_revision_date
```

This is a latest-revision product, not a historically pinned canonical snapshot. A repair may therefore update the descriptive canonical stamp while preserving a newer forecast/value/raw lineage already in the target.

The anchor universe is the intersection of the explicit bridge v1, the latest canonical dimension, and publishable Grid facts. It is not all 426 current Seoul administrative dongs. Current DEV evidence shows 425 bridge-v1 codes join the latest dimension: legacy `신설동` and `용두동` candidates do not join, and current `용신동` has no v1 candidate. Unmatched candidates stay visible in the bridge but never enter public Gold.

## Product schema and winner

The exact 27-column order is:

```text
product_row_id, admin_dong_code, forecast_at, category,
admin_dong, gu_code, gu, admin_dong_revision_date,
bridge_version, nx, ny, source_grid_place_id,
issued_at, collected_at, published_at,
fcst_value_raw, fcst_value_num, value_representation,
value_num, value_lower_bound, value_upper_bound, qualitative_code,
forecast_lead_hours, source_id, dag_run_id, raw_object_key, request_id
```

`product_row_id` is deterministic and preserves timestamp(6) precision:

```sql
concat(
  admin_dong_code,
  '|',
  to_iso8601(cast(forecast_at as timestamp(6))),
  '|',
  category
)
```

`date_format(..., '%f')` is not used because Trino truncates that rendering to millisecond precision. The primary key is `product_row_id`; the natural grain remains the three product-question columns.

The required winner prefix is:

```text
issued_at DESC,
collected_at DESC,
raw_object_key DESC,
request_id DESC
```

Stable terminal fields are appended only to make a total order. The same comparison is reused by the incremental no-downgrade logic. Gold forwards Grid value semantics without inventing a generic metric: `metrics` is empty because KMA categories have incompatible units. The seven `value_representation` states remain `explicit_none`, `quantitative_exact`, `quantitative_range`, `bare_numeric`, `qualitative_code`, `missing`, and `unparseable`.

## Normal and repair modes

Normal incremental runs preserve the existing inclusive 30-minute `collected_at` replay behavior. They never bootstrap a missing shared relation.

To make “latest canonical at execution” true for the whole incremental relation, not only newly selected forecasts, an incremental run also selects existing target rows whose descriptive canonical stamp differs from the current dimension. In normal mode those stale-stamp rows are restamp candidates. In repair mode only stale-stamp target rows outside `[start, cutoff]` are added this way; rows inside the repair window must come from the authoritative expected Grid set or be deleted as stale. Restamp candidates retain their forecast, value, bridge, and raw lineage columns exactly.

Repair requires all of the following:

```text
weather_w2_repair_mode=bounded_reconcile
weather_w2_repair_start_at=YYYY-MM-DD HH:MM:SS.ffffff
weather_w2_publishable_cutoff_at=YYYY-MM-DD HH:MM:SS.ffffff
weather_w2_bridge_version=weather_admin_dong_grid_bridge_v1
```

The timestamps are KST timestamp(6) values, `start <= cutoff`, cutoff is not in the future, and the bounded window is at most 24 hours. Repair and shared first build are allowed only for target `dev` in `iceberg_dev.weather`. Any partial setting, malformed value, unknown bridge version, prod target, different catalog/schema, or `--full-refresh` fails closed.

At cutoff, repair first ranks every manifest state up to the cutoff by `(source_id, dag_run_id)` and only then selects the latest state. It does not pre-filter to successful states, which would incorrectly revive a run retracted before the cutoff. Eligible anchor runs have latest state `SUCCESS`, `is_publishable=true`, and publication time inside `[start, cutoff]`.

Before target DML, every anchor must prove:

- `expected_rows = actual_rows > 0`
- `expected_raw_objects = actual_raw_objects > 0`
- Bronze row count equals `actual_rows`
- distinct Bronze `raw_object_key` count equals `actual_raw_objects`
- at least one eligible anchor exists

Failure leaves the target untouched.

## W1 bounded recovery

Observation normal mode keeps the current 30-minute predicate. In bounded repair it instead reads Bronze rows belonging to the validated manifest anchors, allowing an old `collected_at` row to be recovered without an unbounded scan.

Grid bounded repair reads repaired observations whose `published_at` is inside the same window and retains the existing Grid winner order. An incremental anti-downgrade predicate prevents an older repair candidate from overwriting a newer existing Grid winner. Observation and Grid remain history-like MERGE tables; they do not delete stale history.

The W1 initial-build and bridge/seed guards gain one narrow exception: validated bounded repair in `iceberg_dev.weather`. Existing unique isolated smoke mode remains valid. Default shared bootstrap, prod, and full refresh remain blocked.

## Atomic Gold reconciliation

Gold is incremental with custom strategy `weather_w2_reconcile`, `views_enabled=false`, and `on_schema_change='fail'`. dbt-trino therefore creates a temporary table with only the 27 public columns. The custom strategy builds one Trino/Iceberg `MERGE` source:

1. all expected Grid rows and eligible target canonical-restamp rows labeled as upserts;
2. only during repair, target rows with `published_at` inside `[start, cutoff]` whose natural key is absent from temp, labeled as deletes.

The action column exists only in the derived MERGE source so it cannot leak into the physical public schema.

The single statement applies clauses in this order:

1. matched delete sentinel → delete;
2. matched upsert → update only when the forecast winner is not older and a non-canonical value differs, or when a canonical descriptive stamp differs;
3. unmatched upsert → insert.

When the repair source winner is older, forecast, value, mapping lineage, and raw lineage columns stay unchanged; only `admin_dong`, `gu_code`, `gu`, and `admin_dong_revision_date` may be restamped from the latest dimension. Equal rows are no-ops to avoid needless Iceberg snapshot churn.

The stale-delete boundary is reused verbatim by reverse reconciliation:

```text
target.published_at BETWEEN repair_start_at AND publishable_cutoff_at
```

Rows before the start, after the cutoff, or carrying a newer winner cannot be deleted or downgraded. During repair, zero expected rows inside the repair boundary, null/duplicate temp grain, or duplicate target grain raises before MERGE so restamp-only input or an incomplete expected set cannot trigger mass deletion. A normal incremental run may have an empty temp and becomes a no-op.

## Failure and concurrency boundary

- Guard or temp-table creation failure: target unchanged.
- MERGE failure: one Iceberg statement, so the target snapshot is unchanged.
- Temp cleanup failure after a successful MERGE: the task fails, and the next run removes the stale temp relation and converges for the same cutoff.
- Same-cutoff second run: no row, grain, winner, canonical stamp, or fingerprint change.

SQL no-downgrade is a defensive guarantee, but normal/repair writer serialization is not established by W2. A1 must serialize writers before scheduled operation.

## Public contract and proof

The model is declared `visibility=published_producer`, `contract_status=dev_pending`, and `exposure_status=none_no_live_consumer`. It is catalog-visible as a reusable producer but does not claim a live application consumer. Four time roles are explicit in Asia/Seoul: forecast, issue, collection, and publication.

Named spatial/join tests resolve directly to the Gold node in a fresh `dbt parse --no-partial-parse` manifest. Additional tests cover natural grain, row-id reproducibility, exact winner/value lineage, bridge exclusions, bounded bidirectional reconciliation, and no-downgrade. Source lint, manifest validation, physical catalog comparison, scoped data tests, and manual semantic review remain separate evidence classes.

-- depends_on: {{ ref('gold_weather_forecast_by_admin_dong') }}
-- depends_on: {{ ref('bridge_weather_admin_dong_grid') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}
-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}

{% set canonical_contract = weather_w2_canonical_contract() %}

{% if weather_w2_is_repair() %}
with eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),

active_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
),

canonical as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        cast(revision_date as date) as admin_dong_revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),

grid_candidates as (
    select
        cast(grid.nx as integer) as nx,
        cast(grid.ny as integer) as ny,
        cast(grid.source_grid_place_id as varchar) as source_grid_place_id,
        cast(grid.issued_at as timestamp(6)) as issued_at,
        cast(grid.forecast_at as timestamp(6)) as forecast_at,
        cast(grid.category as varchar) as category,
        cast(grid.collected_at as timestamp(6)) as collected_at,
        cast(grid.published_at as timestamp(6)) as published_at,
        cast(grid.fcst_value_raw as varchar) as fcst_value_raw,
        cast(grid.fcst_value_num as double) as fcst_value_num,
        cast(grid.value_representation as varchar) as value_representation,
        cast(grid.value_num as double) as value_num,
        cast(grid.value_lower_bound as double) as value_lower_bound,
        cast(grid.value_upper_bound as double) as value_upper_bound,
        cast(grid.qualitative_code as varchar) as qualitative_code,
        cast(grid.forecast_lead_hours as bigint) as forecast_lead_hours,
        cast(grid.source_id as varchar) as source_id,
        cast(grid.selected_dag_run_id as varchar) as dag_run_id,
        cast(grid.raw_object_key as varchar) as raw_object_key,
        cast(grid.request_id as varchar) as request_id
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    where cast(grid.published_at as timestamp(6))
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(grid.published_at as timestamp(6))
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
),

joined_candidates as (
    select
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        bridge.bridge_version,
        grid.nx,
        grid.ny,
        grid.source_grid_place_id,
        grid.issued_at,
        grid.forecast_at,
        grid.category,
        grid.collected_at,
        grid.published_at,
        grid.fcst_value_raw,
        grid.fcst_value_num,
        grid.value_representation,
        grid.value_num,
        grid.value_lower_bound,
        grid.value_upper_bound,
        grid.qualitative_code,
        grid.forecast_lead_hours,
        grid.source_id,
        grid.dag_run_id,
        grid.raw_object_key,
        grid.request_id
    from grid_candidates as grid
    inner join active_bridge as bridge
        on grid.nx = bridge.nx
       and grid.ny = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
),

ranked_grid_candidate_keys as (
    select
        nx,
        ny,
        forecast_at,
        category,
        issued_at,
        collected_at,
        raw_object_key,
        request_id,
        dag_run_id,
        source_grid_place_id,
        row_number() over (
            partition by nx, ny, forecast_at, category
            order by
                issued_at desc,
                collected_at desc,
                raw_object_key desc,
                request_id desc,
                dag_run_id desc,
                source_grid_place_id desc,
                nx desc,
                ny desc
        ) as product_row_num
    from grid_candidates
),

winning_grid_candidate_keys as (
    select
        nx,
        ny,
        forecast_at,
        category,
        issued_at,
        collected_at,
        raw_object_key,
        request_id,
        dag_run_id,
        source_grid_place_id
    from ranked_grid_candidate_keys
    where product_row_num = 1
),

boundary_expected as (
    select
        concat(
            candidate.admin_dong_code,
            '|',
            to_iso8601(cast(candidate.forecast_at as timestamp(6))),
            '|',
            candidate.category
        ) as product_row_id,
        candidate.admin_dong_code,
        candidate.forecast_at,
        candidate.category,
        candidate.issued_at,
        candidate.collected_at,
        candidate.published_at,
        candidate.source_id,
        candidate.dag_run_id,
        candidate.raw_object_key,
        candidate.request_id,
        candidate.source_grid_place_id,
        candidate.nx,
        candidate.ny,
        to_hex(sha256(to_utf8(json_format(cast(row(
            cast(candidate.admin_dong_code as varchar),
            cast(candidate.forecast_at as timestamp(6)),
            cast(candidate.category as varchar),
            cast(candidate.admin_dong as varchar),
            cast(candidate.gu_code as varchar),
            cast(candidate.gu as varchar),
            cast(candidate.admin_dong_revision_date as date),
            cast(candidate.bridge_version as varchar),
            cast(candidate.nx as integer),
            cast(candidate.ny as integer),
            cast(candidate.source_grid_place_id as varchar),
            cast(candidate.issued_at as timestamp(6)),
            cast(candidate.collected_at as timestamp(6)),
            cast(candidate.published_at as timestamp(6)),
            cast(candidate.fcst_value_raw as varchar),
            cast(candidate.fcst_value_num as double),
            cast(candidate.value_representation as varchar),
            cast(candidate.value_num as double),
            cast(candidate.value_lower_bound as double),
            cast(candidate.value_upper_bound as double),
            cast(candidate.qualitative_code as varchar),
            cast(candidate.forecast_lead_hours as bigint),
            cast(candidate.source_id as varchar),
            cast(candidate.dag_run_id as varchar),
            cast(candidate.raw_object_key as varchar),
            cast(candidate.request_id as varchar)
        ) as json))))) as candidate_payload_hash
    from joined_candidates as candidate
    inner join winning_grid_candidate_keys as winner
        on candidate.nx = winner.nx
       and candidate.ny = winner.ny
       and candidate.forecast_at = winner.forecast_at
       and candidate.category = winner.category
       and candidate.issued_at is not distinct from winner.issued_at
       and candidate.collected_at is not distinct from winner.collected_at
       and candidate.raw_object_key is not distinct from winner.raw_object_key
       and candidate.request_id is not distinct from winner.request_id
       and candidate.dag_run_id is not distinct from winner.dag_run_id
       and candidate.source_grid_place_id is not distinct from winner.source_grid_place_id
)

select
    coalesce(expected.product_row_id, cast(actual.product_row_id as varchar))
        as product_row_id,
    case
        when expected.product_row_id is null then 'unexpected_window_gold_row'
        when actual.product_row_id is null then 'missing_expected_gold_row'
        else 'gold_payload_differs_from_repair_winner'
    end as failure_reason
from boundary_expected as expected
full outer join {{ ref('gold_weather_forecast_by_admin_dong') }} as actual
    on expected.admin_dong_code = cast(actual.admin_dong_code as varchar)
   and expected.forecast_at = cast(actual.forecast_at as timestamp(6))
   and expected.category = cast(actual.category as varchar)
where (
        expected.product_row_id is null
    and cast(actual.published_at as timestamp(6))
        >= timestamp '{{ weather_w2_repair_start_at() }}'
    and cast(actual.published_at as timestamp(6))
        <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
)
or actual.product_row_id is null
or (
    not (
        {{ weather_w2_gold_winner_is_not_older('actual', 'expected') }}
        and not {{ weather_w2_gold_winner_is_not_older('expected', 'actual') }}
        and (
            cast(actual.published_at as timestamp(6))
                < timestamp '{{ weather_w2_repair_start_at() }}'
            or cast(actual.published_at as timestamp(6))
                > timestamp '{{ weather_w2_publishable_cutoff_at() }}'
            or exists (
                select 1
                from eligible_manifest_anchors as anchor
                where anchor.anchor_source_id = cast(actual.source_id as varchar)
                  and anchor.anchor_dag_run_id = cast(actual.dag_run_id as varchar)
            )
        )
    )
    and expected.candidate_payload_hash is distinct from
        to_hex(sha256(to_utf8(json_format(cast(row(
            cast(actual.admin_dong_code as varchar),
            cast(actual.forecast_at as timestamp(6)),
            cast(actual.category as varchar),
            cast(actual.admin_dong as varchar),
            cast(actual.gu_code as varchar),
            cast(actual.gu as varchar),
            cast(actual.admin_dong_revision_date as date),
            cast(actual.bridge_version as varchar),
            cast(actual.nx as integer),
            cast(actual.ny as integer),
            cast(actual.source_grid_place_id as varchar),
            cast(actual.issued_at as timestamp(6)),
            cast(actual.collected_at as timestamp(6)),
            cast(actual.published_at as timestamp(6)),
            cast(actual.fcst_value_raw as varchar),
            cast(actual.fcst_value_num as double),
            cast(actual.value_representation as varchar),
            cast(actual.value_num as double),
            cast(actual.value_lower_bound as double),
            cast(actual.value_upper_bound as double),
            cast(actual.qualitative_code as varchar),
            cast(actual.forecast_lead_hours as bigint),
            cast(actual.source_id as varchar),
            cast(actual.dag_run_id as varchar),
            cast(actual.raw_object_key as varchar),
            cast(actual.request_id as varchar)
        ) as json)))))
)
{% else %}
select cast(null as varchar) as failure_reason
where false
{% endif %}

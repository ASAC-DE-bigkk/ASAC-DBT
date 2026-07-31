{% macro weather_w2_recovery_checkpoint_id() -%}
  {%- set checkpoint_id = var('weather_w2_recovery_checkpoint_id', none) -%}
  {%- if checkpoint_id is none and not execute -%}
    {{ return('parse-only') }}
  {%- endif -%}
  {%- if checkpoint_id is not string
        or checkpoint_id | length < 1
        or checkpoint_id | length > 80
        or modules.re.fullmatch(
            '^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$',
            checkpoint_id
        ) is none -%}
    {{ exceptions.raise_compiler_error(
      'weather_w2_recovery_checkpoint_id must be 1-80 letters, numbers, dot, dash, or underscore.'
    ) }}
  {%- endif -%}
  {{ return(checkpoint_id) }}
{%- endmacro %}

{% macro weather_w2_recovery_target_admin_dong_code() -%}
  {%- set admin_dong_code = var(
      'weather_w2_recovery_target_admin_dong_code',
      none
  ) -%}
  {%- if admin_dong_code is none and not execute -%}
    {{ return('1123053600') }}
  {%- endif -%}
  {%- if admin_dong_code | string != '1123053600' -%}
    {{ exceptions.raise_compiler_error(
      'Weather W2 staged recovery is restricted to Yongsin-dong 1123053600.'
    ) }}
  {%- endif -%}
  {{ return(admin_dong_code | string) }}
{%- endmacro %}

{% macro weather_w2_positive_snapshot_id(var_name) -%}
  {%- set snapshot_id = var(var_name, none) -%}
  {%- if snapshot_id is none and not execute -%}
    {{ return(0) }}
  {%- endif -%}
  {%- if snapshot_id is not integer or snapshot_id <= 0 -%}
    {{ exceptions.raise_compiler_error(
      var_name ~ ' must be a positive Iceberg snapshot ID.'
    ) }}
  {%- endif -%}
  {{ return(snapshot_id) }}
{%- endmacro %}

{% macro weather_w2_silver_grid_at_snapshot() -%}
  {%- set relation = ref('silver_kma_vilage_fcst_grid') -%}
  {%- set snapshot_id = weather_w2_positive_snapshot_id(
      'weather_w2_silver_grid_pin_snapshot_id'
  ) -%}
  {{ return(relation ~ ' FOR VERSION AS OF ' ~ snapshot_id) }}
{%- endmacro %}

{% macro weather_w2_bridge_at_snapshot() -%}
  {%- set relation = ref('bridge_weather_admin_dong_grid') -%}
  {%- set snapshot_id = weather_w2_positive_snapshot_id(
      'weather_w2_bridge_pin_snapshot_id'
  ) -%}
  {{ return(relation ~ ' FOR VERSION AS OF ' ~ snapshot_id) }}
{%- endmacro %}

{% macro weather_w2_recovery_expected_rows_sql() -%}
{%- set target_admin_dong_code = weather_w2_recovery_target_admin_dong_code() -%}
{%- set canonical_contract = weather_w2_canonical_contract() -%}
with eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),
active_bridge as (
    select
        cast(source_admin_code as varchar) as admin_dong_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ weather_w2_bridge_at_snapshot() }}
    where cast(source_admin_code as varchar) = '{{ target_admin_dong_code }}'
      and cast(nx as integer) = 61
      and cast(ny as integer) = 127
      and cast(bridge_version as varchar) = '{{ weather_w2_bridge_version() }}'
),
canonical as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        cast(revision_date as date) as admin_dong_revision_date
    from {{ asac_axes.pinned_dim_admin_dong() }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
      and cast(admin_dong_code as varchar) = '{{ target_admin_dong_code }}'
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
    from {{ weather_w2_silver_grid_at_snapshot() }} as grid
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    where cast(grid.published_at as timestamp(6))
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(grid.published_at as timestamp(6))
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
      and cast(grid.nx as integer) = 61
      and cast(grid.ny as integer) = 127
),
joined_candidates as (
    select
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        bridge.bridge_version,
        grid.*
    from grid_candidates as grid
    inner join active_bridge as bridge
        on grid.nx = bridge.nx
       and grid.ny = bridge.ny
    inner join canonical
        on bridge.admin_dong_code = canonical.admin_dong_code
),
winning_candidates as (
    select
        admin_dong_code,
        forecast_at,
        category,
        max_by(
            {{ weather_w2_gold_candidate_row('joined_candidates') }},
            {{ weather_w2_grid_winner_order_key('joined_candidates') }}
        ) as winner
    from joined_candidates
    group by admin_dong_code, forecast_at, category
)
select
    concat(
        winner.admin_dong_code,
        '|',
        to_iso8601(cast(winner.forecast_at as timestamp(6))),
        '|',
        winner.category
    ) as product_row_id,
    winner.admin_dong_code,
    winner.forecast_at,
    winner.category,
    winner.admin_dong,
    winner.gu_code,
    winner.gu,
    winner.admin_dong_revision_date,
    winner.bridge_version,
    winner.nx,
    winner.ny,
    winner.source_grid_place_id,
    winner.issued_at,
    winner.collected_at,
    winner.published_at,
    winner.fcst_value_raw,
    winner.fcst_value_num,
    winner.value_representation,
    winner.value_num,
    winner.value_lower_bound,
    winner.value_upper_bound,
    winner.qualitative_code,
    winner.forecast_lead_hours,
    winner.source_id,
    winner.dag_run_id,
    winner.raw_object_key,
    winner.request_id
from winning_candidates
{%- endmacro %}

{% macro get_incremental_weather_w2_recovery_stage_sql(arg_dict) -%}
{%- do weather_w2_assert_gold_target() -%}
{%- set target_relation = arg_dict['target_relation'] -%}
{%- set temp_relation = arg_dict['temp_relation'] -%}
{%- set dest_columns = arg_dict['dest_columns'] -%}
{%- set column_names = dest_columns | map(attribute='name') | list -%}
{%- set quoted_columns = get_quoted_csv(column_names) -%}

{%- set preflight_sql -%}
with source_summary as (
    select
        count(*) as row_count,
        count_if(
            checkpoint_id is null
            or product_row_id is null
            or admin_dong_code is null
            or forecast_at is null
            or category is null
            or issued_at is null
            or collected_at is null
            or published_at is null
            or source_id is null
            or dag_run_id is null
            or raw_object_key is null
            or request_id is null
        ) as null_contract_count,
        count_if(
            admin_dong_code != '1123053600'
            or nx != 61
            or ny != 127
        ) as out_of_scope_count
    from {{ temp_relation }}
),
duplicate_grain as (
    select checkpoint_id, admin_dong_code, forecast_at, category
    from {{ temp_relation }}
    group by checkpoint_id, admin_dong_code, forecast_at, category
    having count(*) > 1
)
select
    source_summary.row_count,
    source_summary.null_contract_count,
    source_summary.out_of_scope_count,
    (select count(*) from duplicate_grain) as duplicate_count
from source_summary
{%- endset -%}
{%- set preflight = run_query(preflight_sql) -%}
{%- if preflight is none or preflight.rows | length != 1 -%}
  {{ exceptions.raise_compiler_error(
    'Weather W2 recovery stage preflight did not return one summary row.'
  ) }}
{%- endif -%}
{%- set summary = preflight.rows[0] -%}
{%- if summary[0] | int == 0
      or summary[1] | int > 0
      or summary[2] | int > 0
      or summary[3] | int > 0 -%}
  {{ exceptions.raise_compiler_error(
    'Weather W2 recovery stage contains zero, null, duplicate, or out-of-scope rows.'
  ) }}
{%- endif -%}

merge into {{ target_relation }} as DBT_INTERNAL_DEST
using {{ temp_relation }} as DBT_INTERNAL_SOURCE
on DBT_INTERNAL_SOURCE.checkpoint_id = DBT_INTERNAL_DEST.checkpoint_id
and DBT_INTERNAL_SOURCE.admin_dong_code = DBT_INTERNAL_DEST.admin_dong_code
and DBT_INTERNAL_SOURCE.forecast_at = DBT_INTERNAL_DEST.forecast_at
and DBT_INTERNAL_SOURCE.category = DBT_INTERNAL_DEST.category
when matched
  and {{ weather_w2_gold_winner_is_not_older(
      'DBT_INTERNAL_SOURCE',
      'DBT_INTERNAL_DEST'
  ) }}
  and (
      {{ weather_w2_gold_candidate_row('DBT_INTERNAL_DEST') }}
          is distinct from {{ weather_w2_gold_candidate_row('DBT_INTERNAL_SOURCE') }}
      or DBT_INTERNAL_DEST.window_start_at
          is distinct from DBT_INTERNAL_SOURCE.window_start_at
      or DBT_INTERNAL_DEST.window_cutoff_at
          is distinct from DBT_INTERNAL_SOURCE.window_cutoff_at
  )
then update set
{%- for column in dest_columns %}
    {{ adapter.quote(column.name) }} = DBT_INTERNAL_SOURCE.{{ adapter.quote(column.name) }}{{ ',' if not loop.last }}
{%- endfor %}
when not matched then insert ({{ quoted_columns }})
values (
{%- for column in dest_columns %}
    DBT_INTERNAL_SOURCE.{{ adapter.quote(column.name) }}{{ ',' if not loop.last }}
{%- endfor %}
)
{%- endmacro %}

{% macro weather_w2_publish_recovery_stage() -%}
{%- set checkpoint_id = weather_w2_recovery_checkpoint_id() -%}
{%- set target_admin_dong_code = weather_w2_recovery_target_admin_dong_code() -%}
{%- set stage_relation = ref('weather_w2_observation_recovery_stage') -%}
{%- set gold_relation = ref('gold_weather_forecast_by_admin_dong') -%}
{%- do weather_w2_assert_gold_target(gold_relation) -%}
{%- set gold_columns = [
    'product_row_id',
    'admin_dong_code',
    'forecast_at',
    'category',
    'admin_dong',
    'gu_code',
    'gu',
    'admin_dong_revision_date',
    'bridge_version',
    'nx',
    'ny',
    'source_grid_place_id',
    'issued_at',
    'collected_at',
    'published_at',
    'fcst_value_raw',
    'fcst_value_num',
    'value_representation',
    'value_num',
    'value_lower_bound',
    'value_upper_bound',
    'qualitative_code',
    'forecast_lead_hours',
    'source_id',
    'dag_run_id',
    'raw_object_key',
    'request_id'
] -%}
{%- set update_columns = gold_columns | reject(
    'in',
    ['admin_dong_code', 'forecast_at', 'category']
) | list -%}

{%- set preflight_sql -%}
with scoped_stage as (
    select *
    from {{ stage_relation }}
    where checkpoint_id = '{{ checkpoint_id }}'
      and admin_dong_code = '1123053600'
),
duplicate_grain as (
    select admin_dong_code, forecast_at, category
    from scoped_stage
    group by admin_dong_code, forecast_at, category
    having count(*) > 1
)
select
    count(*) as row_count,
    count_if(
        admin_dong_code != '{{ target_admin_dong_code }}'
        or nx != 61
        or ny != 127
    ) as out_of_scope_count,
    (select count(*) from duplicate_grain) as duplicate_count
from scoped_stage
{%- endset -%}
{%- set preflight = run_query(preflight_sql) -%}
{%- if preflight is none or preflight.rows | length != 1 -%}
  {{ exceptions.raise_compiler_error(
    'Weather W2 staged publish preflight did not return one summary row.'
  ) }}
{%- endif -%}
{%- set summary = preflight.rows[0] -%}
{%- if summary[0] | int == 0
      or summary[1] | int > 0
      or summary[2] | int > 0 -%}
  {{ exceptions.raise_compiler_error(
    'Weather W2 staged publish source is empty, duplicated, or outside Yongsin-dong.'
  ) }}
{%- endif -%}

{%- set merge_sql -%}
merge into {{ gold_relation }} as DBT_INTERNAL_DEST
using (
    select
    {%- for column_name in gold_columns %}
        {{ adapter.quote(column_name) }}{{ ',' if not loop.last }}
    {%- endfor %}
    from {{ stage_relation }}
    where checkpoint_id = '{{ checkpoint_id }}'
      and admin_dong_code = '1123053600'
) as DBT_INTERNAL_SOURCE
on DBT_INTERNAL_SOURCE.admin_dong_code = DBT_INTERNAL_DEST.admin_dong_code
and DBT_INTERNAL_SOURCE.forecast_at = DBT_INTERNAL_DEST.forecast_at
and DBT_INTERNAL_SOURCE.category = DBT_INTERNAL_DEST.category
when matched
  and {{ weather_w2_gold_winner_is_not_older(
      'DBT_INTERNAL_SOURCE',
      'DBT_INTERNAL_DEST'
  ) }}
  and {{ weather_w2_gold_candidate_row('DBT_INTERNAL_DEST') }}
      is distinct from {{ weather_w2_gold_candidate_row('DBT_INTERNAL_SOURCE') }}
then update set
{%- for column_name in update_columns %}
    {{ adapter.quote(column_name) }} = DBT_INTERNAL_SOURCE.{{ adapter.quote(column_name) }}{{ ',' if not loop.last }}
{%- endfor %}
when not matched then insert (
{%- for column_name in gold_columns %}
    {{ adapter.quote(column_name) }}{{ ',' if not loop.last }}
{%- endfor %}
)
values (
{%- for column_name in gold_columns %}
    DBT_INTERNAL_SOURCE.{{ adapter.quote(column_name) }}{{ ',' if not loop.last }}
{%- endfor %}
)
{%- endset -%}
{%- do run_query(merge_sql) -%}
{{ return({'checkpoint_id': checkpoint_id, 'staged_row_count': summary[0] | int}) }}
{%- endmacro %}

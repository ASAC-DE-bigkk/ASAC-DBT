-- Serving Gold: most recently observed TrafficInfo row per road link.
-- Incremental path recalculates only links touched by the pinned Flow run.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='link_id',
    on_table_exists='drop',
    on_schema_change='fail',
    views_enabled=false,
    pre_hook="{{ traffic_flow_assert_pinned_incremental_rows() }}"
) }}

with changed_rows as (
    {{ traffic_flow_changed_rows() }}
),

changed_links as (
    select distinct link_id
    from changed_rows
    where link_id is not null
      and trim(link_id) <> ''
),

candidate_changed as (
    select
        cast(request_id as varchar) as request_id,
        cast(source_id as varchar) as source_id,
        cast(request_params_json as varchar) as request_params_json,
        cast(link_id as varchar) as link_id,
        cast(flow_speed as double) as flow_speed,
        cast(flow_travel_time as double) as flow_travel_time,
        cast(flow_value_quality as varchar) as flow_value_quality,
        cast(observed_at as timestamp(6)) as observed_at,
        cast(raw_object_key as varchar) as raw_object_key,
        cast(payload_hash as varchar) as payload_hash,
        cast(collected_at as timestamp(6)) as collected_at,
        cast(dag_run_id as varchar) as dag_run_id
    from changed_rows
),

candidate_target as (
    {% if is_incremental() %}
    select
        cast(target.request_id as varchar) as request_id,
        cast(target.source_id as varchar) as source_id,
        cast(null as varchar) as request_params_json,
        cast(target.link_id as varchar) as link_id,
        cast(target.flow_speed as double) as flow_speed,
        cast(target.flow_travel_time as double) as flow_travel_time,
        cast(target.flow_value_quality as varchar) as flow_value_quality,
        cast(target.observed_at_utc as timestamp(6)) as observed_at,
        cast(target.raw_object_key as varchar) as raw_object_key,
        cast(target.payload_hash as varchar) as payload_hash,
        cast(target.collected_at_utc as timestamp(6)) as collected_at,
        cast(target.dag_run_id as varchar) as dag_run_id
    from {{ this }} as target
    inner join changed_links
        on cast(target.link_id as varchar) = changed_links.link_id
    {% else %}
    select
        cast(null as varchar) as request_id,
        cast(null as varchar) as source_id,
        cast(null as varchar) as request_params_json,
        cast(null as varchar) as link_id,
        cast(null as double) as flow_speed,
        cast(null as double) as flow_travel_time,
        cast(null as varchar) as flow_value_quality,
        cast(null as timestamp(6)) as observed_at,
        cast(null as varchar) as raw_object_key,
        cast(null as varchar) as payload_hash,
        cast(null as timestamp(6)) as collected_at,
        cast(null as varchar) as dag_run_id
    where 1 = 0
    {% endif %}
),

ranked as (
    select
        combined.*,
        row_number() over (
            partition by combined.link_id
            order by combined.observed_at desc, combined.raw_object_key desc, combined.request_id desc
        ) as row_num
    from (
        select * from candidate_changed
        union all
        select * from candidate_target
    ) as combined
)

select
    cast(link_id as varchar) as product_row_id,
    cast(link_id as varchar) as link_id,
    cast(source_id as varchar) as source_id,
    cast(flow_speed as double) as flow_speed,
    cast(flow_travel_time as double) as flow_travel_time,
    cast(flow_value_quality as varchar) as flow_value_quality,
    cast(observed_at as timestamp(6)) as observed_at_utc,
    cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6)) as observed_at_kst,
    cast(raw_object_key as varchar) as raw_object_key,
    cast(payload_hash as varchar) as payload_hash,
    cast(request_id as varchar) as request_id,
    cast(collected_at as timestamp(6)) as collected_at_utc,
    cast(dag_run_id as varchar) as dag_run_id
from ranked
where row_num = 1

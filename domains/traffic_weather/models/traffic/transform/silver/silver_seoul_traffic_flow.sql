-- Silver: typed TrafficInfo rows for one publishable flow snapshot.
-- The input run is pinned by traffic_flow_snapshot_dag_run_id so a transform
-- invocation cannot drift to a newer collection while it is running.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['link_id', 'dag_run_id'],
    on_table_exists='drop',
) }}

{% set flow_snapshot_dag_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' %}

with latest_manifest_state as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_flow') }}
),

publishable_run as (
    select distinct dag_run_id
    from latest_manifest_state
    where manifest_status = 'SUCCESS'
      and is_publishable
      and dag_run_id = '{{ flow_snapshot_dag_run_id | replace("'", "''") }}'
),

bronze as (
    select
        cast(flow.request_id as varchar) as request_id,
        cast(flow.source_id as varchar) as source_id,
        cast(flow.request_params_json as varchar) as request_params_json,
        cast(flow.link_id as varchar) as link_id,
        cast(flow.parent_incident_run_id as varchar) as parent_incident_run_id,
        try_cast(nullif(trim(cast(flow.prcs_spd as varchar)), '') as double) as flow_speed,
        try_cast(nullif(trim(cast(flow.prcs_trv_time as varchar)), '') as double) as flow_travel_time,
        cast(flow.raw_object_key as varchar) as raw_object_key,
        cast(flow.payload_hash as varchar) as payload_hash,
        try_cast(flow.http_status as integer) as http_status,
        cast(flow.result_code as varchar) as result_code,
        cast(flow.result_msg as varchar) as result_msg,
        try_cast(flow.list_total_count as integer) as list_total_count,
        try_cast(flow.row_count as integer) as row_count,
        cast(flow.collected_at as timestamp(6)) as collected_at,
        cast(flow.load_date as varchar) as load_date,
        cast(flow.dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'seoul_traffic_flow') }} as flow
    inner join publishable_run
        on cast(flow.dag_run_id as varchar) = publishable_run.dag_run_id
    where cast(flow.result_code as varchar) = 'INFO-000'
      and cast(flow.link_id as varchar) is not null
      and cast(flow.link_id as varchar) <> ''
      {% if is_incremental() %}
      and cast(flow.collected_at as timestamp(6)) >= (
          select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
          from {{ this }}
      )
      {% endif %}
),

ranked as (
    select
        *,
        row_number() over (
            partition by link_id, dag_run_id
            order by collected_at desc, raw_object_key desc, request_id desc
        ) as row_num
    from bronze
)

select
    request_id,
    source_id,
    request_params_json,
    link_id,
    parent_incident_run_id,
    flow_speed,
    flow_travel_time,
    case
        when flow_speed is not null or flow_travel_time is not null then 'available'
        else 'missing_value'
    end as flow_value_quality,
    collected_at as observed_at,
    raw_object_key,
    payload_hash,
    http_status,
    result_code,
    result_msg,
    list_total_count,
    row_count,
    load_date,
    collected_at,
    dag_run_id
from ranked
where row_num = 1

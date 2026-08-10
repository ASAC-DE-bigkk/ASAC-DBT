{% set incident_run_id = var('traffic_snapshot_dag_run_id', '') or '' %}
{% set flow_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' %}

with road_context as (
    select
        cast(product_row_id as varchar) as product_row_id,
        cast(link_id as varchar) as link_id,
        cast(link_reference_quality as varchar) as link_reference_quality,
        cast(parent_incident_run_id as varchar) as parent_incident_run_id,
        cast(flow_dag_run_id as varchar) as flow_dag_run_id
    from {{ ref('gold_traffic_road_congestion_context_current') }}
),

flow_anchor as (
    select
        cast(product_row_id as varchar) as product_row_id,
        cast(link_id as varchar) as link_id,
        cast(parent_incident_run_id as varchar) as parent_incident_run_id,
        cast(dag_run_id as varchar) as flow_dag_run_id
    from {{ ref('gold_traffic_flow_link_latest') }}
),

violations as (
    select
        'traffic_gold_publication' as model_name,
        'missing_pinned_incident_run' as violation_type,
        cast(null as varchar) as product_row_id
    where nullif(trim('{{ incident_run_id }}'), '') is null

    union all

    select
        'gold_traffic_incident_current_by_admin_dong_hourly',
        'stale_incident_snapshot',
        cast(product_row_id as varchar)
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
    where cast(snapshot_dag_run_id as varchar)
        is distinct from '{{ incident_run_id }}'

    union all

    select
        'gold_traffic_incident_x_weather_current_hourly',
        'stale_incident_snapshot',
        cast(product_row_id as varchar)
    from {{ ref('gold_traffic_incident_x_weather_current_hourly') }}
    where cast(snapshot_dag_run_id as varchar)
        is distinct from '{{ incident_run_id }}'

    union all

    select
        'gold_traffic_incident_x_weather_current_hourly' as model_name,
        'invalid_product_row_id' as violation_type,
        cast(product_row_id as varchar) as product_row_id
    from {{ ref('gold_traffic_incident_x_weather_current_hourly') }}
    where product_row_id is null

    union all

    select
        'gold_traffic_incident_x_weather_current_hourly',
        'duplicate_product_row_id',
        cast(product_row_id as varchar)
    from {{ ref('gold_traffic_incident_x_weather_current_hourly') }}
    group by product_row_id
    having count(*) > 1

    union all

    select
        'gold_traffic_road_congestion_context_current',
        'invalid_road_context_key',
        road.product_row_id
    from road_context as road
    where road.product_row_id is null
       or road.link_id is null
       or road.link_reference_quality is null
       or road.flow_dag_run_id is null

    union all

    select
        'gold_traffic_road_congestion_context_current',
        'duplicate_road_context_product_row_id',
        road.product_row_id
    from road_context as road
    group by road.product_row_id
    having count(*) > 1

    union all

    select
        'gold_traffic_road_congestion_context_current',
        'road_context_flow_lineage_mismatch',
        road.product_row_id
    from road_context as road
    left join flow_anchor as flow
      on road.product_row_id = flow.product_row_id
     and road.link_id = flow.link_id
     and road.flow_dag_run_id = flow.flow_dag_run_id
     and road.parent_incident_run_id is not distinct from flow.parent_incident_run_id
    where flow.product_row_id is null

    union all

    select
        'gold_traffic_road_congestion_context_current',
        'missing_road_context_row',
        flow.product_row_id
    from flow_anchor as flow
    left join road_context as road
      on flow.product_row_id = road.product_row_id
    where road.product_row_id is null

    {% if flow_run_id %}
    {% for model_name in [
        'gold_traffic_flow_congestion_hotspots_hourly',
        'gold_traffic_flow_link_latest',
        'gold_traffic_flow_change_latest',
        'gold_traffic_flow_link_time_profile',
        'gold_traffic_flow_anomaly_current'
    ] %}

    union all

    select
        '{{ model_name }}',
        'invalid_product_row_id',
        cast(product_row_id as varchar)
    from {{ ref(model_name) }}
    where product_row_id is null

    union all

    select
        '{{ model_name }}',
        'duplicate_product_row_id',
        cast(product_row_id as varchar)
    from {{ ref(model_name) }}
    group by product_row_id
    having count(*) > 1
    {% endfor %}
    {% endif %}
)

select *
from violations

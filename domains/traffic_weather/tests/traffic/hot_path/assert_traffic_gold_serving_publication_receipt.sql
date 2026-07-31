{% set flow_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' %}

with violations as (
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

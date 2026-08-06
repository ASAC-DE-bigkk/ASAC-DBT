{% set incident_run_id = var('traffic_snapshot_dag_run_id', '') or '' %}
{% set flow_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' %}

with violations as (
    select
        'gold_traffic_incident_current_by_admin_dong_hourly' as model_name,
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
        'gold_traffic_incident_current_by_admin_dong_hourly',
        'invalid_product_row_id',
        cast(product_row_id as varchar)
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
    where product_row_id is null

    union all

    select
        'gold_traffic_incident_current_by_admin_dong_hourly',
        'duplicate_product_row_id',
        cast(product_row_id as varchar)
    from {{ ref('gold_traffic_incident_current_by_admin_dong_hourly') }}
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

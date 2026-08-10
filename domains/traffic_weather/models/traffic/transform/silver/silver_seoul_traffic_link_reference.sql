-- One human-readable, spatially located reference row per observed TOPIS link.
-- depends_on: {{ ref('asac_axes', 'seoul_admin_dong_boundary') }}

with attempts as (
    {{ traffic_link_reference_attempts() }}
),

latest_attempt_ranked as (
    select
        *,
        row_number() over (
            partition by link_id
            order by attempt_collected_at desc, dag_run_id desc
        ) as attempt_row_num
    from attempts
    where link_id is not null
),

latest_attempt as (
    select *
    from latest_attempt_ranked
    where attempt_row_num = 1
),

vertex_positioned as (
    select
        vertex.*,
        row_number() over (
            partition by link_id
            order by vertex_sequence
        ) as vertex_position,
        count(*) over (partition by link_id) as vertex_count
    from {{ ref('silver_seoul_traffic_link_vertex') }} as vertex
),

representative as (
    select *
    from vertex_positioned
    where vertex_position = cast(
        floor((vertex_count + 1) / 2.0) as bigint
    )
),

located as (
    {{ asac_axes.tm_to_wgs84_relation(
        'representative', 'grs80tm_x', 'grs80tm_y'
    ) }}
),

complete_reference as (
    select
        info.link_id,
        info.road_name,
        info.start_node_name,
        info.end_node_name,
        info.map_distance,
        info.region_code,
        located.vertex_sequence as representative_vertex_sequence,
        located.vertex_count,
        located.grs80tm_x,
        located.grs80tm_y,
        located.longitude,
        located.latitude,
        info.request_id as info_request_id,
        located.request_id as vertex_request_id,
        info.raw_object_key as info_raw_object_key,
        located.raw_object_key as vertex_raw_object_key,
        info.payload_hash as info_payload_hash,
        located.payload_hash as vertex_payload_hash,
        greatest(
            info.reference_collected_at,
            located.reference_collected_at
        ) as reference_collected_at,
        info.dag_run_id as reference_dag_run_id
    from {{ ref('silver_seoul_traffic_link_info') }} as info
    left join located
      on info.link_id = located.link_id
     and info.dag_run_id = located.dag_run_id
),

anchored as (
    select
        latest_attempt.link_id,
        complete_reference.road_name,
        complete_reference.start_node_name,
        complete_reference.end_node_name,
        complete_reference.map_distance,
        complete_reference.region_code,
        complete_reference.representative_vertex_sequence,
        complete_reference.vertex_count,
        complete_reference.grs80tm_x,
        complete_reference.grs80tm_y,
        complete_reference.longitude,
        complete_reference.latitude,
        complete_reference.info_request_id,
        complete_reference.vertex_request_id,
        complete_reference.info_raw_object_key,
        complete_reference.vertex_raw_object_key,
        complete_reference.info_payload_hash,
        complete_reference.vertex_payload_hash,
        complete_reference.reference_collected_at,
        complete_reference.reference_dag_run_id,
        latest_attempt.attempt_collected_at as latest_attempt_collected_at,
        latest_attempt.dag_run_id as latest_attempt_dag_run_id,
        latest_attempt.info_actual_count as latest_info_actual_count,
        latest_attempt.vertex_actual_count as latest_vertex_actual_count
    from latest_attempt
    left join complete_reference
      on latest_attempt.link_id = complete_reference.link_id
),

admin_matched as (
    select
        anchored.*,
        boundary.admin_dong_code,
        boundary.gu_code,
        boundary.dong as admin_dong,
        boundary.sigungu as gu,
        row_number() over (
            partition by anchored.link_id
            order by
                case when boundary.admin_dong_code is null then 1 else 0 end,
                boundary.admin_dong_code
        ) as admin_match_num
    from anchored
    left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} as boundary
      on anchored.longitude is not null
     and anchored.latitude is not null
     and boundary.admin_dong_code is not null
     and {{ asac_axes.admin_dong_contains(
         'boundary.boundary_wkt', 'anchored.longitude', 'anchored.latitude'
     ) }}
),

admin_deduped as (
    select *
    from admin_matched
    where admin_match_num = 1
)

select
    link_id,
    road_name,
    start_node_name,
    end_node_name,
    map_distance,
    region_code,
    representative_vertex_sequence,
    vertex_count,
    grs80tm_x,
    grs80tm_y,
    longitude,
    latitude,
    admin_dong_code,
    admin_dong,
    gu_code,
    gu,
    case
        when reference_dag_run_id is null
         and coalesce(latest_info_actual_count, 0) = 0
            then 'missing_info'
        when reference_dag_run_id is null
            then 'missing_vertex'
        when road_name is null
            then 'missing_info'
        when representative_vertex_sequence is null
            then 'missing_vertex'
        when longitude is null or latitude is null
            then 'coordinate_conversion_or_bbox_miss'
        when admin_dong_code is null
            then 'admin_boundary_miss'
        else 'complete'
    end as link_reference_quality,
    info_request_id,
    vertex_request_id,
    info_raw_object_key,
    vertex_raw_object_key,
    info_payload_hash,
    vertex_payload_hash,
    reference_collected_at,
    reference_dag_run_id,
    latest_attempt_collected_at,
    latest_attempt_dag_run_id,
    latest_info_actual_count,
    latest_vertex_actual_count
from admin_deduped

-- depends_on: {{ ref('gold_traffic_incident_spatial_mapping_quality_daily') }}

{% set snapshot_dag_run_id = var('traffic_snapshot_dag_run_id') %}

with checked as (
    select
        *,
        count(*) over (
            partition by quality_day, mapping_bucket
        ) as natural_grain_row_count,
        count(*) over (
            partition by product_row_id
        ) as product_row_id_row_count
    from {{ ref('gold_traffic_incident_spatial_mapping_quality_daily') }}
)

select *
from checked
where product_row_id is null
   or quality_day is null
   or mapping_bucket is null
   or snapshot_dag_run_id is null
   or snapshot_dag_run_id is distinct from '{{ snapshot_dag_run_id | replace("'", "''") }}'
   or snapshot_run_count <> 1
   or evidence_scope is distinct from 'pinned_current_snapshot_by_occurrence_day'
   or natural_grain_row_count <> 1
   or product_row_id_row_count <> 1
   or product_row_id is distinct from concat(
       cast(quality_day as varchar),
       '|',
       mapping_bucket
   )
   or incident_count <= 0
   or mapped_incident_count < 0
   or source_coordinate_missing_count < 0
   or wgs84_conversion_or_bbox_miss_count < 0
   or boundary_match_missing_count < 0
   or canonical_admin_miss_count < 0
   or incident_count is distinct from (
       mapped_incident_count
       + source_coordinate_missing_count
       + wgs84_conversion_or_bbox_miss_count
       + boundary_match_missing_count
       + canonical_admin_miss_count
   )
   or abs(
       mapping_success_ratio
       - cast(mapped_incident_count as double) / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       source_coordinate_missing_ratio
       - cast(source_coordinate_missing_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       wgs84_conversion_or_bbox_miss_ratio
       - cast(wgs84_conversion_or_bbox_miss_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       boundary_match_missing_ratio
       - cast(boundary_match_missing_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or abs(
       canonical_admin_miss_ratio
       - cast(canonical_admin_miss_count as double)
         / cast(incident_count as double)
   ) > 0.000000000001
   or (
       mapping_bucket = '__UNMAPPED__'
       and (
           mapping_state is distinct from 'unmapped'
           or admin_dong_code is not null
           or admin_dong is not null
           or gu_code is not null
           or gu is not null
           or admin_dong_revision_date is not null
           or mapped_incident_count <> 0
       )
   )
   or (
       mapping_bucket <> '__UNMAPPED__'
       and (
           mapping_state is distinct from 'mapped'
           or admin_dong_code is distinct from mapping_bucket
           or admin_dong is null
           or gu_code is null
           or gu is null
           or admin_dong_revision_date is null
           or mapped_incident_count <> incident_count
           or source_coordinate_missing_count <> 0
           or wgs84_conversion_or_bbox_miss_count <> 0
           or boundary_match_missing_count <> 0
           or canonical_admin_miss_count <> 0
       )
   )

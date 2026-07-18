{{ config(tags=['traffic_gold_gate']) }}
-- depends_on: {{ ref('gold_traffic_incident_spatial_mapping_quality_daily') }}
-- depends_on: {{ ref('silver_seoul_traffic_incident_current') }}
-- depends_on: {{ ref('asac_axes', 'dim_admin_dong') }}

with canonical_raw as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        try_cast(revision_date as date) as admin_dong_revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

canonical_ranked as (
    select
        *,
        row_number() over (
            partition by admin_dong_code
            order by
                admin_dong_revision_date desc nulls last,
                admin_dong asc nulls last,
                gu_code asc nulls last,
                gu asc nulls last
        ) as canonical_row_num
    from canonical_raw
),

canonical as (
    select *
    from canonical_ranked
    where admin_dong_code is not null
      and canonical_row_num = 1
),

classified as (
    select
        cast(current_snapshot.occurred_at as date) as quality_day,
        coalesce(canonical.admin_dong_code, '__UNMAPPED__') as mapping_bucket,
        canonical.admin_dong_code,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        cast(current_snapshot.dag_run_id as varchar) as snapshot_dag_run_id,
        case
            when canonical.admin_dong_code is not null
                then 'mapped'
            when current_snapshot.source_location_quality
                    = 'source_coordinate_missing'
              or current_snapshot.grs80tm_x is null
              or current_snapshot.grs80tm_y is null
                then 'source_coordinate_missing'
            when current_snapshot.longitude is null
              or current_snapshot.latitude is null
                then 'wgs84_conversion_or_bbox_miss'
            when current_snapshot.admin_dong_code is null
                then 'boundary_match_missing'
            else 'canonical_admin_miss'
        end as mapping_evidence_class
    from {{ ref('silver_seoul_traffic_incident_current') }} as current_snapshot
    left join canonical
        on cast(current_snapshot.admin_dong_code as varchar)
            = canonical.admin_dong_code
    where current_snapshot.occurred_at is not null
),

evidence as (
    select
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        max(snapshot_dag_run_id) as snapshot_dag_run_id,
        count(distinct snapshot_dag_run_id) as snapshot_run_count,
        count(*) as incident_count,
        count_if(mapping_evidence_class = 'mapped')
            as mapped_incident_count,
        count_if(mapping_evidence_class = 'source_coordinate_missing')
            as source_coordinate_missing_count,
        count_if(mapping_evidence_class = 'wgs84_conversion_or_bbox_miss')
            as wgs84_conversion_or_bbox_miss_count,
        count_if(mapping_evidence_class = 'boundary_match_missing')
            as boundary_match_missing_count,
        count_if(mapping_evidence_class = 'canonical_admin_miss')
            as canonical_admin_miss_count
    from classified
    group by
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date
),

expected as (
    select
        concat(cast(quality_day as varchar), '|', mapping_bucket)
            as product_row_id,
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        snapshot_dag_run_id,
        snapshot_run_count,
        cast('pinned_current_snapshot_by_occurrence_day' as varchar)
            as evidence_scope,
        incident_count,
        mapped_incident_count,
        source_coordinate_missing_count,
        wgs84_conversion_or_bbox_miss_count,
        boundary_match_missing_count,
        canonical_admin_miss_count,
        cast(mapped_incident_count as double) / cast(incident_count as double)
            as mapping_success_ratio,
        cast(source_coordinate_missing_count as double)
            / cast(incident_count as double)
            as source_coordinate_missing_ratio,
        cast(wgs84_conversion_or_bbox_miss_count as double)
            / cast(incident_count as double)
            as wgs84_conversion_or_bbox_miss_ratio,
        cast(boundary_match_missing_count as double)
            / cast(incident_count as double)
            as boundary_match_missing_ratio,
        cast(canonical_admin_miss_count as double)
            / cast(incident_count as double)
            as canonical_admin_miss_ratio,
        case
            when mapping_bucket = '__UNMAPPED__' then 'unmapped'
            else 'mapped'
        end as mapping_state
    from evidence
),

actual as (
    select
        product_row_id,
        quality_day,
        mapping_bucket,
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        admin_dong_revision_date,
        snapshot_dag_run_id,
        snapshot_run_count,
        evidence_scope,
        incident_count,
        mapped_incident_count,
        source_coordinate_missing_count,
        wgs84_conversion_or_bbox_miss_count,
        boundary_match_missing_count,
        canonical_admin_miss_count,
        mapping_success_ratio,
        source_coordinate_missing_ratio,
        wgs84_conversion_or_bbox_miss_ratio,
        boundary_match_missing_ratio,
        canonical_admin_miss_ratio,
        mapping_state
    from {{ ref('gold_traffic_incident_spatial_mapping_quality_daily') }}
),

missing_rows as (
    select * from expected
    except
    select * from actual
),

extra_rows as (
    select * from actual
    except
    select * from expected
)

select 'missing_expected_row' as violation_type, *
from missing_rows

union all

select 'extra_actual_row' as violation_type, *
from extra_rows

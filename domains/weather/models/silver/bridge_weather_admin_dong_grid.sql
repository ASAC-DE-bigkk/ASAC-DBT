-- W1 canonical bridge: legacy assertion을 보존하고 공통 행정동 차원의 값을 exact-code로 stamp한다.
{{ config(materialized='table') }}

with candidate as (
    select
        cast(place_id as varchar) as place_id,
        cast(place_name as varchar) as place_name,
        cast(alias_names as varchar) as alias_names,
        cast(legacy_gu as varchar) as legacy_gu,
        cast(legacy_admin_dong as varchar) as legacy_admin_dong,
        cast(latitude as double) as latitude,
        cast(longitude as double) as longitude,
        cast(source_admin_code as varchar) as source_admin_code,
        cast(bridge_version as varchar) as bridge_version,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny,
        cast(legacy_mapping_method as varchar) as legacy_mapping_method,
        cast(mapping_revision_label as varchar) as mapping_revision_label,
        cast(recorded_at as timestamp(6)) as recorded_at,
        cast(valid_from_at as timestamp(6)) as valid_from_at,
        cast(valid_to_at as timestamp(6)) as valid_to_at,
        cast(effective_from_basis as varchar) as effective_from_basis,
        cast(mapping_method as varchar) as mapping_method,
        cast(temporal_quality as varchar) as temporal_quality,
        cast(grid_distance_m as double) as grid_distance_m
    from {{ ref('weather_admin_dong_grid_bridge_history') }}
),

canonical as (
    select
        admin_dong_code,
        admin_dong,
        gu_code,
        gu,
        revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
)

select
    candidate.*,
    canonical.admin_dong_code,
    canonical.admin_dong,
    canonical.gu_code,
    canonical.gu,
    canonical.revision_date as admin_dong_revision_date,
    case when canonical.admin_dong_code is not null then 'matched' else 'unmatched' end as canonical_mapping_state,
    canonical.admin_dong_code is not null as canonical_join_eligible
from candidate
left join canonical
    on candidate.source_admin_code = canonical.admin_dong_code

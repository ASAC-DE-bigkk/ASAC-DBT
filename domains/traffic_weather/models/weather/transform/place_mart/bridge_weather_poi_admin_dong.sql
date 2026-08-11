-- bridge_weather_poi_admin_dong — 서울 주요 장소(citydata 121 POI) ↔ 행정동 매핑 (#511).
--
-- 페르소나 실측(ASK-Seoul#116)의 "행정동 ↔ 주요 장소 매핑" 간극 해소. citydata 의
-- 장소 seed(중심 좌표 보유)를 행정동 경계(point-in-polygon)에 붙여, weather 의
-- 행정동 축 제품과 citydata 의 장소 축 제품을 오갈 수 있는 다리를 만든다.
--
-- 매핑 방식은 culture `culture_dong_map`(가동 중) 과 동일 — `asac_axes.admin_dong_contains`
-- 로 중심 좌표의 소속 행정동을 찍고, dim_admin_dong 으로 정본 이름·자치구를 붙인다.
-- 경계 밖(서울 외곽 POI 등)은 unmatched 로 남긴다(값을 꾸며내지 않는다).

{{ config(materialized='table') }}

with poi as (
    select
        cast(area_cd as varchar)             as area_cd,
        cast(category as varchar)            as category,
        cast(area_nm as varchar)             as area_nm,
        cast(center_lon as double)           as longitude,
        cast(center_lat as double)           as latitude
    from {{ source('citydata_gold', 'seoul_hotspot_area_geo') }}
),

pip as (
    select
        p.*,
        b.admin_dong_code as boundary_admin_dong_code
    from poi p
    left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} b
      on {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'p.longitude', 'p.latitude') }}
),

canonical as (
    select admin_dong_code, admin_dong, gu_code, gu
    from {{ ref('asac_axes', 'dim_admin_dong') }}
)

select
    pip.area_cd,
    pip.category,
    pip.area_nm,
    pip.longitude,
    pip.latitude,
    canonical.admin_dong_code,
    canonical.admin_dong,
    canonical.gu_code,
    canonical.gu,
    case when canonical.admin_dong_code is not null
         then 'matched' else 'unmatched' end as canonical_mapping_state
from pip
left join canonical
  on pip.boundary_admin_dong_code = canonical.admin_dong_code

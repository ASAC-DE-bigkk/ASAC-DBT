-- dim_transit_parking — 주차장 차원(최신 load_date 스냅샷).
--
-- 키: parking_id(pklt_cd). 공간축: lot(경도)/lat(위도) → seoul_lonlat → longitude/latitude,
--     seoul_admin_dong_boundary 와 point-in-polygon 조인해 admin_dong_code/gu_code 부착.
-- 좌표 0.0(미상) 주차장이 다수라 admin_dong 커버리지는 좌표 유효분(≈67%)으로 제한된다.
--
-- addr_gu: 주소 첫 자치구 토큰('[가-힣]+구'). 경계 조인 결과 gu(sigungu)와의 일치를
--          경량 검증(assert_parking_addr_gu_matches_boundary, warn)에 쓴다.

{{ config(materialized='view') }}

with latest as (
    select max(load_date) as load_date
    from {{ source('transit_bronze', 'park_info_master') }}
),

master as (
    select
        cast(pklt_cd as varchar) as parking_id,
        cast(pklt_nm as varchar) as parking_name,
        cast(addr as varchar) as addr,
        regexp_extract(cast(addr as varchar), '([가-힣]+구)', 1) as addr_gu,
        cast(pklt_knd_nm as varchar) as parking_kind_nm,
        cast(chgd_free_nm as varchar) as charge_free_nm,
        try(cast(tpkct as integer)) as total_capacity,
        {{ asac_axes.seoul_lonlat('lot', 'lat') }},
        raw_object_key,
        source_system,
        collected_at,
        load_date
    from {{ source('transit_bronze', 'park_info_master') }}
    where load_date = (select load_date from latest)
),

located as (
    select
        m.*,
        b.admin_dong_code,
        b.gu_code,
        b.sigungu as gu,
        b.dong as admin_dong,
        row_number() over (
            partition by m.parking_id
            order by b.admin_dong_code
        ) as rn
    from master m
    left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} b
        on m.longitude is not null
       and {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'm.longitude', 'm.latitude') }}
)

select
    parking_id,
    parking_name,
    addr,
    addr_gu,
    parking_kind_nm,
    charge_free_nm,
    total_capacity,
    latitude,
    longitude,
    admin_dong_code,
    gu_code,
    gu,
    admin_dong,
    raw_object_key,
    source_system,
    collected_at,
    load_date
from located
where rn = 1

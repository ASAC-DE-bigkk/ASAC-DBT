-- dim_transit_station — 지하철 역사 차원(최신 load_date 스냅샷).
--
-- 키: station_id(bldn_id, 마스터 PK). 실시간 arrival 과의 조인은 bldn_id 가 아니라
-- '역명 + 노선' 으로 한다(arrival 은 다른 statnId 체계를 쓰고, bldn_id 뒤4자리 방식은
-- 신분당선에서 불성립함이 실증됨). 이를 위해 조인용 정규화 컬럼 station_name_join 을 노출한다:
--   - 역명 괄호 부기 제거: '잠실(송파구청)' → '잠실' (arrival statnNm 은 '잠실')
--   - route 는 라벨 그대로 유지(괄호 제거 시 '7호선' vs '7호선(인천)' 이 충돌해 grain 깨짐).
-- (station_name_join, route) 은 마스터에서 unique 함을 실증(중복 0건).
--
-- 공간축: lot(경도)/lat(위도) 를 seoul_lonlat 로 정규화 → longitude/latitude,
--        seoul_admin_dong_boundary 와 point-in-polygon 조인해 admin_dong_code/gu_code 부착.
-- 수도권(경기·인천) 역은 서울 bbox 밖이라 좌표/행정동이 NULL 이 된다(정상).

{{ config(materialized='view') }}

with latest as (
    select max(load_date) as load_date
    from {{ source('transit_bronze', 'subway_station_master') }}
),

master as (
    select
        cast(bldn_id as varchar) as station_id,
        cast(bldn_nm as varchar) as station_name,
        trim(regexp_replace(cast(bldn_nm as varchar), '\(.*\)', '')) as station_name_join,
        cast(route as varchar) as route,
        {{ asac_axes.seoul_lonlat('lot', 'lat') }},
        raw_object_key,
        source_system,
        collected_at,
        load_date
    from {{ source('transit_bronze', 'subway_station_master') }}
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
            partition by m.station_id
            order by b.admin_dong_code
        ) as rn
    from master m
    left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} b
        on m.longitude is not null
       and {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'm.longitude', 'm.latitude') }}
)

select
    station_id,
    station_name,
    station_name_join,
    route,
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

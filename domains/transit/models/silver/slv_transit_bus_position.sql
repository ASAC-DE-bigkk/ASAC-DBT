-- slv_transit_bus_position — 버스 실시간 위치 정제.
--
-- 원문은 XML(<ServiceResult>…다수 <itemList>). Trino 는 xpath 함수가 없어
-- regexp_extract_all 로 itemList 조각을 뽑아 UNNEST 하고, 각 조각을 필드 regexp 로 파싱한다.
--   (PoC: <vehId>/<dataTm>/<gpsX>/<gpsY> 등, 태그값은 '[^<]*' 로 캡처)
-- grain: (veh_id=vehId, data_tm=dataTm). incremental(merge), ingested_at 기준 -2h lookback.
-- 시간축: event_at = dataTm(yyyyMMddHHmmss) KST.
-- 공간축: gpsX→longitude, gpsY→latitude 직접(이미 WGS84), seoul_admin_dong_boundary 와
--         런타임 point-in-polygon 조인으로 admin_dong_code/gu_code 할당.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['veh_id', 'data_tm'],
) }}

with bronze as (
    select
        raw,
        cast(bus_route_id as varchar) as bus_route_id,
        cast(dag_run_id as varchar) as dag_run_id,
        ingested_at
    from {{ source('transit_bronze', 'bus_position') }}
    {% if is_incremental() %}
    where ingested_at >= (
        select coalesce(max(ingested_at), timestamp '1970-01-01') - interval '2' hour
        from {{ this }}
    )
    {% endif %}
),

items as (
    select
        b.bus_route_id,
        b.dag_run_id,
        b.ingested_at,
        regexp_extract(item, '<vehId>([^<]*)</vehId>', 1) as veh_id,
        regexp_extract(item, '<dataTm>([^<]*)</dataTm>', 1) as data_tm,
        regexp_extract(item, '<plainNo>([^<]*)</plainNo>', 1) as plain_no,
        regexp_extract(item, '<gpsX>([^<]*)</gpsX>', 1) as gps_x,
        regexp_extract(item, '<gpsY>([^<]*)</gpsY>', 1) as gps_y,
        regexp_extract(item, '<sectOrd>([^<]*)</sectOrd>', 1) as sect_ord,
        regexp_extract(item, '<congetion>([^<]*)</congetion>', 1) as congestion,
        regexp_extract(item, '<nextStId>([^<]*)</nextStId>', 1) as next_st_id
    from bronze b
    cross join unnest(regexp_extract_all(b.raw, '<itemList>(.*?)</itemList>')) as t(item)
),

typed as (
    select
        veh_id,
        data_tm,
        {{ asac_axes.kst_at('data_tm') }} as event_at,
        bus_route_id,
        plain_no,
        {{ asac_axes.seoul_lonlat('gps_x', 'gps_y') }},
        try(cast(sect_ord as integer)) as sect_ord,
        try(cast(congestion as integer)) as congestion,
        next_st_id,
        dag_run_id,
        ingested_at
    from items
    where veh_id is not null and veh_id <> ''
      and data_tm is not null and data_tm <> ''
),

ranked as (
    select
        *,
        row_number() over (
            partition by veh_id, data_tm
            order by ingested_at desc
        ) as row_num
    from typed
),

located as (
    select
        r.*,
        b.admin_dong_code,
        b.gu_code,
        row_number() over (
            partition by r.veh_id, r.data_tm
            order by b.admin_dong_code
        ) as geo_rn
    from ranked r
    left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} b
        on r.row_num = 1
       and r.longitude is not null
       and {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'r.longitude', 'r.latitude') }}
    where r.row_num = 1
)

select
    veh_id,
    data_tm,
    event_at,
    bus_route_id,
    plain_no,
    latitude,
    longitude,
    admin_dong_code,
    gu_code,
    sect_ord,
    congestion,
    next_st_id,
    dag_run_id,
    ingested_at
from located
where geo_rn = 1

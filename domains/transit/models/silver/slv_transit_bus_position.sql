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
        regexp_extract(item, '<nextStId>([^<]*)</nextStId>', 1) as next_st_id,
        regexp_extract(item, '<stopFlag>([^<]*)</stopFlag>', 1) as stop_flag_raw,
        regexp_extract(item, '<isFullFlag>([^<]*)</isFullFlag>', 1) as is_full_raw,
        regexp_extract(item, '<islastyn>([^<]*)</islastyn>', 1) as is_last_bus_raw,
        regexp_extract(item, '<rtDist>([^<]*)</rtDist>', 1) as rt_dist_raw,
        regexp_extract(item, '<fullSectDist>([^<]*)</fullSectDist>', 1) as full_sect_dist_raw
    from bronze b
    -- (?s): Trino 정규식의 '.' 는 기본적으로 개행에 매치되지 않는다. itemList 조각이
    --       개행을 포함하면 매치가 조용히 0건이 되므로 DOTALL 플래그로 개행을 포함시킨다.
    cross join unnest(regexp_extract_all(b.raw, '(?s)<itemList>(.*?)</itemList>')) as t(item)
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
        try(cast(stop_flag_raw as integer)) as stop_flag,
        try(cast(is_full_raw as integer)) as is_full,
        try(cast(is_last_bus_raw as integer)) as is_last_bus,
        -- rtDist(노선 누적 진행거리)·fullSectDist(구간 전체거리)는 둘 다 km 단위(실증:
        -- rtDist 39.65~62.2 = 노선 왕복 수십 km, fullSectDist 0.095~3.584 = 정류장 간 수백 m).
        try(cast(rt_dist_raw as double)) as rt_dist_km,
        try(cast(full_sect_dist_raw as double)) as full_sect_dist_km,
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

-- grain 중복 제거를 경계 조인과 분리(row_num=1 술어를 한 곳에서만 평가).
deduped as (
    select *
    from ranked
    where row_num = 1
),

located as (
    select
        d.*,
        b.admin_dong_code,
        b.gu_code,
        row_number() over (
            partition by d.veh_id, d.data_tm
            order by b.admin_dong_code
        ) as geo_rn
    from deduped d
    -- 좌표 유효분만 경계 조인(null 좌표 행은 left join 으로 보존, admin_dong 은 null).
    left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} b
        on d.longitude is not null
       and {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'd.longitude', 'd.latitude') }}
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
    stop_flag,
    is_full,
    is_last_bus,
    rt_dist_km,
    full_sect_dist_km,
    dag_run_id,
    ingested_at
from located
where geo_rn = 1

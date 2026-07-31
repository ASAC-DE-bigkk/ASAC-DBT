-- gold: 장소×대여소 **현재 따릉이 가용 현황** (챗봇 서빙, d1_direct). grain = (area_cd, spot_id).
--
-- silver_citydata_sbike(대여소별 상태 시계열)에서 대여소별 **최신 상태**만 골라 서빙.
-- "지금 여기 따릉이 남아 있어?" 를 parking_count>0(대여 가능 자전거 수)으로 답한다.
-- place_latest 는 장소 합계만 줘서 "어느 대여소" 를 못 답함 — 이 골드가 대여소 단위를 채운다.
-- 소형(장소당 수~수십 대여소)이라 전량 교체 스냅샷으로 D1 서빙 적합. table+replace 상속(멱등).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
    tags=['fast'],
) }}

with latest as (
    -- 대여소별 최신 관측 1건
    select *, row_number() over (
        partition by area_cd, spot_id
        order by observed_at desc) as rn
    from {{ ref('silver_citydata_sbike') }}
),

cur as (select * from latest where rn = 1)

select
    c.area_cd,
    ar.area_nm,
    ar.area_category,
    c.admin_dong_code,
    c.gu_code,
    c.spot_id,
    c.spot_nm,
    c.spot_longitude,
    c.spot_latitude,
    c.parking_count,                                              -- 대여 가능 자전거 수 (★ "남아있어?")
    c.rack_count,                                                 -- 거치대 수
    c.shared_rate_percent,                                        -- 거치율(%) = parking/rack
    case when c.parking_count > 0 then true else false end as has_bikes,
    c.observed_at
from cur c
left join {{ ref('dim_seoul_area') }} ar on c.area_cd = ar.area_cd

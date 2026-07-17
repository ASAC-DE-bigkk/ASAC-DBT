-- gold: 장소×충전소 **현재 EV 충전 가용 현황** (챗봇 서빙, D1 export d1_direct 후보). grain = (area_cd, stat_id).
--
-- silver_citydata_charger(충전기별 상태 시계열)에서 충전기별 **최신 상태**만 골라 충전소로 집계.
-- "지금 근처 충전 가능한 곳" 질의를 available_count>0 필터로 답한다. 소형(수백 충전소)이라
-- 전량 교체 스냅샷으로 D1 서빙에 적합. table+replace(프로젝트 기본) 상속 — 매 run 재빌드(멱등).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
) }}

with latest as (
    -- 충전기별 최신 상태 1건 (상태 변경 로그에서 현재값)
    select *, row_number() over (
        partition by area_cd, stat_id, charger_id
        order by observed_at desc, collected_at desc) as rn
    from {{ ref('silver_citydata_charger') }}
),

cur as (select * from latest where rn = 1),

agg as (
    -- grain 은 (area_cd, stat_id) 만. 충전소 속성(이름·주소·좌표)은 행마다 미세 변동이
    -- 있을 수 있어 max() 대표값으로(같은 stat_id 는 사실상 동일).
    select
        area_cd,
        stat_id,
        max(admin_dong_code)                                       as admin_dong_code,
        max(gu_code)                                               as gu_code,
        max(longitude)                                             as longitude,
        max(latitude)                                              as latitude,
        max(stat_nm)                                               as stat_nm,
        max(stat_addr)                                             as stat_addr,
        max(stat_longitude)                                        as stat_longitude,
        max(stat_latitude)                                         as stat_latitude,
        max(place_kind)                                            as place_kind,
        count(*)                                                   as total_chargers,
        sum(if(charger_stat = '사용가능', 1, 0))                    as available_count,
        sum(if(charger_stat = '충전중', 1, 0))                      as charging_count,
        sum(if(charger_stat in ('점검중', '통신이상', '운영중지', '상태미확인'), 1, 0)) as unavailable_count,
        -- 급속(DC)/완속(AC) 가용 — 챗봇 "급속 되는 곳"
        sum(if(charger_stat = '사용가능' and (charger_type like 'DC%' or charger_type like '%급속%'), 1, 0)) as fast_available,
        sum(if(charger_stat = '사용가능' and (charger_type like 'AC%' or charger_type like '%완속%'), 1, 0)) as slow_available,
        max(output_kw)                                             as max_output_kw,
        max(observed_at)                                           as observed_at
    from cur
    group by area_cd, stat_id
)

select
    a.area_cd,
    ar.area_nm,
    ar.area_category,
    a.admin_dong_code,
    a.gu_code,
    a.longitude,
    a.latitude,
    a.stat_id,
    a.stat_nm,
    a.stat_addr,
    a.stat_longitude,
    a.stat_latitude,
    a.place_kind,
    a.total_chargers,
    a.available_count,
    a.charging_count,
    a.unavailable_count,
    a.fast_available,
    a.slow_available,
    cast(round(100.0 * a.available_count / a.total_chargers, 1) as double) as availability_pct,
    a.max_output_kw,
    a.observed_at
from agg a
left join {{ ref('dim_seoul_area') }} ar on a.area_cd = ar.area_cd

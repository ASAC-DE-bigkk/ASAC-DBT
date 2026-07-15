-- dim_transit_parking — 주차장 차원(최신 load_date 스냅샷).
--
-- 키: parking_id(pklt_cd). 공간축: lot(경도)/lat(위도) → seoul_lonlat → longitude/latitude,
--     seoul_admin_dong_boundary 와 point-in-polygon 조인해 admin_dong_code/gu_code 부착.
-- 좌표 0.0(미상) 주차장이 다수라 admin_dong 커버리지는 좌표 유효분(≈67%)으로 제한된다.
--
-- addr_gu: 주소 첫 자치구 토큰('[가-힣]+구'). 경계 조인 결과 gu(sigungu)와의 일치를
--          경량 검증(assert_parking_addr_gu_matches_boundary, warn)에 쓴다.

{{ config(materialized='table') }}

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
        -- 운영 관련 컬럼("운영시간 내 점유율" 분석 재료). 시각은 HHMM 문자열 그대로 노출
        -- (0000~2400, '0000/0000'=미상 존재 → 파싱은 소비층에서).
        -- 중복 pklt_cd 행 간 운영 필드 전부 동일함을 실증(차이 나는 lot 0건) —
        -- 아래 rn dedup 결정성(order by admin_dong_code, 좌표)에 영향 없음.
        cast(wd_oper_bgng_tm as varchar) as wd_oper_bgng_tm,
        cast(wd_oper_end_tm as varchar) as wd_oper_end_tm,
        cast(we_oper_bgng_tm as varchar) as we_oper_bgng_tm,
        cast(we_oper_end_tm as varchar) as we_oper_end_tm,
        cast(nght_free_opn_yn_name as varchar) as night_free_open_yn_nm,
        -- 원천 tpkct 가 소수 문자열("1.0")이라 integer 직접 캐스트는 전건 실패(#72) —
        -- double 경유 매크로로 소수·정수 문자열 모두 수용(silver_transit_parking 과 공유).
        {{ transit_int_from_numeric_str('tpkct') }} as total_capacity,
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
        -- pklt_cd 는 마스터에서 유일하지 않다: 65개 lot 이 같은 addr·행정동에
        -- 좌표만 다른 다수 행으로 존재(실증). admin_dong_code 만으로 정렬하면 동률이
        -- 발생해 어떤 좌표가 뽑힐지 비결정적 → view 재실행마다 좌표가 바뀔 수 있다.
        -- admin_dong 이 잡힌 행 우선(nulls last) 후 좌표로 전순서를 확정해 결정성 보장.
        row_number() over (
            partition by m.parking_id
            order by b.admin_dong_code nulls last, m.latitude, m.longitude
        ) as rn
    from master m
    left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} b
        on m.longitude is not null and m.latitude is not null
       and {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'm.longitude', 'm.latitude') }}
)

select
    parking_id,
    parking_name,
    addr,
    addr_gu,
    parking_kind_nm,
    charge_free_nm,
    wd_oper_bgng_tm,
    wd_oper_end_tm,
    we_oper_bgng_tm,
    we_oper_end_tm,
    night_free_open_yn_nm,
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

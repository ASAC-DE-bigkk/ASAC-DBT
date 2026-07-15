-- gold_env_facility_operation — 영업(가동) 시간·일수 축 집계: 시군구 × 업종.
--
-- 인사이트 계약(#71) — "영업시간·영업요일 조회" 요구의 실측 대응: LOCALDATA 인허가 원천에는
-- 영업시간/영업요일 필드가 **존재하지 않는다**(카탈로그 payload 전수 검색 0건). 유일한 실존
-- 축은 환경 v2 2종(대기/수질 배출시설)의 **연간 가동일수(anl_oprtng_dcnt)·가동시간(oper_hrm)**
-- — 이를 영업 중(상태 01) 시설 기준으로 집계한다. 타 업종의 영업시간 축은 외부 원천 결합이
-- 필요(후속 과제, PROJECT.md §4.3 비고).
--
-- 현재 버전 매칭: entity ⋈ detail (자연키+content_hash — 정본 패턴 §1.4).
-- materialized=table(소형 — 전량 재계산 멱등. D1 export 는 스냅샷 교체).

{{ config(materialized='table') }}

with fac as (
    select e.dataset, coalesce(e.gu_code, 'UNK') as gu_code, e.gu,
           d.ems_fclt_anl_oprtng_dcnt as ems_days, d.ems_fclt_oper_hrm as ems_hours,
           d.pvt_fclt_anl_oprtng_dcnt as pvt_days, d.pvt_fclt_oper_hrm as pvt_hours
    from {{ ref('silver_license_entity') }} e
    join {{ source('commerce_silver_details', 'silver_air_pollution_facility_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    where substr(trim(coalesce(e.trdstategbn, '')), 1, 2) = '01'      -- 영업/가동 중만

    union all

    select e.dataset, coalesce(e.gu_code, 'UNK'), e.gu,
           d.ems_fclt_anl_oprtng_dcnt, d.ems_fclt_oper_hrm,
           d.pvt_fclt_anl_oprtng_dcnt, d.pvt_fclt_oper_hrm
    from {{ ref('silver_license_entity') }} e
    join {{ source('commerce_silver_details', 'silver_water_pollution_facility_detail') }} d
      on  d.dataset = e.dataset and d.opnsfteamcode = e.opnsfteamcode
      and d.mgtno = e.mgtno and d.content_hash = e.content_hash
    where substr(trim(coalesce(e.trdstategbn, '')), 1, 2) = '01'
),

typed as (
    select dataset, gu_code, gu,
           case when regexp_like(trim(coalesce(ems_days,  '')), '^\d+(\.\d+)?$') then cast(trim(ems_days)  as double) end as op_days,
           case when regexp_like(trim(coalesce(ems_hours, '')), '^\d+(\.\d+)?$') then cast(trim(ems_hours) as double) end as op_hours
    from fac
    union all
    select dataset, gu_code, gu,
           case when regexp_like(trim(coalesce(pvt_days,  '')), '^\d+(\.\d+)?$') then cast(trim(pvt_days)  as double) end,
           case when regexp_like(trim(coalesce(pvt_hours, '')), '^\d+(\.\d+)?$') then cast(trim(pvt_hours) as double) end
    from fac
)

select dataset, gu_code, max(gu) as gu,
       count(*)                          as facility_rows,
       count(op_days)                    as with_operating_days,
       round(avg(op_days), 1)            as avg_operating_days_per_year,
       approx_percentile(op_days, 0.5)   as p50_operating_days,
       count(op_hours)                   as with_operating_hours,
       round(avg(op_hours), 1)           as avg_operating_hours,
       approx_percentile(op_hours, 0.5)  as p50_operating_hours
from typed
group by dataset, gu_code

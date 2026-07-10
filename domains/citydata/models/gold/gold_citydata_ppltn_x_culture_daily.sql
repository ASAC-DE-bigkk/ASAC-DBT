-- gold: 인구혼잡 × 문화행사 (#122). grain = (event_date, admin_dong_code).
--
-- 우리 인구 silver 를 행정동×일 로 롤업하고, 그날 그 동에서 '활성' 인 문화행사
-- (culture.silver_culture_event, event_start_date~end_date 포함)를 붙여 행사의 집객
-- 효과를 본다. 답: 행사 있는 동·날이 더 붐비나.
--
-- 크로스도메인: culture 는 별도 dbt 프로젝트라 source() 로 참조(같은 카탈로그, schema=culture).
-- 조인축 admin_dong_code — 우리=라이브(B)/traffic·culture=자체 매핑, 대개 일치하나 재편 시
-- 어긋날 수 있음(#122 배선 노트). 동 이름/구는 dim_admin_dong(라이브 대장) 조인.
-- 커버리지: 우리 121핫플이 속한 동에 한정(전 서울 아님).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['event_date', 'admin_dong_code'],
    on_table_exists='drop',
) }}

with ppltn_dong as (
    select
        cast(event_at as date) as event_date,
        admin_dong_code,
        max(gu_code) as gu_code,
        avg((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_avg,
        max((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_peak,
        count(distinct area_cd) as hotspot_count
    from {{ ref('silver_seoul_ppltn') }}
    where admin_dong_code is not null
    {% if is_incremental() %}
      and event_at >= (
        select coalesce(max(event_date), date '1970-01-01') - interval '1' day from {{ this }}
    )
    {% endif %}
    group by 1, 2
),

-- 각 (동, 날)에 활성인 행사: 시작~종료 범위가 그날을 포함. distinct event_key 로 카운트.
events_daily as (
    select
        p.event_date,
        p.admin_dong_code,
        count(distinct e.event_key) as event_count,
        count(distinct case when e.is_free = '무료' then e.event_key end) as free_event_count,
        array_join(array_distinct(array_agg(e.category)), ', ') as event_categories
    from ppltn_dong p
    join {{ source('culture', 'silver_culture_event') }} e
        on e.admin_dong_code = p.admin_dong_code
        and p.event_date between e.event_start_date and e.event_end_date
    group by 1, 2
)

select
    p.event_date,
    p.admin_dong_code,
    m.admin_dong,
    p.gu_code,
    m.gu,
    p.hotspot_count,
    round(p.ppltn_avg, 1) as ppltn_avg,
    round(p.ppltn_peak, 1) as ppltn_peak,
    coalesce(e.event_count, 0) as event_count,
    coalesce(e.event_count, 0) > 0 as has_event,
    coalesce(e.free_event_count, 0) as free_event_count,
    e.event_categories
from ppltn_dong p
left join events_daily e
    on p.event_date = e.event_date and p.admin_dong_code = e.admin_dong_code
left join {{ ref('asac_axes', 'dim_admin_dong') }} m
    on p.admin_dong_code = m.admin_dong_code

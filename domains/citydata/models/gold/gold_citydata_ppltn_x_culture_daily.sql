-- gold: 인구혼잡 × 문화활동(통합) (#122, 확장). grain = (event_date, admin_dong_code).
--
-- 우리 인구 silver 를 행정동×일 로 롤업하고, 그날 그 동에서 '활성' 인 **문화활동 6종**
-- (행사·축제·공연·전시·세종문화회관·KCISA행사)을 붙여 집객효과를 본다. 기존엔 서울
-- 문화행사(event) 하나만 봤으나, culture 의 6개 silver 가 모두 admin_dong_code +
-- event_start_date~event_end_date 공통이라 UNION 해 "이 동·날 전체 문화활동 수"로 확장.
-- 답: 문화활동 많은 동·날이 더 붐비나 / 어떤 유형이 붐빔과 관련되나.
--
-- 크로스도메인: culture 는 별도 dbt 프로젝트라 source() 로 참조(같은 카탈로그, schema=culture).
-- 조인축 admin_dong_code(라이브 B). 동 이름/구는 dim_admin_dong 조인. 커버리지: 우리
-- 121핫플이 속한 동 한정. 6종은 서로 다른 원천이라 소량 중복은 total 로 합산(교차 dedup 안 함).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
) }}

with ppltn_dong as (
    select
        cast(event_at as date) as event_date,
        admin_dong_code,
        max(gu_code) as gu_code,
        avg((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_avg,
        max((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_peak,
        count(distinct area_cd) as hotspot_count
    from {{ ref('silver_citydata_ppltn') }}
    where admin_dong_code is not null
    {% if is_incremental() %}
      and event_at >= (
        select coalesce(max(event_date), date '1970-01-01') - interval '1' day from {{ this }}
    )
    {% endif %}
    group by 1, 2
),

-- 문화활동 6종 공통축(동+기간)만 UNION. 각 원천을 ctype 으로 라벨.
culture_union as (
    select admin_dong_code, event_start_date, event_end_date, '행사' as ctype
        from {{ source('culture', 'silver_culture_event') }}
    union all select admin_dong_code, event_start_date, event_end_date, '축제'
        from {{ source('culture', 'silver_culture_festival') }}
    union all select admin_dong_code, event_start_date, event_end_date, '공연'
        from {{ source('culture', 'silver_culture_performance') }}
    union all select admin_dong_code, event_start_date, event_end_date, '전시'
        from {{ source('culture', 'silver_culture_exhibition') }}
    union all select admin_dong_code, event_start_date, event_end_date, '세종문화회관'
        from {{ source('culture', 'silver_culture_sejong') }}
    union all select admin_dong_code, event_start_date, event_end_date, 'KCISA행사'
        from {{ source('culture', 'silver_culture_kcisa_event') }}
),

-- 각 (동, 날)에 활성인 문화활동: 시작~종료 범위가 그날을 포함.
events_daily as (
    select
        p.event_date,
        p.admin_dong_code,
        count(*) as event_count,
        count_if(cu.ctype = '공연') as performance_count,
        count_if(cu.ctype = '전시') as exhibition_count,
        count_if(cu.ctype = '축제') as festival_count,
        array_join(array_distinct(array_agg(cu.ctype)), ', ') as event_types
    from ppltn_dong p
    join culture_union cu
        on cu.admin_dong_code = p.admin_dong_code
        and cu.admin_dong_code is not null
        and p.event_date between cu.event_start_date and cu.event_end_date
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
    coalesce(e.performance_count, 0) as performance_count,
    coalesce(e.exhibition_count, 0) as exhibition_count,
    coalesce(e.festival_count, 0) as festival_count,
    e.event_types
from ppltn_dong p
left join events_daily e
    on p.event_date = e.event_date and p.admin_dong_code = e.admin_dong_code
left join {{ ref('asac_axes', 'dim_admin_dong') }} m
    on p.admin_dong_code = m.admin_dong_code

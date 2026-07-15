-- gold: 승하차 × 교통돌발 (#122). grain = (time_bucket=시간, admin_dong_code).
--
-- 우리 승하차 silver 를 행정동×시간 으로 롤업하고, 그 시간 그 동에서 '활성' 인 교통돌발
-- (traffic.silver_seoul_traffic_incident, occurred_at~expected_clear_at 이 그 시간을 포함)을
-- 붙인다. 답: 돌발(사고/공사) 시간대에 인근 승하차가 어떻게 변하나.
--
-- 승하차 값은 5분 창(min~max)의 중앙값을 시간 내 평균낸 '대표 강도'(합산은 5분창이 겹쳐
-- 중복이라 avg 사용). subway+bus 합산(동 단위 총 이동성). observed_at 은 원천 시각 필드가
-- 없어 collected_at(KST) 이며 이를 시간으로 절삭해 time_bucket 으로 삼는다.
--
-- 크로스도메인: traffic 은 별도 프로젝트라 source()(같은 카탈로그, schema=traffic).
-- 조인축 admin_dong_code. 동 이름/구는 dim_admin_dong 조인. 커버리지=우리 핫플 동 한정.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
) }}

with transit_dong as (
    select
        date_trunc('hour', observed_at) as time_bucket,
        admin_dong_code,
        max(gu_code) as gu_code,
        avg((gton_5min_min + gton_5min_max) / 2.0) as board_5min_avg,
        avg((gtoff_5min_min + gtoff_5min_max) / 2.0) as alight_5min_avg,
        max((gton_5min_min + gton_5min_max) / 2.0) as board_5min_peak,
        count(distinct area_cd) as hotspot_count,
        count(distinct mode) as mode_count
    from {{ ref('silver_citydata_transit_ppltn') }}
    where admin_dong_code is not null
    {% if is_incremental() %}
      and observed_at >= (
        select coalesce(max(time_bucket), timestamp '1970-01-01') - interval '2' hour from {{ this }}
    )
    {% endif %}
    group by 1, 2
),

-- 각 (동, 시간)에 활성인 돌발: [발생시각 시간, 예상해제시각] 범위가 그 시간을 포함.
incidents as (
    select
        t.time_bucket,
        t.admin_dong_code,
        count(distinct i.source_record_id) as incident_count,
        array_join(array_distinct(array_agg(i.acc_type)), ', ') as acc_types
    from transit_dong t
    join {{ source('traffic', 'silver_seoul_traffic_incident') }} i
        on i.admin_dong_code = t.admin_dong_code
        and t.time_bucket between date_trunc('hour', i.occurred_at)
            and coalesce(i.expected_clear_at, i.occurred_at)
    group by 1, 2
)

select
    t.time_bucket,
    t.admin_dong_code,
    m.admin_dong,
    t.gu_code,
    m.gu,
    t.hotspot_count,
    t.mode_count,
    round(t.board_5min_avg, 1) as board_5min_avg,
    round(t.alight_5min_avg, 1) as alight_5min_avg,
    round(t.board_5min_peak, 1) as board_5min_peak,
    coalesce(i.incident_count, 0) as incident_count,
    coalesce(i.incident_count, 0) > 0 as has_incident,
    i.acc_types
from transit_dong t
left join incidents i
    on t.time_bucket = i.time_bucket and t.admin_dong_code = i.admin_dong_code
left join {{ ref('asac_axes', 'dim_admin_dong') }} m
    on t.admin_dong_code = m.admin_dong_code

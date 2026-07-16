-- gold_license_address_succession — 자리 승계: 폐업 후 같은 주소에 무엇이 들어오나.
--
-- 인사이트(#discovery/churn 확장): 폐업 업소별 **같은 도로명주소의 최근접 후속 개업 1건**
-- (0~365일)을 매칭 — "자리의 업종 고착성"(음식점 자리엔 음식점이 다시 드나) + 승계 속도.
-- 주소는 건물 단위라 근사임을 명시(호수 구분 없음 — M×N 팬아웃은 최근접 1건 매칭으로 제어).
-- grain = (closed_category, opened_category). materialized=table(소형 스냅샷).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with e as (
    select t.major, t.category, e.dataset, trim(e.road_address) as addr,
           case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.apvpermymd) end as o_iso,
           case when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.dcbymd) end as c_iso
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
    where e.road_address is not null and length(trim(e.road_address)) > 10
),

closed as (
    select major as closed_major, category as closed_category, addr, c_iso
    from e where c_iso is not null and c_iso >= '2015-01-01'
),

opened as (
    select major as opened_major, category as opened_category, addr, o_iso
    from e where o_iso is not null
),

matched as (
    select c.closed_major, c.closed_category, c.addr, c.c_iso,
           o.opened_major, o.opened_category,
           date_diff('day', try(from_iso8601_date(c.c_iso)), try(from_iso8601_date(o.o_iso))) as gap_days,
           row_number() over (partition by c.addr, c.c_iso, c.closed_category
                              order by o.o_iso) as rn
    from closed c
    join opened o
      on o.addr = c.addr
     and o.o_iso >= c.c_iso
     and o.o_iso <= cast(cast(try(from_iso8601_date(c.c_iso)) + interval '365' day as date) as varchar)
)

select closed_major, closed_category, opened_major, opened_category,
       {{ label_major_ko('closed_major') }}       as closed_major_ko,
       {{ label_category_ko('closed_category') }} as closed_category_ko,
       {{ label_major_ko('opened_major') }}       as opened_major_ko,
       {{ label_category_ko('opened_category') }} as opened_category_ko,
       count(*)                              as successions,
       round(avg(gap_days), 1)               as avg_gap_days,
       approx_percentile(gap_days, 0.5)      as p50_gap_days,
       count_if(gap_days <= 90)              as within_90d
from matched
where rn = 1 and gap_days is not null and gap_days >= 0
group by 1, 2, 3, 4

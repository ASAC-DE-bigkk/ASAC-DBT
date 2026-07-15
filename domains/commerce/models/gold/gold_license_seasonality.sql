-- gold_license_seasonality — 개업/폐업의 월중 계절성(month-of-year 1~12) × 업종 3단.
--
-- 인사이트(#discovery): "어느 달에 개업/폐업이 몰리나" — flow_monthly(절대 시계열)와 달리
-- **연도 무관 월 패턴**. 최근 10년 완결연도만 사용(구조 변화·당해 미완결 왜곡 차단).
-- materialized=table(소형 — 스냅샷 재계산. D1 은 스냅샷 교체).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with e as (
    select t.major, t.category, e.dataset,
           case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.apvpermymd) end as o_iso,
           case when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.dcbymd) end as c_iso
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
),

bounds as (
    select substr(cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar), 1, 4) as cur_y
),

ev as (
    select 'opened' as event_type, substr(o_iso, 6, 2) as month_of_year, major, category, dataset
    from e cross join bounds
    where o_iso is not null
      and substr(o_iso, 1, 4) >= cast(cast(cur_y as integer) - 10 as varchar)
      and substr(o_iso, 1, 4) <  cur_y                    -- 완결연도만
    union all
    select 'closed', substr(c_iso, 6, 2), major, category, dataset
    from e cross join bounds
    where c_iso is not null
      and substr(c_iso, 1, 4) >= cast(cast(cur_y as integer) - 10 as varchar)
      and substr(c_iso, 1, 4) <  cur_y
)

select event_type, month_of_year, major, category, dataset,
       count(*) as cnt
from ev
where month_of_year between '01' and '12'
group by 1, 2, 3, 4, 5

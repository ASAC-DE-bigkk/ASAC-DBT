-- gold: 장소별 일 소비 인사이트 (#69). grain = (event_date, area_cd).
--
-- silver_citydata_cmrcl(10분 슬라이스)을 하루 단위로 집계 — 결제 규모·피크 시간대·
-- 활성(바쁜/분주한) 비율·측정 완결성. gold_seoul_ppltn_daily 와 같은 패턴:
-- incremental(merge) 로 **최근 2일치만 재집계** 후 (event_date, area_cd) 키로 merge.
-- 당일 슬라이스가 늦게 도착해도 다음 run 재집계가 흡수한다(멱등).

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['event_date', 'area_cd'],
    on_table_exists='drop',
) }}

with slices as (
    select *
    from {{ ref('silver_citydata_cmrcl') }}
    {% if is_incremental() %}
    where event_at >= (
        select coalesce(max(event_date), date '1970-01-01') - interval '1' day
        from {{ this }}
    )
    {% endif %}
)

select
    cast(event_at as date) as event_date,
    area_cd,
    max(area_nm) as area_nm,
    max(area_category) as area_category,
    max(gu) as gu,
    max(admin_dong) as admin_dong,
    max(gu_code) as gu_code,
    max(admin_dong_code) as admin_dong_code,
    max(longitude) as longitude,
    max(latitude) as latitude,
    sum(payment_count) as payment_count_total,
    round(avg(payment_count), 1) as payment_count_avg,
    max(payment_amt_max) as payment_amt_peak,
    max_by(event_at, payment_count) as peak_at,
    max_by(cmrcl_lvl, payment_count) as peak_cmrcl_lvl,
    round(100.0 * count_if(cmrcl_lvl in ('바쁜', '분주한')) / count(*), 1) as busy_ratio_percent,
    count(*) as measurement_count
from slices
group by 1, 2

-- gold: 장소별 일 소비 인사이트 (#69). grain = (event_date, area_cd).
--
-- silver_citydata_cmrcl(10분 슬라이스)을 하루 단위로 집계 — 결제 규모·피크 시간대·
-- 활성(바쁜/분주한) 비율·측정 완결성. 공간축: silver는 코드·좌표만 담고 이름은
-- dim_seoul_area 조인으로 붙인다(#115). incremental(delete+insert) 로 최근 2일치만
-- 재집계 후 (event_date, area_cd) 키로 delete+insert (멱등).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='incremental',
    incremental_strategy='delete+insert',
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
),

agg as (
    select
        cast(event_at as date) as event_date,
        area_cd,
        max(gu_code) as gu_code,               -- area 당 상수
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
)

select
    a.event_date,
    a.area_cd,
    dim.area_nm,
    dim.area_category,
    dim.gu,
    dim.admin_dong,
    a.gu_code,
    a.admin_dong_code,
    a.longitude,
    a.latitude,
    a.payment_count_total,
    a.payment_count_avg,
    a.payment_amt_peak,
    a.peak_at,
    a.peak_cmrcl_lvl,
    a.busy_ratio_percent,
    a.measurement_count
from agg a
left join {{ ref('dim_seoul_area') }} dim on a.area_cd = dim.area_cd

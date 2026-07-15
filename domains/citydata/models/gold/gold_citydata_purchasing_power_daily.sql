-- gold: 장소별 일 구매력·붐빔대비구매 (#122). grain = (event_date, area_cd).
--
-- silver_citydata_ppltn(유동인구) 와 silver_citydata_cmrcl(결제) 를 각각 하루로 집계해
-- 조인, "붐빔 대비 구매" 지수를 낸다. 세 관점을 한 마트로:
--   * buy_per_crowd_idx  = 결제건수 / 평균 유동인구  (붐빔 대비 구매)
--   * spend_per_crowd_idx = 결제금액 / 평균 유동인구  (구매력 proxy)
--   * rank_spend / rank_spend_in_gu → Top10=상위, 구매력 약한 지역=하위
-- ⚠ 유동인구(area_ppltn_min~max)는 '동시 체류 추정(stock)' 이라 이 지수는 문자 그대로의
--   1인당이 아니라 **장소 간 상대 비교용 지수**다. 랭킹은 event_date 파티션 내에서 매겨
--   증분(최근 2일 재집계)에도 해당 날짜 전체가 함께 재계산되어 정합하다.
-- 공간축: silver 는 코드·좌표만, 이름은 dim_seoul_area 조인(#115).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
) }}

with ppltn as (
    select
        cast(event_at as date) as event_date,
        area_cd,
        max(admin_dong_code) as admin_dong_code,
        max(gu_code) as gu_code,
        max(longitude) as longitude,
        max(latitude) as latitude,
        avg((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_avg,
        max((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_peak,
        max_by(area_congest_lvl, (area_ppltn_min + area_ppltn_max) / 2.0) as congest_peak_lvl,
        count(*) as ppltn_measure_count
    from {{ ref('silver_citydata_ppltn') }}
    {% if is_incremental() %}
    where event_at >= (
        select coalesce(max(event_date), date '1970-01-01') - interval '1' day from {{ this }}
    )
    {% endif %}
    group by 1, 2
),

cmrcl as (
    select
        cast(event_at as date) as event_date,
        area_cd,
        sum(payment_count) as payment_cnt_total,
        sum((payment_amt_min + payment_amt_max) / 2) as payment_amt_total,
        max(payment_amt_max) as payment_amt_peak,
        count(*) as cmrcl_measure_count
    from {{ ref('silver_citydata_cmrcl') }}
    {% if is_incremental() %}
    where event_at >= (
        select coalesce(max(event_date), date '1970-01-01') - interval '1' day from {{ this }}
    )
    {% endif %}
    group by 1, 2
),

joined as (
    select
        p.event_date,
        p.area_cd,
        p.admin_dong_code,
        p.gu_code,
        p.longitude,
        p.latitude,
        round(p.ppltn_avg, 1) as ppltn_avg,
        round(p.ppltn_peak, 1) as ppltn_peak,
        p.congest_peak_lvl,
        p.ppltn_measure_count,
        c.payment_cnt_total,
        c.payment_amt_total,
        c.payment_amt_peak,
        c.cmrcl_measure_count,
        round(c.payment_cnt_total / nullif(p.ppltn_avg, 0), 4) as buy_per_crowd_idx,
        round(c.payment_amt_total / nullif(p.ppltn_avg, 0), 1) as spend_per_crowd_idx
    from ppltn p
    left join cmrcl c
        on p.event_date = c.event_date and p.area_cd = c.area_cd
),

ranked as (
    select
        *,
        rank() over (
            partition by event_date order by spend_per_crowd_idx desc nulls last
        ) as rank_spend,
        rank() over (
            partition by event_date, gu_code order by spend_per_crowd_idx desc nulls last
        ) as rank_spend_in_gu
    from joined
)

select
    r.event_date,
    r.area_cd,
    dim.area_nm,
    dim.area_category,
    dim.gu,
    dim.admin_dong,
    r.gu_code,
    r.admin_dong_code,
    r.longitude,
    r.latitude,
    r.ppltn_avg,
    r.ppltn_peak,
    r.congest_peak_lvl,
    r.payment_cnt_total,
    r.payment_amt_total,
    r.payment_amt_peak,
    r.buy_per_crowd_idx,
    r.spend_per_crowd_idx,
    r.rank_spend,
    r.rank_spend_in_gu,
    r.ppltn_measure_count,
    r.cmrcl_measure_count
from ranked r
left join {{ ref('dim_seoul_area') }} dim on r.area_cd = dim.area_cd

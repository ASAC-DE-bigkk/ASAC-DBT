-- gold: 뜨는 상권 지수. grain = area_cd (장소당 현재 1행).
--
-- "지금 뜨는 상권 어디?" — 붐빔이 오르고(추세) + 구매력 높고(spend/붐빔) + 결제 볼륨 큰 곳을
-- 결합한 종합 지수. 세 축을 백분위(0~1)로 정규화해 평균 → hot_index(0~1, 높을수록 핫).
--
-- trend(붐빔 변화) + purchasing_power(구매력·결제, 최근일) 파생 table. 챗봇 "요즘 뜨는 상권?"용.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
) }}

with pw as (
    select area_cd, spend_per_crowd_idx, payment_cnt_total
    from {{ ref('gold_citydata_purchasing_power_daily') }}
    where event_date = (select max(event_date) from {{ ref('gold_citydata_purchasing_power_daily') }})
),

base as (
    select
        t.area_cd, t.area_nm, t.gu, t.gu_code, t.admin_dong,
        t.cur_ppltn, t.change_pct, t.trend,
        coalesce(pw.spend_per_crowd_idx, 0) as spend_idx,
        coalesce(pw.payment_cnt_total, 0) as payment_total
    from {{ ref('gold_citydata_ppltn_trend') }} t
    left join pw on pw.area_cd = t.area_cd
)

select
    area_cd, area_nm, gu, gu_code, admin_dong,
    cur_ppltn, change_pct, trend, spend_idx, payment_total,
    round((
        percent_rank() over (order by change_pct)
      + percent_rank() over (order by spend_idx)
      + percent_rank() over (order by payment_total)
    ) / 3.0, 3) as hot_index
from base

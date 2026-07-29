-- gold: 장소 스코어카드. grain = area_cd (장소당 현재 1행).
--
-- 챗봇 핵심 골드 — "강남역 어때?" 한 번에 답하도록 **한 행에 전부** 모은다: 현재 혼잡·인구,
-- 상권(결제)·교통(승차)·날씨·따릉이(place_latest) + 평소대비 이상(anomaly) + 실시간 추세(trend)
-- + 구매력(purchasing_power). LLM 이 area_cd 로 1행 읽어 바로 자연어 답변.
--
-- 여러 골드를 area_cd 로 합친 table (매 run 재빌드). Text-to-SQL/도구호출 챗봇의 대표 조회 대상.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
) }}

with pw as (
    select area_cd, spend_per_crowd_idx, rank_spend
    from {{ ref('gold_citydata_purchasing_power_daily') }}
    where event_date = (select max(event_date) from {{ ref('gold_citydata_purchasing_power_daily') }})
)

select
    p.area_cd,
    p.area_nm,
    p.area_category,
    p.gu,
    p.admin_dong,
    -- 현재 상태 (place_latest)
    p.area_congest_lvl,
    p.area_ppltn_min,
    p.area_ppltn_max,
    p.cmrcl_lvl,
    p.payment_count,
    p.subway_gton_30min,
    p.bus_gton_30min,
    p.sbike_parking_total,
    p.sbike_rack_total,
    p.temperature,
    p.pm25,
    p.pm25_index,
    -- 평소 대비 이상 (anomaly)
    a.base_mean,
    a.pct_vs_normal,
    a.z_score,
    -- 실시간 추세 (trend)
    t.change_pct,
    t.trend,
    -- 구매력 (purchasing_power, 최근일)
    pw.spend_per_crowd_idx,
    pw.rank_spend,
    p.refreshed_at
from {{ ref('gold_citydata_place_latest') }} p
left join {{ ref('gold_citydata_ppltn_anomaly') }} a on a.area_cd = p.area_cd
left join {{ ref('gold_citydata_ppltn_trend') }} t on t.area_cd = p.area_cd
left join pw on pw.area_cd = p.area_cd

-- gold(Q&A metric): 재난 경보 요일×시간 패턴. grain (dow, hr, dst_type).
--
-- "재난 경보가 주로 언제 오나" — 폭염은 한낮, 호우·대설은 특정 시간대 등 발령 패턴.
-- 지역 곱을 빼려 distinct 발령(event_at, dst_type)만 세고, 요일×시간으로 롤업한다.
--
-- ⚠ 표본 주의: 재난은 드물어(폭염 위주, ~3주) 셀당 표본이 얇다. base_n·reliable(base_n>=5)을
--   동봉해 소비측이 표본 적은 셀을 참고용으로 캐비앳하게 한다(다른 dow_hour 골드와 동형, 임계만 낮춤).
{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
) }}

with events as (
    -- 광역 중복 제거: 같은 발령(시각·유형·단계)은 1건으로
    select distinct event_at, dst_type, emrg_step
    from {{ ref('silver_citydata_dst_message') }}
)

select
    day_of_week(event_at)          as dow,          -- 1=월 … 7=일 (Trino day_of_week)
    hour(event_at)                 as hr,           -- 0 … 23
    dst_type,
    count(*)                       as alert_count,  -- 그 요일·시간대 발령 수
    count(distinct date(event_at)) as active_days,  -- 발령된 날 수
    (count(*) >= 5)                as reliable       -- 표본 충분 여부(재난 드묾 — 임계 5)
from events
group by day_of_week(event_at), hour(event_at), dst_type

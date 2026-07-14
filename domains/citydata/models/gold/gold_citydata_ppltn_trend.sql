-- gold: 인구혼잡 실시간 추세. grain = area_cd (장소당 현재 1행).
--
-- "지금 뜨는/식는 곳" — 최근 30분 평균 붐빔 vs 그 이전 30분 평균의 변화율. 챗봇 "지금 어디
-- 뜨고 있어?" / 급증 감지용. by_time(5분 간격) 최근 12버킷(=1시간)을 반으로 나눠 비교.
--
-- by_time 파생 view (조회 시 최신). area_cd 로 1행 읽어 상승/하락·변화율 답변.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='view',
) }}

with ranked as (
    select
        area_cd, area_nm, gu, gu_code, admin_dong, admin_dong_code,
        event_at, avg_ppltn, area_congest_lvl,
        row_number() over (partition by area_cd order by event_at desc) as rn
    from {{ ref('gold_citydata_ppltn_by_time') }}
    where avg_ppltn is not null
),

-- 최근 1시간(12버킷)을 30분씩 둘로: 최근 30분(rn 1~6) vs 이전 30분(rn 7~12)
windows as (
    select
        area_cd,
        avg(if(rn <= 6, avg_ppltn)) as last_30min,
        avg(if(rn > 6 and rn <= 12, avg_ppltn)) as prev_30min
    from ranked
    where rn <= 12
    group by 1
)

select
    c.area_cd,
    c.area_nm,
    c.gu,
    c.gu_code,
    c.admin_dong,
    c.admin_dong_code,
    c.event_at,
    round(c.avg_ppltn, 0) as cur_ppltn,
    c.area_congest_lvl,
    round(w.last_30min, 0) as last_30min,
    round(w.prev_30min, 0) as prev_30min,
    round(w.last_30min / nullif(w.prev_30min, 0) - 1, 3) as change_pct,
    case
        when w.last_30min > w.prev_30min * 1.05 then '증가'
        when w.last_30min < w.prev_30min * 0.95 then '감소'
        else '유지'
    end as trend
from ranked c
join windows w on w.area_cd = c.area_cd
where c.rn = 1

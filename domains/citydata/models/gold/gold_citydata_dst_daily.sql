-- gold: 일별 재난 경보 시계열. grain (event_date, dst_type, emrg_step).
--
-- "언제 무슨 재난 경보가 얼마나 발령됐나" — 폭염·호우·대설 등 일별 발령 현황.
-- 재난문자는 대체로 광역(같은 문자가 여러 지역에 동시 수록)이라, 지역 곱을 그대로 세면 과대집계된다.
-- → distinct 발령시각(event_at)으로 경보 수를, distinct 지역으로 영향 범위를 따로 집계한다.
-- 평시엔 재난이 없어 그 날짜 행 자체가 없음(정상 0건). 시간축 = event_date.
{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
) }}

select
    date(event_at)              as event_date,
    dst_type,
    emrg_step,
    count(distinct event_at)    as alert_count,        -- 그 날 서로 다른 발령시각 수
    count(distinct area_cd)     as affected_areas,     -- 영향 지역 수 (광역≈120, 국지=소수)
    min(event_at)               as first_alert_at,
    max(event_at)               as last_alert_at,
    max_by(msg_cn, event_at)    as latest_message      -- 가장 최근 발령 메시지 본문
from {{ ref('silver_citydata_dst_message') }}
group by date(event_at), dst_type, emrg_step

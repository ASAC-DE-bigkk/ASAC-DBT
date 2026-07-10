-- 미래 행사 재고 감시(#111) — 소스가 신규 공급을 멈추면 max(event_start_date)가
-- current_date 로 다가온다. event-time(등록 시각) 부재의 유일한 proxy.
-- warn 계측 전용: 이미 등록된 미래 재고가 남으면 신규 정체를 못 잡는 원천 한계(설계 §3).
-- error 하드게이트 아님(culture 는 미래 시작일이 정상).
{{ config(severity='warn') }}

with sources as (
    select 'event'       as src, max(event_start_date) as max_start from {{ ref('silver_culture_event') }}
    union all select 'performance', max(event_start_date) from {{ ref('silver_culture_performance') }}
    union all select 'festival',    max(event_start_date) from {{ ref('silver_culture_festival') }}
    union all select 'exhibition',  max(event_start_date) from {{ ref('silver_culture_exhibition') }}
    union all select 'sejong',      max(event_start_date) from {{ ref('silver_culture_sejong') }}
    union all select 'kcisa',       max(event_start_date) from {{ ref('silver_culture_kcisa_event') }}
)
select src, max_start
from sources
where max_start is null
   or max_start < date_add('day', {{ var('culture_future_coverage_days', 14) }}, current_date)

-- boxoffice 공간축 승계율 감시(#509) — gold_culture_boxoffice_daily 의 자치구는
-- performance(→facility) 경유 best-effort 승계라(#270), KOPIS 공연목록에 없는
-- 공연은 비는 게 정상이다. 다만 승계율이 바닥이면 조인 키(performance_id) 회귀나
-- 상류 결손 신호이므로 warn 계측으로 감시한다. 최신 스냅샷 기준.
{{ config(severity='warn') }}

with latest as (
    select gu_code
    from {{ ref('gold_culture_boxoffice_daily') }}
    where snapshot_date = (select max(snapshot_date) from {{ ref('gold_culture_boxoffice_daily') }})
)

select
    count(*)                                as total_rows,
    count(gu_code)                          as inherited_rows,
    round(count(gu_code) * 1.0 / count(*), 3) as inherit_rate
from latest
having count(*) > 0
   and count(gu_code) * 1.0 / count(*) < {{ var('culture_boxoffice_spatial_inherit_min', 0.3) }}

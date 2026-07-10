-- #85: silver_culture_kcisa_event 에 3축(performance·event·exhibition) 교차 중복이
-- 남아 있으면 실패. 매칭 = 정규화 제목 일치 + (기간 교차 or 한쪽 기간 null).
with k as (
    select event_id, {{ culture_norm_title('title') }} as norm_title,
           event_start_date, event_end_date
    from {{ ref('silver_culture_kcisa_event') }}
),

axes as (
    select {{ culture_norm_title('performance_name') }} as norm_title,
           event_start_date, event_end_date
    from {{ ref('silver_culture_performance') }}
    union all
    select {{ culture_norm_title('event_title') }}, event_start_date, event_end_date
    from {{ ref('silver_culture_event') }}
    union all
    select {{ culture_norm_title('title') }}, event_start_date, event_end_date
    from {{ ref('silver_culture_exhibition') }}
    where title is not null
)

select k.event_id
from k
join axes a on a.norm_title = k.norm_title
where a.event_start_date is null or a.event_end_date is null
   or k.event_start_date is null or k.event_end_date is null
   or (a.event_start_date <= k.event_end_date and a.event_end_date >= k.event_start_date)

-- #85: silver_culture_kcisa_event 에 3축(performance·event·exhibition) 교차 중복이
-- 남아 있으면 실패. 매칭 = 정규화 제목 일치 + (기간 교차 or 한쪽 기간 null).
-- 기간 조건은 모델의 anti-join 과 같은 culture_period_overlap_or_null 매크로(#199) —
-- 모델·테스트가 한 정의를 공유해 규칙 드리프트가 구조적으로 불가능하다.
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
where {{ culture_period_overlap_or_null('a', 'k') }}

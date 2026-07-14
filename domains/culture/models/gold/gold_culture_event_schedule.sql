-- gold: 문화행사 목록 질의 표면 (행사 1행, #187). sports_schedule(#90)과 같은 패턴 —
--   "이번 주말 종로구 행사" = where gu_code=... and event_start_date <= :주말끝 and event_end_date >= :주말시작
-- 집계 gold(location_daily·activity_by_dong)가 못 답하는 "그래서 뭐 하는데?"(제목·장소·기간)를 담당.
-- 크로스소스 dedup: norm_title×시작일×gu 일치 시 전문 소스 우선(performance>exhibition>festival>sejong>kcisa>event)
--   — 서울문화행사(event)는 종합 수집 소스라 타 소스와 중복이 잦아 후순위. gu를 축에 넣어
--   같은 제목·같은 날짜의 타 지역 별개 행사를 오병합하지 않는다.
-- 기간 검증은 int_culture_activity_days 와 동일 기준(시작≤종료, 400일 상한).

with unioned as (
    select
        'event:' || event_key                        as event_ref,
        'event'                                      as event_type,
        event_title                                  as title,
        category,
        place                                        as venue_name,
        is_free,
        event_start_date, event_end_date, event_at,
        gu, gu_code, admin_dong, admin_dong_code,
        latitude, longitude, quality_status,
        6 as source_priority
    from {{ ref('silver_culture_event') }}

    union all
    select
        'performance:' || cast(performance_id as varchar),
        'performance',
        performance_name,
        genre,
        venue_name,
        cast(null as varchar),
        event_start_date, event_end_date, event_at,
        gu, gu_code, admin_dong, admin_dong_code,
        latitude, longitude, quality_status,
        1
    from {{ ref('silver_culture_performance') }}

    union all
    select
        'exhibition:' || cast(exhibition_id as varchar),
        'exhibition',
        title,
        cast(null as varchar),
        venue_name,
        cast(null as varchar),
        event_start_date, event_end_date, event_at,
        gu, gu_code, admin_dong, admin_dong_code,
        latitude, longitude, quality_status,
        2
    from {{ ref('silver_culture_exhibition') }}

    union all
    select
        'festival:' || cast(festival_id as varchar),
        'festival',
        festival_name,
        genre,
        venue_name,
        cast(null as varchar),
        event_start_date, event_end_date, event_at,
        gu, gu_code, admin_dong, admin_dong_code,
        latitude, longitude, quality_status,
        3
    from {{ ref('silver_culture_festival') }}

    union all
    select
        'sejong:' || cast(sejong_id as varchar),
        'sejong',
        title,
        genre,
        venue_name,
        cast(null as varchar),
        event_start_date, event_end_date, event_at,
        gu, gu_code, admin_dong, admin_dong_code,
        latitude, longitude, quality_status,
        4
    from {{ ref('silver_culture_sejong') }}

    union all
    select
        'kcisa:' || cast(event_id as varchar),
        'kcisa',
        title,
        category,
        venue_name,
        cast(null as varchar),
        event_start_date, event_end_date, event_at,
        gu, gu_code, admin_dong, admin_dong_code,
        latitude, longitude, quality_status,
        5
    from {{ ref('silver_culture_kcisa_event') }}
),

valid as (
    select * from unioned
    where title is not null
      and event_start_date is not null
      and event_end_date is not null
      and event_end_date >= event_start_date
      and date_diff('day', event_start_date, event_end_date) <= 400
),

deduped as (
    select * from (
        select *, row_number() over (
            partition by {{ culture_norm_title('title') }}, event_start_date, coalesce(gu_code, '')
            order by source_priority, event_ref
        ) as rn
        from valid
    ) where rn = 1
)

select
    event_ref, event_type, title, category, venue_name, is_free,
    event_start_date, event_end_date, event_at,
    gu, gu_code, admin_dong, admin_dong_code,
    latitude, longitude, quality_status
from deduped

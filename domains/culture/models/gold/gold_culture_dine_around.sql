-- gold(크로스도메인): 동별 문화 밀도 × 요식업 스톡 — "공연 보고 밥 먹기 좋은 동네"(#308, 티어링 v2 #8).
--   그레인: admin_dong_code (426동 스카폴드 = activity_by_dong 전체 유지, 요식업은 left join).
--   문화 축 = 다가오는 90일 행사량(current_date 기준 — 빌드 시점마다 창이 굴러감, 일 배치 전제).
--   요식업 축 = commerce 인허가 스톡(category='food' active). culture 첫 commerce read (source 경유).
--   ⚠ commerce 동 매핑 커버리지 219/426동(51.4%, 7/21 실측) — 미커버 동은 has_dining_data=false,
--   dining_*·dining_stock_pctl·dine_around_score 모두 null (동 자체는 스카폴드에 남는다).
--   score = 두 축 percent_rank 기하평균: 둘 다 높아야 높다. 순위 질의는 score desc 정렬.

with culture as (
    select
        admin_dong_code,
        max(admin_dong)                as admin_dong,
        max(gu_code)                   as gu_code,
        max(gu)                        as gu,
        sum(case when event_date between current_date and current_date + interval '90' day
                 then activities_count else 0 end)   as events_upcoming_90d,
        sum(case when event_date between current_date and current_date + interval '90' day
                 then performances_count else 0 end) as performances_upcoming_90d
    from {{ ref('gold_culture_activity_by_dong') }}
    group by admin_dong_code
),

dining as (
    select
        admin_dong_code,
        sum(active_cnt)          as dining_active_cnt,
        sum(opened_last_365d)    as dining_opened_365d
    from {{ source('commerce_gold', 'gold_license_dong_category_matrix') }}
    where category = 'food'
    group by admin_dong_code
),

joined as (
    select
        c.admin_dong_code,
        c.admin_dong,
        c.gu_code,
        c.gu,
        c.events_upcoming_90d,
        c.performances_upcoming_90d,
        d.dining_active_cnt,
        d.dining_opened_365d,
        d.admin_dong_code is not null as has_dining_data
    from culture c
    left join dining d on d.admin_dong_code = c.admin_dong_code
),

ranked as (
    select
        *,
        percent_rank() over (order by events_upcoming_90d) as culture_events_pctl,
        -- 요식업 pctl 은 데이터 있는 동끼리만 경쟁 (partition 으로 분리 후 false 쪽은 버림)
        case when has_dining_data
             then percent_rank() over (partition by has_dining_data order by dining_active_cnt)
        end as dining_stock_pctl
    from joined
)

select
    admin_dong_code,
    admin_dong,
    gu_code,
    gu,
    cast(events_upcoming_90d as integer)        as events_upcoming_90d,
    cast(performances_upcoming_90d as integer)  as performances_upcoming_90d,
    cast(dining_active_cnt as integer)          as dining_active_cnt,
    cast(dining_opened_365d as integer)         as dining_opened_365d,
    has_dining_data,
    round(culture_events_pctl, 3)               as culture_events_pctl,
    round(dining_stock_pctl, 3)                 as dining_stock_pctl,
    round(sqrt(culture_events_pctl * dining_stock_pctl), 3) as dine_around_score
from ranked

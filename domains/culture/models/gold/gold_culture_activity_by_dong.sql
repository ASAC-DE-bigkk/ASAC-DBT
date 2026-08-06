-- gold: 행정동(admin_dong) × 일자 문화활동 집계 — bronze canonical 소비 첫 gold(#48).
-- dim_admin_dong(426동)을 활동 일자 spine과 cross join한 scaffold에 활동을 left join →
-- 활동 0건 행정동도 0으로 행 존재(지도 빈칸 방지, dim 문서 권장 패턴).
-- sports(야구)는 문화활동 축 아님 → 제외(gold_culture_location_daily 관례 유지).
-- 주의(#111): admin_dong_code 그레인이라 정의상 quality_status='dong_precise' 활동만 포함된다.
--   좌표 없는 활동(gu_only)은 이 gold 에서 누락 — 구 레벨 집계는 gold_culture_location_daily 참조.
-- 활동 원천·기간 전개는 int_culture_activity_days 공유. kcisa 는 activity_type 별도 유지(kcisa_count).
-- free/edu 카운트(#280): free_access(티어링 #19) 흡수 — event 소스만 유무료·카테고리 보유.
--   해석적 이름(family_friendly) 대신 기술적 카운트만 — "가족적합" 해석은 Q&A 레이어 몫(governed).
-- 🔑 유형 열은 합산용이 아니다(#406) — activities_count 가 총계의 정본이다:
--   원천 유형 5종  performances·events·exhibitions·sejong·kcisa
--   부분집합 지표 4종  festivals(KOPIS 축제) · free_events·edu_experience_events·
--                     festival_events(행사 중 일부) → 위 5종과 겹친다, 더하면 중복
--   kopis_festivals_count 를 원천 유형처럼 6번째로 세면 KOPIS 축제가 공연과 이중계상된다
--   — mt20id 를 공연목록·축제목록이 공유하기 때문이고, 실측으로 합이 1,106 어긋났다.
--   ⚠ 반대로 "5종 합 == activities_count" 도 불변식이 아니다: 축제목록에만 잡히는 날이
--   있으면(두 API 의 기간 정보가 다를 수 있다) 어느 유형 열에도 안 잡힌다. 이 그레인의
--   현재 데이터에선 0건이지만, 같은 원천을 쓰는 location_daily 는 gu 축에서 522 활동-일이
--   그 경우다. 그래서 총계는 언제나 activities_count 를 쓰게 계약에 못 박았다.

with dim as (
    select admin_dong_code, admin_dong, gu_code, gu, stat_region_cd
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),

expanded as (
    select admin_dong_code, activity_id, activity_type, activity_date, is_free, category, collected_at
    from {{ ref('int_culture_activity_days') }}
    where admin_dong_code is not null
),

-- date_spine 은 최근 창 [today-90, today+365] 으로 제한 — 27년치 scaffold(3.9M행·96% 0)
-- 방지. "0건 동 표현"은 현재~근미래 지도에만 유의미(과거/먼미래 0-fill 불요).
date_spine as (
    select distinct activity_date as event_date
    from expanded
    where activity_date between date_add('day', -90, current_date)
                           and date_add('day', 365, current_date)
),

scaffold as (
    select dim.admin_dong_code, dim.admin_dong, dim.gu_code, dim.gu, dim.stat_region_cd, ds.event_date
    from dim
    cross join date_spine ds
),

agg as (
    select
        admin_dong_code,
        activity_date as event_date,
        -- 신선도 축(#707) — 이 칸의 집계에 쓰인 원천이 마지막으로 수집된 시각.
        -- event_date 는 미래 1년까지 뻗는 달력이라 신선도가 될 수 없다.
        -- 활동이 없는 스캐폴드 칸은 NULL 이고, 그게 맞다(원천이 없다).
        max(collected_at) as source_collected_at,
        count(distinct activity_id) as activities_count,
        count(distinct case when activity_type = 'performance' then activity_id end) as performances_count,
        count(distinct case when activity_type = 'event'       then activity_id end) as events_count,
        count(distinct case when activity_type = 'festival'    then activity_id end) as kopis_festivals_count,
        count(distinct case when activity_type = 'exhibition'  then activity_id end) as exhibitions_count,
        count(distinct case when activity_type = 'sejong'      then activity_id end) as sejong_count,
        count(distinct case when activity_type = 'kcisa'       then activity_id end) as kcisa_count,
        count(distinct case when activity_type = 'event' and is_free = '무료'      then activity_id end) as free_events_count,
        count(distinct case when activity_type = 'event' and category = '교육/체험' then activity_id end) as edu_experience_events_count,
        -- 서울시 문화행사의 축제 분류 6종(축제-문화/예술·기타·전통/역사·자연/경관·시민화합·관광/체육).
        -- kopis_festivals_count(KOPIS)와 다른 원천이다 — 소비자가 "축제"로 기대하는 쪽은 이 열이고,
        -- 이 창에서 KOPIS 축제(1,106 활동-일)보다 크다(1,813). 접두 매칭인 이유는 분류가
        -- '축제-<세부>' 형태로 세분되고 세부 항목이 늘 수 있어서다.
        count(distinct case when activity_type = 'event' and category like '축제%' then activity_id end) as festival_events_count
    from expanded
    group by admin_dong_code, activity_date
)

select
    s.admin_dong_code, s.admin_dong, s.gu_code, s.gu, s.stat_region_cd,
    s.event_date,
    coalesce(a.activities_count, 0)   as activities_count,
    coalesce(a.performances_count, 0) as performances_count,
    coalesce(a.events_count, 0)       as events_count,
    coalesce(a.kopis_festivals_count, 0) as kopis_festivals_count,
    coalesce(a.exhibitions_count, 0)  as exhibitions_count,
    coalesce(a.sejong_count, 0)       as sejong_count,
    coalesce(a.kcisa_count, 0)        as kcisa_count,
    coalesce(a.free_events_count, 0)            as free_events_count,
    coalesce(a.edu_experience_events_count, 0)  as edu_experience_events_count,
    coalesce(a.festival_events_count, 0)        as festival_events_count,
    -- coalesce 하지 않는다 — 활동 없는 칸은 원천이 없으므로 NULL 이 정직하다.
    -- Publisher 는 NULL 이 아닌 값들의 max() 를 신선도로 쓴다(#707).
    a.source_collected_at
from scaffold s
left join agg a on a.admin_dong_code = s.admin_dong_code and a.event_date = s.event_date

-- gold: culture 활동(공연·행사·축제·전시·세종·kcisa)을 gu_code × 일자로 집계 — #48 코드 축.
-- 활동 원천·기간 전개는 int_culture_activity_days 공유(gold_culture_activity_by_dong 과 동일 원천).
-- kcisa 는 type_bucket 으로 기존 type 에 병합 — 별도 kcisa 카운트 없음. 그레인: gu_code × event_date.

with activities as (
    select * from {{ ref('int_culture_activity_days') }}
    where gu_code is not null
)

select
    gu_code,
    max(gu) as gu,
    activity_date as event_date,
    count(distinct activity_id) as activities_count,
    count(distinct case when type_bucket = 'performance' then activity_id end) as performances_count,
    count(distinct case when type_bucket = 'event'       then activity_id end) as events_count,
    count(distinct case when type_bucket = 'festival'    then activity_id end) as festivals_count,
    count(distinct case when type_bucket = 'exhibition'  then activity_id end) as exhibitions_count,
    count(distinct case when type_bucket = 'sejong'      then activity_id end) as sejong_count,
    count(distinct case when quality_status = 'dong_precise' then activity_id end) as dong_precise_count
from activities
group by gu_code, activity_date

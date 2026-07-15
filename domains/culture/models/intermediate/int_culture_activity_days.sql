{{ config(materialized='ephemeral') }}

-- 두 gold(gold_culture_location_daily·gold_culture_activity_by_dong)가 공유하는 활동
-- 원천: 6개 silver union → 기간 검증 → 일자 전개(unnest sequence). 공간 not-null 필터는
-- 각 gold이 자기 축(gu_code / admin_dong_code)으로 적용하므로 여기서 걸지 않는다(행 단위
-- 속성이라 전개 전/후 필터 결과 동일).
-- kcisa 처리 차이(location=기존 type 병합 / by_dong=별도 kcisa type)를 두 컬럼으로 보존:
--   activity_type : 원본 6종(kcisa 별도)                       → activity_by_dong 소비
--   type_bucket   : kcisa 를 service_name 으로 기존 4종에 병합 → location_daily 소비
-- 5개 코어 arm은 activity_type == type_bucket. quality_status(#111)는 location 의
-- dong_precise_count 용으로 실어 나른다(activity_by_dong 은 admin_dong 그레인이라 미사용).

with raw_activities as (
    select admin_dong_code, gu_code, gu, cast(performance_id as varchar) as activity_id,
           'performance' as activity_type, 'performance' as type_bucket, quality_status,
           event_start_date, event_end_date
    from {{ ref('silver_culture_performance') }}
    union all
    select admin_dong_code, gu_code, gu, event_key, 'event', 'event', quality_status, event_start_date, event_end_date
    from {{ ref('silver_culture_event') }}
    union all
    select admin_dong_code, gu_code, gu, cast(festival_id as varchar), 'festival', 'festival', quality_status, event_start_date, event_end_date
    from {{ ref('silver_culture_festival') }}
    union all
    select admin_dong_code, gu_code, gu, cast(exhibition_id as varchar), 'exhibition', 'exhibition', quality_status, event_start_date, event_end_date
    from {{ ref('silver_culture_exhibition') }}
    union all
    select admin_dong_code, gu_code, gu, cast(sejong_id as varchar), 'sejong', 'sejong', quality_status, event_start_date, event_end_date
    from {{ ref('silver_culture_sejong') }}
    union all
    -- kcisa(#85): activity_type='kcisa'(by_dong 별도 축) / type_bucket=service_name 병합(location 축)
    select admin_dong_code, gu_code, gu, 'kcisa:' || event_id, 'kcisa',
           case service_name
               when '전시' then 'exhibition'
               when '공연' then 'performance'
               when '행사/축제' then 'festival'
               else 'event'   -- 교육/체험 등
           end,
           quality_status,
           event_start_date, event_end_date
    from {{ ref('silver_culture_kcisa_event') }}
),

valid as (
    select * from raw_activities
    where {{ culture_valid_period() }}
)

select
    v.admin_dong_code, v.gu_code, v.gu,
    v.activity_id, v.activity_type, v.type_bucket, v.quality_status,
    d.activity_date
from valid v
cross join unnest(sequence(v.event_start_date, v.event_end_date, interval '1' day)) as d(activity_date)

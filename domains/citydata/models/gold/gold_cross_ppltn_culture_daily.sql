-- gold (크로스도메인 조인 예시, #94): 행정동 × 날짜별 **인구 혼잡도 × 진행 중 문화행사 수**.
--
-- 공통축 통일(admin_dong_code 행안부10 + KST)이 끝나 도메인 간 조인이 가능해진 첫 예시.
-- grain = (admin_dong_code, event_date).
--
--  * 인구(silver_seoul_ppltn, 장소·5분 grain) → admin_dong_code × 날짜로 **집계**
--    (여러 장소가 한 행정동에 매핑되므로 place 단위를 dong 단위로 올린다).
--  * 문화행사(culture.silver_culture_event) → 그 행정동에서 그 날짜에 **진행 중
--    (event_start_date <= 날짜 <= event_end_date)인 이벤트 수**를 range 조인으로 집계.
--
-- ⚠ 크로스도메인: culture 스키마에 의존한다. 그래서 tag=cross_domain 을 달고,
--    라이브 transform(5분 SLA)은 이 태그를 제외한다 — 소스 도메인 파이프라인이
--    타 도메인 테이블 상태에 결합되지 않도록. (별도 캐던스/수동 빌드)
-- ⚠ 커버리지: 인구는 서울 90개 행정동만 커버(주요 밀집지역). 그 범위에서만 조인된다.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='table',
    on_table_exists='drop',
    tags=['cross_domain'],
) }}

with ppltn_daily as (
    -- 인구: 장소·5분 → 행정동·날짜로 집계 (grain 을 dong 으로 올림)
    select
        admin_dong_code,
        min(gu_code) as gu_code,
        min(gu) as gu,
        cast(event_at as date) as event_date,
        count(distinct area_cd) as place_count,
        round(avg((area_ppltn_min + area_ppltn_max) / 2.0)) as avg_ppltn,
        max(area_ppltn_max) as max_ppltn,
        round(count_if(area_congest_lvl in ('붐빔', '약간 붐빔')) * 100.0 / count(*), 1)
            as busy_ratio_percent,
        count(*) as measurement_count
    from {{ ref('silver_seoul_ppltn') }}
    where admin_dong_code is not null
      and event_at is not null
    group by admin_dong_code, cast(event_at as date)
),

culture_active as (
    -- 인구 쪽 (dong, date) 를 spine 으로, 같은 행정동에서 그 날짜에 진행 중인 행사 수.
    select
        p.admin_dong_code,
        p.event_date,
        count(distinct c.event_key) as active_event_count,
        count(distinct c.category) as active_category_count
    from ppltn_daily p
    left join {{ source('culture', 'silver_culture_event') }} c
        on c.admin_dong_code = p.admin_dong_code
       and p.event_date between c.event_start_date and c.event_end_date
    group by p.admin_dong_code, p.event_date
)

select
    p.admin_dong_code,
    p.gu_code,
    p.gu,
    p.event_date,
    -- 인구 신호
    p.place_count,
    p.avg_ppltn,
    p.max_ppltn,
    p.busy_ratio_percent,
    p.measurement_count,
    -- 문화행사 신호
    coalesce(ca.active_event_count, 0) as active_event_count,
    coalesce(ca.active_category_count, 0) as active_category_count,
    (coalesce(ca.active_event_count, 0) > 0) as has_active_event
from ppltn_daily p
left join culture_active ca
    on p.admin_dong_code = ca.admin_dong_code
   and p.event_date = ca.event_date

-- gold: 인구혼잡 × 상권밀도 (크로스도메인). grain = admin_dong_code (동 단위 1행).
--
-- 우리 인구를 행정동 단위로 평균내고, 그 동의 상가 밀도(commerce 인허가 명부)를 붙인다.
-- 답: 상가 많은 동이 더 붐비나(상권 밀집 vs 혼잡 상관).
--
-- commerce.silver_license_current 는 전 서울 인허가 명부(현재)로 시계열이 아니라 '상태/맥락'
-- 이라 동별 밀도(개수)로 집계해 붙인다. 크로스도메인 source()(schema=commerce). 조인축
-- admin_dong_code(라이브 B). 커버리지=우리 핫플 동 한정. 90행짜리 가벼운 집계 + 5분 티어라
-- materialized=view (조회 시 계산·항상 최신·재생성 갭 없음). commerce 는 source 라 읽기만.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='view',
) }}

with ppltn_dong as (
    select
        admin_dong_code,
        max(gu_code) as gu_code,
        avg((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_avg,
        max((area_ppltn_min + area_ppltn_max) / 2.0) as ppltn_peak,
        count(distinct area_cd) as hotspot_count
    from {{ ref('silver_citydata_ppltn') }}
    where admin_dong_code is not null
    group by 1
),

-- 동별 상가 밀도. 영업상태(trdstatenm) '영업/정상'·'영업' 을 영업 중으로 본다.
commerce_dong as (
    select
        admin_dong_code,
        count(*) as license_total,
        count_if(trdstatenm in ('영업/정상', '영업')) as license_active,
        count_if(dataset in ('general_restaurant', 'rest_restaurant')
                 and trdstatenm in ('영업/정상', '영업')) as restaurant_active,
        count_if(dataset = 'beauty_shop' and trdstatenm in ('영업/정상', '영업')) as beauty_active
    from {{ source('commerce', 'silver_license_current') }}
    where admin_dong_code is not null
    group by 1
)

select
    p.admin_dong_code,
    m.admin_dong,
    p.gu_code,
    m.gu,
    p.hotspot_count,
    round(p.ppltn_avg, 1) as ppltn_avg,
    round(p.ppltn_peak, 1) as ppltn_peak,
    coalesce(c.license_total, 0) as license_total,
    coalesce(c.license_active, 0) as license_active,
    coalesce(c.restaurant_active, 0) as restaurant_active,
    coalesce(c.beauty_active, 0) as beauty_active
from ppltn_dong p
left join commerce_dong c on c.admin_dong_code = p.admin_dong_code
left join {{ ref('asac_axes', 'dim_admin_dong') }} m on p.admin_dong_code = m.admin_dong_code

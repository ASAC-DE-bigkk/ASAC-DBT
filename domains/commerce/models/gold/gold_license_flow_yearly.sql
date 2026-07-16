-- gold_license_flow_yearly — 연 단위 개업/폐업 흐름 × 업종 3단 × 지역 3축(시군구/행정동/법정동).
--
-- 인사이트 계약(#71·#73): "연 단위" 집계 — **이미 적재된 연도는 추가 적재하지 않는다** = 기적재
-- 최대연 초과 완결연만 append. **재실행 시 신규 완결연 없으면 0건**(사용자 확정 — 멱등 확인 대상).
-- D1 서빙은 롤업 전량 교체 스냅샷(서빙 정본 §1.4). 지연 도착(과거연 소급)은 --full-refresh 로 흡수(commerce_load_gold_refresh).

{{ config(
    materialized='incremental',
    incremental_strategy='append',
    on_schema_change='fail'
) }}

with e as (
    select t.major, t.category, e.dataset,
           coalesce(e.gu_code, 'UNK')         as gu_code,
           coalesce(e.admin_dong_code, 'UNK') as admin_dong_code,
           coalesce(e.legal_code, 'UNK')      as legal_code,
           case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.apvpermymd)
                when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{8}$')
                then substr(trim(e.apvpermymd),1,4)||'-'||substr(trim(e.apvpermymd),5,2)||'-'||substr(trim(e.apvpermymd),7,2)
           end as o_iso,
           case when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{4}-\d{2}-\d{2}$') then trim(e.dcbymd)
                when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{8}$')
                then substr(trim(e.dcbymd),1,4)||'-'||substr(trim(e.dcbymd),5,2)||'-'||substr(trim(e.dcbymd),7,2)
           end as c_iso
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
),

ev as (
    select 'opened' as event_type, substr(o_iso, 1, 4) as y,
           major, category, dataset, gu_code, admin_dong_code, legal_code
    from e where o_iso is not null
    union all
    select 'closed', substr(c_iso, 1, 4), major, category, dataset, gu_code, admin_dong_code, legal_code
    from e where c_iso is not null
)

select y, event_type, dataset, gu_code, admin_dong_code, legal_code,
       max(major) as major, max(category) as category,
       count(*)   as cnt
from ev
-- 완결연만(KST 당해 제외 — 당해분은 연이 닫힌 뒤 확정 적재)
where y < substr(cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar), 1, 4)
{% if is_incremental() %}
  -- append-only: 기적재 최대연 **초과** 완결연만(문자열 비교 — 신규 없으면 0건 → 재실행 멱등)
  and y > (select coalesce(max(y), '0000') from {{ this }})
{% endif %}
group by 1, 2, 3, 4, 5, 6

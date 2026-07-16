-- gold_license_flow_monthly — 월 단위 개업/폐업 흐름 × 업종 3단 × 지역 3축(시군구/행정동/법정동).
--
-- 인사이트 계약(#71·#73): "달 단위" 집계 — **이미 적재된 달은 다시 뽑지 않는다** = 기적재 최대월
-- 초과 완결월만 append. **재실행 시 신규 완결월 없으면 0건**(사용자 확정 — 멱등 확인 대상).
-- D1 export 도 동일(max(ym) 초과분만). 지연 도착(과거 달 소급 신고)은 --full-refresh 로 흡수
-- (완결월 append-only 의 트레이드오프 — 정기 full-refresh 스윕: commerce_load_gold_refresh).

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
    select 'opened' as event_type, substr(o_iso, 1, 7) as ym,
           major, category, dataset, gu_code, admin_dong_code, legal_code
    from e where o_iso is not null
    union all
    select 'closed', substr(c_iso, 1, 7), major, category, dataset, gu_code, admin_dong_code, legal_code
    from e where c_iso is not null
)

select ym, event_type, dataset, gu_code, admin_dong_code, legal_code,
       max(major) as major, max(category) as category,
       count(*)   as cnt
from ev
-- 완결월만(KST 당월 제외 — 당월분은 월이 닫힌 뒤 확정 적재)
where ym < substr(cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar), 1, 7)
{% if is_incremental() %}
  -- append-only: 기적재 최대월 **초과** 완결월만(문자열 비교 — 신규 없으면 0건 → 재실행 멱등)
  and ym > (select coalesce(max(ym), '0000-00') from {{ this }})
{% endif %}
group by 1, 2, 3, 4, 5, 6

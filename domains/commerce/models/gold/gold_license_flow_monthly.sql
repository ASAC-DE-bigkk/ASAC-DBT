-- gold_license_flow_monthly — 월 단위 개업/폐업 흐름 × 업종 3단 × 지역 3축(시군구/행정동/법정동).
--
-- 인사이트 계약(#71): "달 단위" 집계 — **이미 이전달까지 적재됐다면 그 이전은 다시 뽑지 않는다**
-- (완결월만 + 최근 3개월 지연보정 창 delete+insert). D1 export 는 D1 의 max(ym) 초과분만 append.
-- grain = unique_key 6컬럼 — 재실행 멱등(중복 불가).

{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['ym', 'event_type', 'dataset', 'gu_code', 'admin_dong_code', 'legal_code'],
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
  -- 지연 도착 보정 창: 기적재 최대월 - 3개월부터 재계산(delete+insert 교체 — 중복 불가)
  and ym >= substr(cast(
        coalesce(try(from_iso8601_date((select max(ym) from {{ this }}) || '-01')),
                 date '1900-01-01') - interval '3' month as varchar), 1, 7)
{% endif %}
group by 1, 2, 3, 4, 5, 6

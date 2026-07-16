-- gold_license_flow_daily — 일 단위 개업/폐업 흐름 × 업종 3단 × 지역 3축(시군구/행정동/법정동).
--
-- 인사이트 계약(#71, PROJECT.md §4.3): "업종별 하루 단위" 집계의 정본. 추이 분석은 이 테이블에
-- 기간 조건절(event_date between …)로 수행한다. D1 서빙은 **화면 축 롤업의 전량 교체 스냅샷**
-- (append 아님 — full-refresh 소급 반영 위해. 서빙 정본: docs/DB/gold/opus-serving-build-instructions.md §1.4).
--
-- 증분 계약(#73, 사용자 확정): **완결일만**(KST 오늘 제외) + **기적재 최대일 초과분만 append**
-- → 재실행 시 신규 완결일 없으면 **0건**(멱등 확인 대상). 지연 도착(과거일 소급 신고)은
-- --full-refresh 로 흡수(append-only 트레이드오프 — 정기 스윕: commerce_load_gold_refresh).
-- 날짜 규약: 문자열 ISO(사전순=날짜순, docs/DB/gold/status-aggregation-queries.md §1.2).

{{ config(
    materialized='incremental',
    incremental_strategy='append',
    on_schema_change='fail'
) }}

with e as (
    select t.major, t.category, e.dataset,
           t.name_ko,
           e.gu, e.admin_dong, e.legal_dong,
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
    select 'opened' as event_type, try(cast(o_iso as date)) as event_date,
           major, category, dataset, gu_code, admin_dong_code, legal_code,
           name_ko, gu, admin_dong, legal_dong
    from e where o_iso is not null
    union all
    select 'closed', try(cast(c_iso as date)), major, category, dataset, gu_code, admin_dong_code, legal_code,
           name_ko, gu, admin_dong, legal_dong
    from e where c_iso is not null
)

select event_date, event_type, {{ label_event_type_ko('event_type') }} as event_type_ko,
       dataset, max(name_ko) as dataset_ko,
       gu_code, max(gu) as gu,
       admin_dong_code, max(admin_dong) as admin_dong,
       legal_code, max(legal_dong) as legal_dong,
       max(major) as major, {{ label_major_ko('max(major)') }} as major_ko,
       max(category) as category, {{ label_category_ko('max(category)') }} as category_ko,
       count(*)   as cnt
from ev
-- 완결일만(KST 오늘 제외 — 당일분은 다음 실행이 확정 적재)
where event_date is not null
  and event_date < cast(current_timestamp at time zone 'Asia/Seoul' as date)
{% if is_incremental() %}
  -- append-only: 기적재 최대일 **초과** 완결일만(문자열 비교 — 신규 없으면 0건 → 재실행 멱등)
  and event_date > (select coalesce(max(event_date), date '0001-01-01') from {{ this }})
{% endif %}
group by event_date, event_type, dataset, gu_code, admin_dong_code, legal_code

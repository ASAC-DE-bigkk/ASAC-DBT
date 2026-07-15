-- gold_license_flow_daily — 일 단위 개업/폐업 흐름 × 업종 3단 × 지역 3축(시군구/행정동/법정동).
--
-- 인사이트 계약(#71, PROJECT.md §4.3): "업종별 하루 단위" 집계의 정본. 추이 분석은 이 테이블에
-- 기간 조건절(event_date between …)로 수행한다. D1 export 시에도 기간 grain 이라 **D1 의
-- max(event_date) 초과분만 append** 하면 중복 없이 증분 적재된다(§7 문서).
--
-- 증분 계약(중복 불가): **완결일만**(KST 오늘 제외) 적재. is_incremental 시 최근 90일 창을
-- delete+insert 로 재계산 — 폐업일(dcbymd)은 소급 신고가 흔해(지연 도착) 안정 기간을 다시
-- 열지 않으면 유실되기 때문. 90일보다 늦은 소급분은 --full-refresh 로 흡수(문서 명시).
-- grain = unique_key 6컬럼 — delete+insert 가 창 내 기존 행을 교체하므로 재실행 멱등.
-- 날짜 규약: 문자열 ISO(사전순=날짜순, docs/DB/gold/status-aggregation-queries.md §1.2).

{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['event_date', 'event_type', 'dataset', 'gu_code', 'admin_dong_code', 'legal_code'],
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
    select 'opened' as event_type, o_iso as event_date,
           major, category, dataset, gu_code, admin_dong_code, legal_code
    from e where o_iso is not null
    union all
    select 'closed', c_iso, major, category, dataset, gu_code, admin_dong_code, legal_code
    from e where c_iso is not null
)

select event_date, event_type, dataset, gu_code, admin_dong_code, legal_code,
       max(major) as major, max(category) as category,
       count(*)   as cnt
from ev
-- 완결일만(KST 오늘 제외 — 당일분은 다음 실행이 확정 적재)
where event_date < cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar)
{% if is_incremental() %}
  -- 지연 도착 보정 창: 기적재 최대일 - 90일부터 재계산(delete+insert 교체 — 중복 불가)
  -- 문자열 max(사전순=날짜순) 먼저, date 변환은 그 1개만 — 전 행 변환 시 원천 무효
  -- 날짜(예: 2006-02-29, ISO 형식이지만 실존하지 않는 날)에서 파싱 폭발(실측).
  and event_date >= cast(
        coalesce(try(from_iso8601_date((select max(event_date) from {{ this }}))),
                 date '1900-01-01') - interval '90' day as varchar)
{% endif %}
group by 1, 2, 3, 4, 5, 6

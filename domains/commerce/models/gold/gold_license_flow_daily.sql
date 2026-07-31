-- gold_license_flow_daily — 일 단위 개업/폐업 흐름 × 업종 3단 × 지역 3축(시군구/행정동/법정동).
--
-- 인사이트 계약(#71, PROJECT.md §4.3): "업종별 하루 단위" 집계의 정본. 추이 분석은 이 테이블에
-- 기간 조건절(event_date between …)로 수행한다. D1 서빙은 **화면 축 롤업의 전량 교체 스냅샷**
-- (append 아님 — full-refresh 소급 반영 위해. 서빙 정본: docs/DB/gold/opus-serving-build-instructions.md §1.4).
--
-- 증분 계약(#73 → #603 개정, 사용자 확정): **완결일만**(KST 오늘 제외) 적재하고, **갱신이 필요한
-- 날짜는 그 날짜만 다시 계산해 교체**한다. 대상 = ① 신규 완결일(기적재 최대일 초과) ② 직전 빌드
-- 이후 유입·변경된 행이 건드린 날짜(과거일 소급 신고 — 실측 하루 694개 날짜/21,152개 중 3.3%).
-- append-only 였을 때는 이 소급분이 영원히 반영되지 않았고, 흡수 경로라던
-- `commerce_load_gold_refresh` 는 `schedule=None` 이라 실재하지 않았다.
-- 워터마크 `src_collected_at` = 이 빌드가 반영한 silver `max(collected_at)`. 컬럼이 NULL 인 최초
-- 1회는 전 구간 재계산 = 누적 소급 부채 정산.
-- 날짜 규약: 문자열 ISO(사전순=날짜순, docs/DB/gold/status-aggregation-queries.md §1.2).

-- 정렬 스펙(#264): event_date(원천 사건일 = 인허가/폐업일 파생) — iceberg_api 범위질의 정본이라
-- 파일 min/max 를 기간축으로 조인다(실측 before: 2024년 범위질의가 전체 2,918,693행 스캔·프루닝 0%).
{{ config(
    materialized='incremental',
    unique_key='event_date',
    incremental_strategy='delete+insert',
    on_schema_change='append_new_columns',
    properties={
        "sorted_by": "ARRAY['event_date']",
    },
) }}

{#- 워터마크 컬럼은 이 변경으로 신설된다. 기존 테이블엔 아직 없으므로, 있는지 실측해
   없으면 epoch 로 떨어뜨린다 → 최초 1회 전 구간 재계산(누적 소급 정산) 후 자동 델타 전환.
   (이 가드가 없으면 첫 증분 run 이 '컬럼 없음'으로 실패해 수동 --full-refresh 가 필요하다.) -#}
{%- set wm_ready = is_incremental() and 'src_collected_at' in
     (adapter.get_columns_in_relation(this) | map(attribute='name') | list) -%}

with e as (
    select t.major, t.category, e.dataset, e.collected_at,
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
),

-- 이 빌드가 반영하는 silver 워터마크(집계 행에 상수로 실어 다음 빌드가 읽는다).
src as (select max(collected_at) as v from e)

{% if is_incremental() %}
-- 직전 빌드가 반영한 워터마크. 컬럼 신설 직전이면 epoch → 전 구간 재계산 = 누적 소급 정산.
, wm as (
{%- if wm_ready %}
    select coalesce(max(src_collected_at), timestamp '1970-01-01 00:00:00.000') as w from {{ this }}
{%- else %}
    select timestamp '1970-01-01 00:00:00.000' as w
{%- endif %}
)

-- 워터마크 이후 유입·변경된 행이 건드리는 **날짜**(과거일 포함) = 재계산 대상.
, changed as (
    select distinct try(cast(o_iso as date)) as event_date
      from e cross join wm where o_iso is not null and e.collected_at > wm.w
    union
    select distinct try(cast(c_iso as date)) as event_date
      from e cross join wm where c_iso is not null and e.collected_at > wm.w
)
{% endif %}

select event_date, event_type, {{ label_event_type_ko('event_type') }} as event_type_ko,
       dataset, max(name_ko) as dataset_ko,
       gu_code, max(gu) as gu,
       admin_dong_code, max(admin_dong) as admin_dong,
       legal_code, max(legal_dong) as legal_dong,
       max(major) as major, {{ label_major_ko('max(major)') }} as major_ko,
       max(category) as category, {{ label_category_ko('max(category)') }} as category_ko,
       count(*)   as cnt,
       (select v from src) as src_collected_at
from ev
-- 완결일만(KST 오늘 제외 — 당일분은 다음 실행이 확정 적재)
where event_date is not null
  and event_date < cast(current_timestamp at time zone 'Asia/Seoul' as date)
{% if is_incremental() %}
  and (
    -- ① 신규 완결일 — 이 날짜의 행은 워터마크 이전에 수집됐을 수 있어 ②로는 못 잡는다
    event_date > (select coalesce(max(event_date), date '0001-01-01') from {{ this }})
    -- ② 소급 변경일 — 기적재분을 unique_key='event_date' 단위로 교체
    or event_date in (select event_date from changed)
  )
{% endif %}
group by event_date, event_type, dataset, gu_code, admin_dong_code, legal_code

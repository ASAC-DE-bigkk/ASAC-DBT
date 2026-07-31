-- gold_license_flow_monthly — 월 단위 개업/폐업 흐름 × 업종 3단 × 지역 3축(시군구/행정동/법정동).
--
-- 인사이트 계약(#71·#73): "달 단위" 집계 — **완결월만 적재한다**(당월 제외). 여기에 더해
-- **갱신이 필요한 달은 그 달만 다시 계산해 교체한다**(#603, 사용자 확정).
--
-- 왜 append 를 버렸나: 인허가는 과거일로 소급 신고된다. 실측(2026-07-30) 하루 수집분이 완결 과거
-- 구간 **235개 월**(1975-01~2026-06)을 건드렸다. append-only 는 기적재 달을 절대 다시 쓰지 않으므로
-- 이 소급분이 영원히 반영되지 않았고(게시본 181,435행 중 72행이 진값과 불일치, 합계 4,616,291 vs
-- 4,616,354), 흡수 경로라던 `commerce_load_gold_refresh` 는 `schedule=None` 이라 실재하지 않았다.
--
-- 증분 계약: ① 신규 완결월(기적재 최대월 초과) ② 직전 빌드 이후 유입·변경된 행이 건드린 달
-- → 두 집합만 `delete+insert` 로 교체(silver_license_current/entity 와 동일한 사내 관용구).
-- 워터마크 `src_collected_at` = 이 빌드가 반영한 silver `max(collected_at)`. 컬럼이 NULL 인 최초
-- 1회는 전 구간이 변경 대상이 되어 **누적 소급 부채가 한 번에 정산**된다(그 뒤부터 델타).
-- D1 서빙은 롤업 전량 교체 스냅샷(서빙 정본 §1.4).

-- 정렬 스펙(#264): ym(원천 사건월, ISO 문자열 = 사전순 정렬) — /monthly/detail 폴백 범위질의의 파일 프루닝.
{{ config(
    materialized='incremental',
    unique_key='ym',
    incremental_strategy='delete+insert',
    on_schema_change='append_new_columns',
    properties={
        "sorted_by": "ARRAY['ym']",
    },
) }}

{#- 워터마크 컬럼은 이 변경으로 신설된다. 기존 테이블엔 아직 없으므로, 있는지 실측해
   없으면 epoch 로 떨어뜨린다 → 최초 1회 전 구간 재계산(누적 소급 정산) 후 자동 델타 전환.
   (이 가드가 없으면 첫 증분 run 이 '컬럼 없음'으로 실패해 수동 --full-refresh 가 필요하다.) -#}
{%- set wm_ready = is_incremental() and 'src_collected_at' in
     (adapter.get_columns_in_relation(this) | map(attribute='name') | list) -%}

with e as (
    select t.major, t.category, e.dataset, e.collected_at,
           t.name_ko, e.gu, e.admin_dong, e.legal_dong,
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
           major, category, dataset, gu_code, admin_dong_code, legal_code,
           name_ko, gu, admin_dong, legal_dong
    from e where o_iso is not null
    union all
    select 'closed', substr(c_iso, 1, 7), major, category, dataset, gu_code, admin_dong_code, legal_code,
           name_ko, gu, admin_dong, legal_dong
    from e where c_iso is not null
),

-- 이 빌드가 반영하는 silver 워터마크(집계 행에 상수로 실어 다음 빌드가 읽는다).
-- taxonomy 조인 이후 기준이라, 조인에서 떨어진 행은 워터마크를 전진시키지 않는다(보수적).
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

-- 워터마크 이후 유입·변경된 행이 건드리는 **달**(과거 달 포함) = 재계산 대상.
, changed as (
    select distinct substr(o_iso, 1, 7) as ym
      from e cross join wm where o_iso is not null and e.collected_at > wm.w
    union
    select distinct substr(c_iso, 1, 7) as ym
      from e cross join wm where c_iso is not null and e.collected_at > wm.w
)
{% endif %}

select ym, cast(substr(ym, 1, 4) as integer) as y,
       event_type, {{ label_event_type_ko('event_type') }} as event_type_ko,
       dataset, max(name_ko) as dataset_ko,
       gu_code, max(gu) as gu,
       admin_dong_code, max(admin_dong) as admin_dong,
       legal_code, max(legal_dong) as legal_dong,
       max(major) as major, {{ label_major_ko('max(major)') }} as major_ko,
       max(category) as category, {{ label_category_ko('max(category)') }} as category_ko,
       count(*)   as cnt,
       (select v from src) as src_collected_at
from ev
-- 완결월만(KST 당월 제외 — 당월분은 월이 닫힌 뒤 확정 적재)
where ym < substr(cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar), 1, 7)
{% if is_incremental() %}
  and (
    -- ① 신규 완결월(기적재 최대월 초과) — 이 달의 행은 워터마크 이전에 수집됐을 수 있어 ②로는 못 잡는다
    ym > (select coalesce(max(ym), '0000-00') from {{ this }})
    -- ② 소급 변경월 — 기적재분을 unique_key='ym' 단위로 교체(둘 다 없으면 0건 → 재실행 멱등)
    or ym in (select ym from changed)
  )
{% endif %}
group by ym, event_type, dataset, gu_code, admin_dong_code, legal_code

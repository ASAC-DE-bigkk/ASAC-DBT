-- gold_transit_parking_lot_15min — 주차장 개소×15분 점유 아카이브 (#286).
--
-- 한 행 = (parking_id, bucket_at) 한 조합의 점유 관측 집계.
--   grain: (parking_id, bucket_at). bucket_at = 15분 버킷(KST 벽시계, 수집 5분 주기라
--   버킷당 ~3관측). 개소 단위 영구 아카이브 — 만차 리스크(G2)의 점유 변화율·요일×시간
--   만차 확률 프로파일이 전부 여기서 파생된다. 동 단위 집계는 gold_transit_dong_15min.
--
-- ── 점유율 컬럼 설계 ────────────────────────────────────────────────────
--   occ_ratio = now_prk_vhcl_cnt/total_capacity (둘 다 유효 & 총면수>0 만, 그 외 null).
--   버킷 내 avg/min/max 에 더해 occ_last(최신 관측값, max_by)를 남긴다 — G2 의
--   변화율(연속 버킷 lag)이 '버킷 평균 차'가 아니라 '실제 최신값 차'로 계산되도록.
--   capacity_last 는 최신 총면수(운영상 증감 가능) — 점유대수 복원용(occ_last×capacity).
--
-- ── 공간축 ─────────────────────────────────────────────────────────────
--   admin_dong_code/gu_code 는 개소 상수(dim 조인 결과)라 최신 관측값을 스탬프.
--   dim 좌표 갱신 시 새 버킷부터 새 값 — 과거 버킷 소급 없음(아카이브 불변).
--
-- ── 증분(incremental merge) + full-refresh 가드 ─────────────────────────
--   unique_key=(parking_id, bucket_at), 임계 max(bucket_at)-3h (#67 근거 공유).
--   full_refresh=false 고정: 원본 주 경계 삭제(ASAC-DAG #369) 구조에서
--   재빌드 = 지난주 이전 아카이브 영구 소실(#286 원칙 1).

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['parking_id', 'bucket_at'],
    full_refresh=false,
) }}

{%- set incr_filter %}
{% if is_incremental() %}
and event_at >= (
    select coalesce(max(bucket_at), timestamp '1970-01-01') - interval '3' hour
    from {{ this }}
)
{% endif %}
{%- endset %}

with src as (
    select
        parking_id,
        event_at,
        admin_dong_code,
        gu_code,
        now_prk_vhcl_cnt,
        total_capacity,
        case
            when now_prk_vhcl_cnt is not null
             and total_capacity is not null
             and total_capacity > 0
            then cast(now_prk_vhcl_cnt as double) / total_capacity
        end as occ_ratio
    from {{ ref('silver_transit_parking') }}
    where parking_id is not null
      {{ incr_filter }}
)

select
    parking_id,
    {{ transit_time_bucket('event_at', 15) }} as bucket_at,
    max_by(admin_dong_code, event_at) as admin_dong_code,
    max_by(gu_code, event_at) as gu_code,
    count(*) as obs_cnt,
    avg(occ_ratio) as occ_avg,
    min(occ_ratio) as occ_min,
    max(occ_ratio) as occ_max,
    -- 최신 관측(occ_ratio null 관측이 최신일 수 있어 null 가능 — 값 유무는 소비 측 판단).
    max_by(occ_ratio, event_at) as occ_last,
    max_by(total_capacity, event_at) as capacity_last,
    max(event_at) as last_event_at
from src
group by parking_id, {{ transit_time_bucket('event_at', 15) }}

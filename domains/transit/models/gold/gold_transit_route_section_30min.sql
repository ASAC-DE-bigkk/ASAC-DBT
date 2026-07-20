-- gold_transit_route_section_30min — 노선×구간×30분 버스 아카이브 (#286).
--
-- 한 행 = (bus_route_id, sect_ord, bucket_at) 한 조합의 버스 관측 집계.
--   grain: (bus_route_id, sect_ord, bucket_at). bucket_at = 30분 버킷(KST 벽시계).
--   버스 축의 영구 아카이브 — 원본 주 경계 삭제(ASAC-DAG #369) 후에도 노선·구간 단위
--   프로파일(G3 "몇 시에 타면 앉아 가나")을 재계산할 수 있는 유일한 원천이 된다.
--
-- ── 왜 30분 grain 인가 (#440) ───────────────────────────────────────────
--   버스 티어링 후 수집이 30분 주기(tier1 매 런, tier2 는 07·13·19시 런만)라
--   30분 버킷 = 런 1회 스냅샷. 더 촘촘한 버킷은 빈 칸만 늘린다.
--   3분 수집 복귀(#369 잔여) 시에도 이 grain 은 유지 가능(버킷당 관측이 늘 뿐).
--
-- ── tier 스탬프(원칙 ①) ────────────────────────────────────────────────
--   전 티어를 저장하고 dim_transit_bus_route_tier 조인으로 tier 를 행에 스탬프한다.
--   필터는 파생 단계 몫: 시간대 비교(G3 프로파일)는 tier=1 만 소비(원칙 ②).
--   merge 특성상 tier 는 '그 버킷이 마지막으로 재집계된 시점'의 분류로 남는다 —
--   과거 버킷의 tier 재분류는 하지 않는다(당시 수집 정책의 기록으로서 의미가 있음).
--
-- ── sect_ord null 제외 ─────────────────────────────────────────────────
--   구간 그레인 축이라 sect_ord 미상 행은 제외(캐스트 실패·원천 결측 소수).
--   동 단위 소비는 gold_transit_dong_15min 이 담당하므로 손실 아님.
--
-- ── 증분(incremental merge) + full-refresh 가드 ─────────────────────────
--   unique_key=(bus_route_id, sect_ord, bucket_at), 임계 max(bucket_at)-3h
--   (silver -2h lookback + 버킷 경계 여유 — #67 근거 공유). full_refresh=false 고정:
--   원본이 주 단위로 사라지므로 재빌드 = 아카이브 영구 소실(#286 원칙 1).

-- ── Iceberg 일 파티셔닝 ────────────────────────────────────────────────
--   MERGE 가 대상 전체 데이터파일을 훑지 않고 최근 파티션만 건드리게 하고, 하위
--   소비(24h 창·프런티어 산출·시간 롤업)의 시간 술어가 프루닝된다. 테이블이 비어
--   있는 지금 넣지 않으면 full_refresh=false 라 나중엔 CTAS 백업→재적재 수동
--   절차를 거쳐야 바꿀 수 있다.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['bus_route_id', 'sect_ord', 'bucket_at'],
    full_refresh=false,
    properties={'partitioning': "ARRAY['day(bucket_at)']"},
) }}

{%- set incr_filter %}
-- 아카이브 개시일 하한(dong_15min 과 같은 근거 — dbt_project.yml var 주석).
and event_at >= timestamp '{{ var("transit_archive_start_at") }}'
{% if is_incremental() %}
and event_at >= (
    select coalesce(max(bucket_at), timestamp '1970-01-01') - interval '3' hour
    from {{ this }}
)
{% endif %}
{%- endset %}

with src as (
    select
        b.bus_route_id,
        b.sect_ord,
        b.event_at,
        b.veh_id,
        b.congestion,
        b.is_full,
        b.stop_flag,
        t.tier
    from {{ ref('silver_transit_bus_position') }} b
    left join {{ ref('dim_transit_bus_route_tier') }} t
        on b.bus_route_id = t.bus_route_id
    where b.sect_ord is not null
      {{ incr_filter }}
)

select
    bus_route_id,
    sect_ord,
    {{ transit_time_bucket('event_at', 30) }} as bucket_at,
    -- 빌드 시점 분류 스탬프(노선 단위 상수라 min=값 그대로, 그룹 함수는 문법 요구).
    min(tier) as tier,
    count(*) as obs_cnt,
    count(distinct veh_id) as veh_cnt,
    -- congestion=0 은 '정보없음'이라 평균 제외(#67 과 동일).
    {{ transit_bus_congestion_avg() }} as congestion_avg,
    avg(cast(is_full as double)) as full_ratio,
    avg(cast(stop_flag as double)) as stop_ratio,
    max(event_at) as last_event_at
from src
group by bus_route_id, sect_ord, {{ transit_time_bucket('event_at', 30) }}

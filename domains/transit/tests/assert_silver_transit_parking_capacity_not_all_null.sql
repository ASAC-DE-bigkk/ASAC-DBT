-- #72 회귀 방지: silver_transit_parking 의 now_prk_vhcl_cnt / total_capacity 가
--   '전건 null' 로 조용히 회귀하지 않는지 감시하는 하한 계약 테스트.
--
-- 배경(실측): 원천 NOW_PRK_VHCL_CNT·TPKCT 가 정수를 소수 문자열로 내보내(예 "806.0"),
--   try(cast(... as integer)) 가 전건 실패 → 두 컬럼이 조용히 전건 null 이 됐다(slv 46,107행).
--   double 경유 캐스트(transit_int_from_numeric_str)로 고쳤고, 원천 표기 변화나 캐스트
--   퇴행으로 다시 대량 null 이 되면 이 테스트가 잡는다. not_null 이 아니라 '비율 하한'인
--   이유: 원천이 향후 일부 개소에서 비수치/공란을 낼 수 있어(현재는 전 개소 제공) 개별 null 은
--   정상 범위로 허용하되, '전건/대량 null' 이라는 급성 회귀만 실패시키기 위함.
--
-- 윈도: ingested_at 기준 최근 var transit_freshness_monitor_hours(기본 24h).
--   freshness 감시 테스트와 같은 윈도 var 를 재사용(리터럴 중복 금지). 매 빌드 재계산량이
--   상수화되고, 오래된 대량 정상분이 급성 회귀를 임계 아래로 희석하는 것도 막는다.
--
-- 임계 0.5: 실측상 원천은 두 필드를 전 개소에 제공하고("미연계중" 개소도 "0.0" 으로 채움)
--   double 경유로 전건 파싱되어 현재 non-null 비율은 ≈1.0 이다. 0.5 는 그 절반 —
--   개별 개소 몇 곳이 향후 비수치/공란을 내보내도 통과하되, 대량 파싱 붕괴(전건 null 회귀)는
--   반드시 실패하도록 여유를 둔 하한. 윈도에 행이 없으면(수집 공백) nullif 로 비율이 null 이 되어
--   미검출된다 — 신선도(행 유무)는 이 테스트 소관이 아니고 별도 감시 대상이므로 의도적.

with recent as (
    select now_prk_vhcl_cnt, total_capacity
    from {{ ref('silver_transit_parking') }}
    where ingested_at >= cast(at_timezone(current_timestamp, 'UTC') as timestamp(6))
                         - interval '{{ var("transit_freshness_monitor_hours") }}' hour
),

ratios as (
    select
        count_if(now_prk_vhcl_cnt is not null) * 1.0 / nullif(count(*), 0) as now_ratio,
        count_if(total_capacity is not null) * 1.0 / nullif(count(*), 0) as cap_ratio
    from recent
)

select 'now_prk_vhcl_cnt' as column_name, now_ratio as non_null_ratio
from ratios
where now_ratio < 0.5
union all
select 'total_capacity' as column_name, cap_ratio as non_null_ratio
from ratios
where cap_ratio < 0.5

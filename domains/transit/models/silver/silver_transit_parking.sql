-- silver_transit_parking — 주차장 실시간 스냅샷 정제.
--
-- grain: (parking_id=PKLT_CD, event_at=NOW_PRK_VHCL_UPDT_TM KST). 시간당 수집 가정,
--   incremental(merge): 이미 반영된 ingested_at 이후(-2h lookback)만 스캔·중복은 merge 로 갱신.
-- 시간축: event_at = 도메인 대표시각(주차 현황 갱신시각, KST).
-- 공간축: dim_transit_parking 조인(pklt_cd)으로 latitude/longitude/admin_dong_code/gu_code 부착.
-- 신선도(#66): event_at(KST 벽시계)이 수집시각보다 미래인 행을 차단 —
--   event_at <= utc_to_kst(ingested_at)+스큐 상한 필터(transit_event_at_not_future,
--   임계는 var transit_freshness_skew_minutes). 주 quirk 원천은 subway_arrival 이나
--   3종 공통 계약으로 방어 적용(gold #67 시간대 집계 오염 차단). 하한은 없음(과거 수신 정상).

-- sorted_by(#482): 근거는 silver_transit_subway_arrival 동일 주석 참조.
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['parking_id', 'event_at'],
    properties={'sorted_by': "ARRAY['event_at']"},
) }}

with bronze as (
    select
        trim(json_extract_scalar(raw, '$.PKLT_CD')) as parking_id,
        trim(json_extract_scalar(raw, '$.PKLT_NM')) as parking_name,
        -- event_at 도출식은 매크로 공유(#66): 감시 warn 테스트가 같은 식으로 bronze 를 재도록.
        {{ transit_parking_event_at('raw') }} as event_at,
        -- 원천이 소수 문자열("806.0")이라 integer 직접 캐스트는 전건 실패(#72) —
        -- double 경유 매크로로 소수·정수 문자열 모두 수용(dim_transit_parking 과 공유).
        {{ transit_int_from_numeric_str("json_extract_scalar(raw, '$.NOW_PRK_VHCL_CNT')") }} as now_prk_vhcl_cnt,
        {{ transit_int_from_numeric_str("json_extract_scalar(raw, '$.TPKCT')") }} as total_capacity,
        trim(json_extract_scalar(raw, '$.PRK_STTS_NM')) as prk_stts_nm,
        cast(ts_source as varchar) as ts_source,
        cast(dag_run_id as varchar) as dag_run_id,
        ingested_at
    from {{ source('transit_bronze', 'parking') }}
    {% if is_incremental() %}
    where ingested_at >= (
        select coalesce(max(ingested_at), timestamp '1970-01-01') - interval '2' hour
        from {{ this }}
    )
    {% endif %}
),

ranked as (
    select
        *,
        row_number() over (
            partition by parking_id, event_at
            order by ingested_at desc
        ) as row_num
    from bronze
    where parking_id is not null
      and event_at is not null
      -- 신선도 상한(#66): 미래 event_at 차단. dedup 전에 적용.
      and {{ transit_event_at_not_future('event_at', 'ingested_at') }}
)

select
    b.parking_id,
    b.parking_name,
    b.event_at,
    b.now_prk_vhcl_cnt,
    b.total_capacity,
    b.prk_stts_nm,
    d.latitude,
    d.longitude,
    d.admin_dong_code,
    d.gu_code,
    b.ts_source,
    b.dag_run_id,
    b.ingested_at
from ranked b
left join {{ ref('dim_transit_parking') }} d
    on b.parking_id = d.parking_id
where b.row_num = 1

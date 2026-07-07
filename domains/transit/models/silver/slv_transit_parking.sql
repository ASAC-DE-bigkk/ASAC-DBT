-- slv_transit_parking — 주차장 실시간 스냅샷 정제.
--
-- grain: (parking_id=PKLT_CD, event_at=NOW_PRK_VHCL_UPDT_TM KST). 시간당 수집 가정,
--   incremental(merge): 이미 반영된 ingested_at 이후(-2h lookback)만 스캔·중복은 merge 로 갱신.
-- 시간축: event_at = 도메인 대표시각(주차 현황 갱신시각, KST).
-- 공간축: dim_transit_parking 조인(pklt_cd)으로 latitude/longitude/admin_dong_code/gu_code 부착.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['parking_id', 'event_at'],
) }}

with bronze as (
    select
        trim(json_extract_scalar(raw, '$.PKLT_CD')) as parking_id,
        trim(json_extract_scalar(raw, '$.PKLT_NM')) as parking_name,
        {{ asac_axes.kst_at("json_extract_scalar(raw, '$.NOW_PRK_VHCL_UPDT_TM')") }} as event_at,
        try(cast(json_extract_scalar(raw, '$.NOW_PRK_VHCL_CNT') as integer)) as now_prk_vhcl_cnt,
        try(cast(json_extract_scalar(raw, '$.TPKCT') as integer)) as total_capacity,
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

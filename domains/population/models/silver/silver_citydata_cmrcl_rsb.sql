-- silver: citydata 상권 업종별 상세 (#69). grain = (area_cd, event_at, 업종 대·중분류).
--
-- LIVE_CMRCL_STTS 블록 안의 CMRCL_RSB 배열(업종 1개 = 원소 1개)을 UNNEST 로 펼친다.
-- event_at 은 부모 블록의 CMRCL_TIME. merge 키에 업종 축이 들어가 배치 내 dedup 후 멱등.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['area_cd', 'event_at', 'rsb_lrg_ctgr', 'rsb_mid_ctgr'],
    on_table_exists='drop',
) }}

with src as (
    select
        area_cd,
        payload,
        {{ asac_axes.utc_to_kst('collected_at') }} as collected_at
    from {{ source('bronze', 'bronze_seoul_citydata') }}
    where block_name = 'LIVE_CMRCL_STTS'
    {% if is_incremental() %}
      and {{ asac_axes.utc_to_kst('collected_at') }} >= (
          select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
          from {{ this }}
      )
    {% endif %}
),

exploded as (
    select
        s.area_cd,
        {{ asac_axes.kst_at_from_parts(
            "substr(json_extract_scalar(s.payload, '$.CMRCL_TIME'), 1, 8)",
            "substr(json_extract_scalar(s.payload, '$.CMRCL_TIME'), 10, 4)") }} as event_at,
        json_extract_scalar(rsb, '$.RSB_LRG_CTGR') as rsb_lrg_ctgr,
        json_extract_scalar(rsb, '$.RSB_MID_CTGR') as rsb_mid_ctgr,
        json_extract_scalar(rsb, '$.RSB_PAYMENT_LVL') as payment_lvl,
        try_cast(json_extract_scalar(rsb, '$.RSB_SH_PAYMENT_CNT') as integer) as payment_count,
        try_cast(json_extract_scalar(rsb, '$.RSB_SH_PAYMENT_AMT_MIN') as bigint) as payment_amt_min,
        try_cast(json_extract_scalar(rsb, '$.RSB_SH_PAYMENT_AMT_MAX') as bigint) as payment_amt_max,
        try_cast(json_extract_scalar(rsb, '$.RSB_MCT_CNT') as integer) as merchant_count,
        json_extract_scalar(rsb, '$.RSB_MCT_TIME') as merchant_count_month,
        s.collected_at
    from src s
    cross join unnest(cast(json_extract(s.payload, '$.CMRCL_RSB') as array(json))) as t (rsb)
),

deduped as (
    select *
    from (
        select *, row_number() over (
            partition by area_cd, event_at, rsb_lrg_ctgr, rsb_mid_ctgr
            order by collected_at desc) as rn
        from exploded
        where area_cd is not null and event_at is not null
            and rsb_lrg_ctgr is not null and rsb_mid_ctgr is not null
    )
    where rn = 1
)

select
    d.area_cd,
    a.area_nm,
    a.gu,
    a.admin_dong,
    a.gu_code,
    a.admin_dong_code,
    d.event_at,
    d.rsb_lrg_ctgr,
    d.rsb_mid_ctgr,
    d.payment_lvl,
    d.payment_count,
    d.payment_amt_min,
    d.payment_amt_max,
    d.merchant_count,
    d.merchant_count_month,
    d.collected_at
from deduped d
left join {{ ref('dim_seoul_area') }} a on d.area_cd = a.area_cd

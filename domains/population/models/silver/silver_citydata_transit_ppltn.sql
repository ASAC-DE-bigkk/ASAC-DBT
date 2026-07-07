-- silver: citydata 지하철/버스 승하차 인원 (#69). grain = (area_cd, mode, observed_at).
--
-- LIVE_SUB_PPLTN / LIVE_BUS_PPLTN 두 블록은 grain 이 같아(장소×시각 1행) mode 컬럼으로
-- 한 테이블에 담는다. 원천에 자체 갱신시각 필드가 없어(실측: 값이 ~5분마다 교체)
-- 관측시각 observed_at = collected_at(KST) 을 시간축으로 쓴다.
-- 값 의미: 최근 5/10/30분 창의 승·하차 인원 min~max + 당일 누적(acml).

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['area_cd', 'mode', 'observed_at'],
    on_table_exists='drop',
) }}

{% set modes = [('LIVE_SUB_PPLTN', 'subway', 'SUB'), ('LIVE_BUS_PPLTN', 'bus', 'BUS')] %}

with src as (
    {% for block, mode, p in modes %}
    select
        area_cd,
        '{{ mode }}' as mode,
        {{ asac_axes.utc_to_kst('collected_at') }} as observed_at,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_5WTHN_GTON_PPLTN_MIN') as integer) as gton_5min_min,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_5WTHN_GTON_PPLTN_MAX') as integer) as gton_5min_max,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_5WTHN_GTOFF_PPLTN_MIN') as integer) as gtoff_5min_min,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_5WTHN_GTOFF_PPLTN_MAX') as integer) as gtoff_5min_max,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_10WTHN_GTON_PPLTN_MIN') as integer) as gton_10min_min,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_10WTHN_GTON_PPLTN_MAX') as integer) as gton_10min_max,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_10WTHN_GTOFF_PPLTN_MIN') as integer) as gtoff_10min_min,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_10WTHN_GTOFF_PPLTN_MAX') as integer) as gtoff_10min_max,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_30WTHN_GTON_PPLTN_MIN') as integer) as gton_30min_min,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_30WTHN_GTON_PPLTN_MAX') as integer) as gton_30min_max,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_30WTHN_GTOFF_PPLTN_MIN') as integer) as gtoff_30min_min,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_30WTHN_GTOFF_PPLTN_MAX') as integer) as gtoff_30min_max,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_ACML_GTON_PPLTN_MIN') as bigint) as gton_acml_min,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_ACML_GTON_PPLTN_MAX') as bigint) as gton_acml_max,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_ACML_GTOFF_PPLTN_MIN') as bigint) as gtoff_acml_min,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_ACML_GTOFF_PPLTN_MAX') as bigint) as gtoff_acml_max,
        try_cast(json_extract_scalar(payload, '$.{{ p }}_STN_CNT') as integer) as station_count
    from {{ source('bronze', 'bronze_seoul_citydata') }}
    where block_name = '{{ block }}'
    {% if is_incremental() %}
      and {{ asac_axes.utc_to_kst('collected_at') }} >= (
          select coalesce(max(observed_at), timestamp '1970-01-01') - interval '30' minute
          from {{ this }}
      )
    {% endif %}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

deduped as (
    select *
    from (
        select *, row_number() over (
            partition by area_cd, mode, observed_at order by observed_at desc) as rn
        from src
        where area_cd is not null
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
    d.mode,
    d.observed_at,
    d.gton_5min_min, d.gton_5min_max, d.gtoff_5min_min, d.gtoff_5min_max,
    d.gton_10min_min, d.gton_10min_max, d.gtoff_10min_min, d.gtoff_10min_max,
    d.gton_30min_min, d.gton_30min_max, d.gtoff_30min_min, d.gtoff_30min_max,
    d.gton_acml_min, d.gton_acml_max, d.gtoff_acml_min, d.gtoff_acml_max,
    d.station_count
from deduped d
left join {{ ref('dim_seoul_area') }} a on d.area_cd = a.area_cd

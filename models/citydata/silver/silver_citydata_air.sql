-- silver: citydata 날씨 실황 + 대기질 (#69). grain = (area_cd, event_at).
--
-- WEATHER_STTS 블록(원소 1개 배열)에서 **실황**(기온·강수·PM2.5/PM10·통합대기지수)만
-- 파싱한다. FCST24HOURS(예보)는 weather 도메인(KMA)이 canonical 이라 제외(#192 원칙).
-- event_at = WEATHER_TIME("yyyy-MM-dd HH:mm", 실측 10분 주기) 파싱.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['area_cd', 'event_at'],
    on_table_exists='drop',
) }}

with src as (
    select
        area_cd,
        payload,
        {{ asac_axes.utc_to_kst('collected_at') }} as collected_at
    from {{ source('bronze_citydata', 'bronze_seoul_citydata') }}
    where block_name = 'WEATHER_STTS'
    {% if is_incremental() %}
      and {{ asac_axes.utc_to_kst('collected_at') }} >= (
          select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
          from {{ this }}
      )
    {% endif %}
),

parsed as (
    select
        area_cd,
        {{ asac_axes.kst_at("json_extract_scalar(payload, '$[0].WEATHER_TIME')") }} as event_at,
        try_cast(json_extract_scalar(payload, '$[0].TEMP') as decimal(4, 1)) as temperature,
        try_cast(json_extract_scalar(payload, '$[0].SENSIBLE_TEMP') as decimal(4, 1)) as sensible_temperature,
        try_cast(json_extract_scalar(payload, '$[0].HUMIDITY') as integer) as humidity,
        json_extract_scalar(payload, '$[0].PRECIPITATION') as precipitation,
        json_extract_scalar(payload, '$[0].PRECPT_TYPE') as precipitation_type,
        try_cast(json_extract_scalar(payload, '$[0].PM25') as integer) as pm25,
        json_extract_scalar(payload, '$[0].PM25_INDEX') as pm25_index,
        try_cast(json_extract_scalar(payload, '$[0].PM10') as integer) as pm10,
        json_extract_scalar(payload, '$[0].PM10_INDEX') as pm10_index,
        json_extract_scalar(payload, '$[0].AIR_IDX') as air_idx,
        try_cast(json_extract_scalar(payload, '$[0].AIR_IDX_MVL') as decimal(6, 1)) as air_idx_value,
        json_extract_scalar(payload, '$[0].UV_INDEX_LVL') as uv_index_lvl,
        collected_at
    from src
),

deduped as (
    select *
    from (
        select *, row_number() over (
            partition by area_cd, event_at order by collected_at desc) as rn
        from parsed
        where area_cd is not null and event_at is not null
    )
    where rn = 1
)

select
    d.area_cd,
    a.admin_dong_code,
    a.gu_code,
    a.longitude,
    a.latitude,
    d.event_at,
    d.temperature,
    d.sensible_temperature,
    d.humidity,
    d.precipitation,
    d.precipitation_type,
    d.pm25,
    d.pm25_index,
    d.pm10,
    d.pm10_index,
    d.air_idx,
    d.air_idx_value,
    d.uv_index_lvl,
    d.collected_at
from deduped d
left join {{ ref('dim_seoul_area') }} a on d.area_cd = a.area_cd

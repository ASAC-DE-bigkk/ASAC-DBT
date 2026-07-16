-- silver: citydata 전기차 충전소·충전기 현황 (#192 신규 가치). grain = (area_cd, stat_id, charger_id, observed_at).
--
-- CHARGER_STTS 블록 = 장소당 충전소 배열, 각 충전소에 CHARGER_DETAILS(개별 충전기) 중첩.
-- **이중 UNNEST**(충전소 → 충전기)로 충전기 1개 = 1행. observed_at = 충전기 상태갱신시각
-- (STATUPDDT) — 상태 안 바뀌면 같은 값이 반복돼 grain 이 유지되고, 바뀌면 새 행(상태 변경 로그).
-- 룩백은 collected_at, dedup post-hook(order collected_at)로 R2 이중삽입 방지(다른 silver 동일).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['area_cd', 'stat_id', 'charger_id', 'observed_at'],
    on_table_exists='drop',
    post_hook=dedup_latest(['area_cd', 'stat_id', 'charger_id', 'observed_at'], order_col='collected_at'),
) }}

with src as (
    select
        area_cd,
        payload,
        {{ asac_axes.utc_to_kst('collected_at') }} as collected_at
    from {{ source('bronze_citydata', 'bronze_seoul_citydata') }}
    where block_name = 'CHARGER_STTS'
    {% if is_incremental() %}
      and {{ asac_axes.utc_to_kst('collected_at') }} >= (
          select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
          from {{ this }}
      )
    {% endif %}
),

stations as (
    select
        s.area_cd,
        s.collected_at,
        json_extract_scalar(st, '$.STAT_ID')       as stat_id,
        json_extract_scalar(st, '$.STAT_NM')       as stat_nm,
        json_extract_scalar(st, '$.STAT_ADDR')     as stat_addr,
        try_cast(json_extract_scalar(st, '$.STAT_X') as double) as stat_longitude,
        try_cast(json_extract_scalar(st, '$.STAT_Y') as double) as stat_latitude,
        json_extract_scalar(st, '$.STAT_USETIME')  as use_time,
        json_extract_scalar(st, '$.STAT_PARKPAY')  as parking_pay_yn,
        json_extract_scalar(st, '$.STAT_LIMITYN')  as limit_yn,
        json_extract_scalar(st, '$.STAT_KINDDETAIL') as place_kind,
        st as station_json
    from src s
    cross join unnest(cast(json_parse(s.payload) as array(json))) as t (st)
),

chargers as (
    select
        st.area_cd, st.collected_at, st.stat_id, st.stat_nm, st.stat_addr,
        st.stat_longitude, st.stat_latitude, st.use_time, st.parking_pay_yn, st.limit_yn, st.place_kind,
        json_extract_scalar(ch, '$.CHARGER_ID')   as charger_id,
        json_extract_scalar(ch, '$.CHARGER_TYPE') as charger_type,
        json_extract_scalar(ch, '$.CHARGER_STAT') as charger_stat,
        {{ asac_axes.kst_at("json_extract_scalar(ch, '$.STATUPDDT')") }} as observed_at,
        try_cast(json_extract_scalar(ch, '$.OUTPUT') as integer) as output_kw,
        json_extract_scalar(ch, '$.METHOD')       as method
    from stations st
    cross join unnest(cast(json_extract(st.station_json, '$.CHARGER_DETAILS') as array(json))) as t (ch)
),

deduped as (
    select *
    from (
        select *, row_number() over (
            partition by area_cd, stat_id, charger_id, observed_at order by collected_at desc) as rn
        from chargers
        where area_cd is not null and stat_id is not null and charger_id is not null and observed_at is not null
    )
    where rn = 1
)

select
    d.area_cd,
    a.admin_dong_code,
    a.gu_code,
    a.longitude,
    a.latitude,
    d.stat_id,
    d.stat_nm,
    d.stat_addr,
    d.stat_longitude,
    d.stat_latitude,
    d.use_time,
    d.parking_pay_yn,
    d.limit_yn,
    d.place_kind,
    d.charger_id,
    d.charger_type,
    d.charger_stat,
    d.output_kw,
    d.method,
    d.observed_at,
    d.collected_at
from deduped d
left join {{ ref('dim_seoul_area') }} a on d.area_cd = a.area_cd

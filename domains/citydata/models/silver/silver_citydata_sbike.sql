-- silver: citydata 따릉이 대여소 현황 (#69). grain = (area_cd, spot_id, observed_at).
--
-- SBIKE_STTS 블록은 대여소 배열(장소당 0~N개) — UNNEST 로 펼친다. 원천 갱신시각이
-- 없어 observed_at = collected_at(KST). 대여소 좌표는 원소의 X(경도)/Y(위도).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['area_cd', 'spot_id', 'observed_at'],
    on_table_exists='drop',
    post_hook=dedup_latest(['area_cd', 'spot_id', 'observed_at'], order_col='observed_at'),
) }}

with src as (
    select
        area_cd,
        payload,
        {{ asac_axes.utc_to_kst('collected_at') }} as observed_at
    from {{ source('bronze_citydata', 'bronze_seoul_citydata') }}
    where block_name = 'SBIKE_STTS'
    {% if is_incremental() %}
      -- 파티션 프루닝(ASK-Seoul#93): load_date 로 최근 파티션만 읽는다. bronze 는 load_date 로
      -- 파티셔닝되어 collected_at 술어만으로는 프루닝이 안 된다. 2일 창은 아래 30분
      -- collected_at 창의 상위집합(자정 경계·지연도착 커버) → 출력 불변, 스캔량만 준다.
      and load_date >= date_format(current_date - interval '2' day, '%Y-%m-%d')
      and {{ asac_axes.utc_to_kst('collected_at') }} >= (
          select coalesce(max(observed_at), timestamp '1970-01-01') - interval '30' minute
          from {{ this }}
      )
    {% endif %}
),

exploded as (
    select
        s.area_cd,
        s.observed_at,
        json_extract_scalar(spot, '$.SBIKE_SPOT_ID') as spot_id,
        json_extract_scalar(spot, '$.SBIKE_SPOT_NM') as spot_nm,
        try_cast(json_extract_scalar(spot, '$.SBIKE_PARKING_CNT') as integer) as parking_count,
        try_cast(json_extract_scalar(spot, '$.SBIKE_RACK_CNT') as integer) as rack_count,
        try_cast(json_extract_scalar(spot, '$.SBIKE_SHARED') as integer) as shared_rate_percent,
        try_cast(json_extract_scalar(spot, '$.SBIKE_X') as double) as spot_longitude,
        try_cast(json_extract_scalar(spot, '$.SBIKE_Y') as double) as spot_latitude
    from src s
    cross join unnest(cast(json_parse(s.payload) as array(json))) as t (spot)
),

deduped as (
    select *
    from (
        select *, row_number() over (
            partition by area_cd, spot_id, observed_at order by observed_at desc) as rn
        from exploded
        where area_cd is not null and spot_id is not null
    )
    where rn = 1
)

select
    d.area_cd,
    a.admin_dong_code,
    a.gu_code,
    a.longitude,
    a.latitude,
    d.spot_id,
    d.spot_nm,
    d.observed_at,
    d.parking_count,
    d.rack_count,
    d.shared_rate_percent,
    d.spot_longitude,
    d.spot_latitude
from deduped d
left join {{ ref('dim_seoul_area') }} a on d.area_cd = a.area_cd

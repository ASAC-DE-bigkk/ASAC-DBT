-- silver: bronze의 원본 payload(citydata_ppltn 레코드 JSON)를 개별 필드로 파싱하고
-- (area_nm, ppltn_time) 기준 최신 1건으로 중복 제거한 뒤, **위치(좌표)·행정구역(시/구/동)
-- 을 보강**한다. 사내에서 바로 활용 가능한 표준 형태를 목표로, 좌표/행정동을 여기서 붙인다.
--
-- incremental(merge): 5분 주기에 맞춰 최근 수집분만 파싱해 (area_nm, ppltn_time)
-- 키로 merge한다(bronze 전체 재스캔 없음). 지연 도착 대비 30분 lookback.
--
-- 보강(참조 조인):
--  * 좌표/분류: seed(seoul_ppltn_area_geo)를 area_cd로 left join → center_lon/lat, category
--  * 행정구역: area 중심점을 행정동 경계 seed(seoul_dong_boundary)에 point-in-polygon
--    → sido/sigungu/dong (동 code 앞 5자리 = 자치구라 sigungu도 함께). 도메인 통합 join 키.
--
-- ⚠ 새 컬럼(좌표/행정동) 추가 시 기존 테이블은 --full-refresh 로 재생성해야 한다.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['area_nm', 'ppltn_time'],
    on_table_exists='drop',
) }}

with bronze as (
    select
        trim(json_extract_scalar(payload, '$.AREA_NM')) as area_nm,
        trim(json_extract_scalar(payload, '$.AREA_CD')) as area_cd,
        lower(trim(json_extract_scalar(payload, '$.AREA_CONGEST_LVL'))) as area_congest_lvl,
        json_extract_scalar(payload, '$.AREA_CONGEST_MSG') as area_congest_msg,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.AREA_PPLTN_MIN')), '') as integer) as area_ppltn_min,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.AREA_PPLTN_MAX')), '') as integer) as area_ppltn_max,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.MALE_PPLTN_RATE')), '') as decimal(5, 2)) as male_ppltn_rate,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.FEMALE_PPLTN_RATE')), '') as decimal(5, 2)) as female_ppltn_rate,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.PPLTN_RATE_0')), '') as decimal(5, 2)) as ppltn_rate_0,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.PPLTN_RATE_10')), '') as decimal(5, 2)) as ppltn_rate_10,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.PPLTN_RATE_20')), '') as decimal(5, 2)) as ppltn_rate_20,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.PPLTN_RATE_30')), '') as decimal(5, 2)) as ppltn_rate_30,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.PPLTN_RATE_40')), '') as decimal(5, 2)) as ppltn_rate_40,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.PPLTN_RATE_50')), '') as decimal(5, 2)) as ppltn_rate_50,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.PPLTN_RATE_60')), '') as decimal(5, 2)) as ppltn_rate_60,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.PPLTN_RATE_70')), '') as decimal(5, 2)) as ppltn_rate_70,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.RESNT_PPLTN_RATE')), '') as decimal(5, 2)) as resnt_ppltn_rate,
        try_cast(nullif(trim(json_extract_scalar(payload, '$.NON_RESNT_PPLTN_RATE')), '') as decimal(5, 2)) as non_resnt_ppltn_rate,
        json_extract_scalar(payload, '$.REPLACE_YN') as replace_yn,
        json_extract_scalar(payload, '$.PPLTN_TIME') as ppltn_time,
        json_extract_scalar(payload, '$.FCST_YN') as fcst_yn,
        collected_at
    from {{ source('bronze', 'bronze_seoul_ppltn') }}
    {% if is_incremental() %}
    where collected_at >= (
        select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
        from {{ this }}
    )
    {% endif %}
),

ranked as (
    select
        *,
        row_number() over (
            partition by area_nm, ppltn_time
            order by collected_at desc
        ) as row_num
    from bronze
    where area_nm is not null
        and area_cd is not null
        and ppltn_time is not null
),

deduped as (
    select * from ranked where row_num = 1
),

area_admin as (
    -- area 중심점 → 행정동 판정(정적, area당 1건). 동 경계 하나로 시/구/동을 한 번에.
    select area_cd, sido, sigungu, dong
    from (
        select
            g.area_cd,
            '서울특별시' as sido,
            b.sigungu,
            b.dong,
            row_number() over (partition by g.area_cd order by b.dong) as rn
        from {{ ref('seoul_ppltn_area_geo') }} g
        left join {{ ref('seoul_dong_boundary') }} b
            on ST_Contains(ST_GeometryFromText(b.boundary_wkt), ST_Point(g.center_lon, g.center_lat))
    )
    where rn = 1
)

select
    d.area_nm,
    d.area_cd,
    aa.sido,
    aa.sigungu,
    aa.dong,
    geo.center_lon,
    geo.center_lat,
    geo.category as area_category,
    d.area_congest_lvl,
    d.area_congest_msg,
    d.area_ppltn_min,
    d.area_ppltn_max,
    d.male_ppltn_rate,
    d.female_ppltn_rate,
    d.ppltn_rate_0,
    d.ppltn_rate_10,
    d.ppltn_rate_20,
    d.ppltn_rate_30,
    d.ppltn_rate_40,
    d.ppltn_rate_50,
    d.ppltn_rate_60,
    d.ppltn_rate_70,
    d.resnt_ppltn_rate,
    d.non_resnt_ppltn_rate,
    d.replace_yn,
    d.ppltn_time,
    d.fcst_yn,
    d.collected_at
from deduped d
left join {{ ref('seoul_ppltn_area_geo') }} geo
    on d.area_cd = geo.area_cd
left join area_admin aa
    on d.area_cd = aa.area_cd

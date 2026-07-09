-- silver: bronze의 원본 payload(citydata_ppltn 레코드 JSON)를 개별 필드로 파싱하고
-- (area_nm, ppltn_time) 기준 최신 1건으로 중복 제거한 뒤, **위치(좌표)·행정구역·시간축**
-- 을 #48 공통축 표준(asac_axes)으로 보강한다. 사내에서 바로 활용 가능한 표준 형태.
--
-- incremental(merge): 5분 주기에 맞춰 최근 수집분만 파싱해 (area_nm, ppltn_time)
-- 키로 merge한다(bronze 전체 재스캔 없음). 지연 도착 대비 30분 lookback.
--
-- 보강(참조 조인, #48 공통축 표준 — asac_axes 패키지):
--  * 좌표/분류: seed(seoul_ppltn_area_geo)를 area_cd로 left join → longitude/latitude, category
--  * 행정구역: area 중심점을 공용 경계 seed(asac_axes.seoul_admin_dong_boundary)에
--    point-in-polygon → gu/admin_dong + 행안부 admin_dong_code(10, canonical)·gu_code(5).
--    도메인 통합 join 키 = admin_dong_code(동)·gu_code(구).
--  * 시간축: ppltn_time(varchar) → event_at(KST timestamp, asac_axes.kst_at) 신설(원본 유지).
--
-- ⚠ 공용 패키지 참조: packages.yml(local asac_axes) + dbt deps 필요. #49 머지 후 dev 반영.
-- ⚠ 새 컬럼(좌표/행정동/event_at) 추가 시 기존 테이블은 --full-refresh 로 재생성해야 한다.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['area_nm', 'ppltn_time'],
    on_table_exists='drop',
) }}

with bronze as (
    select
        trim(json_extract_scalar(payload, '$[0].AREA_NM')) as area_nm,
        trim(json_extract_scalar(payload, '$[0].AREA_CD')) as area_cd,
        lower(trim(json_extract_scalar(payload, '$[0].AREA_CONGEST_LVL'))) as area_congest_lvl,
        json_extract_scalar(payload, '$[0].AREA_CONGEST_MSG') as area_congest_msg,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].AREA_PPLTN_MIN')), '') as integer) as area_ppltn_min,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].AREA_PPLTN_MAX')), '') as integer) as area_ppltn_max,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].MALE_PPLTN_RATE')), '') as decimal(5, 2)) as male_ppltn_rate,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].FEMALE_PPLTN_RATE')), '') as decimal(5, 2)) as female_ppltn_rate,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].PPLTN_RATE_0')), '') as decimal(5, 2)) as ppltn_rate_0,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].PPLTN_RATE_10')), '') as decimal(5, 2)) as ppltn_rate_10,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].PPLTN_RATE_20')), '') as decimal(5, 2)) as ppltn_rate_20,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].PPLTN_RATE_30')), '') as decimal(5, 2)) as ppltn_rate_30,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].PPLTN_RATE_40')), '') as decimal(5, 2)) as ppltn_rate_40,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].PPLTN_RATE_50')), '') as decimal(5, 2)) as ppltn_rate_50,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].PPLTN_RATE_60')), '') as decimal(5, 2)) as ppltn_rate_60,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].PPLTN_RATE_70')), '') as decimal(5, 2)) as ppltn_rate_70,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].RESNT_PPLTN_RATE')), '') as decimal(5, 2)) as resnt_ppltn_rate,
        try_cast(nullif(trim(json_extract_scalar(payload, '$[0].NON_RESNT_PPLTN_RATE')), '') as decimal(5, 2)) as non_resnt_ppltn_rate,
        json_extract_scalar(payload, '$[0].REPLACE_YN') as replace_yn,
        json_extract_scalar(payload, '$[0].PPLTN_TIME') as ppltn_time,
        json_extract_scalar(payload, '$[0].FCST_YN') as fcst_yn,
        collected_at
    from {{ source('bronze_citydata', 'bronze_seoul_citydata') }}
    -- 인구는 citydata 번들의 LIVE_PPLTN_STTS 블록에서 파싱한다(citydata_ppltn 과 필드 100%
    -- 동일 검증). 블록 payload 는 [{...}] 배열이라 위에서 $[0] 로 꺼낸다. 단일 수집원 통합.
    where block_name = 'LIVE_PPLTN_STTS'
    {% if is_incremental() %}
      and collected_at >= (
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
    -- area 중심점 → 행정동 판정(정적, area당 1건). 공용 경계 seed(asac_axes)로
    -- gu/admin_dong 명칭 + 행안부 admin_dong_code(canonical)·gu_code를 한 번에 보강.
    select area_cd, gu, admin_dong, gu_code, admin_dong_code
    from (
        select
            g.area_cd,
            b.sigungu as gu,
            b.dong as admin_dong,
            b.gu_code,
            b.admin_dong_code,
            row_number() over (partition by g.area_cd order by b.admin_dong_code) as rn
        from {{ ref('seoul_ppltn_area_geo') }} g
        left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} b
            on {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'g.center_lon', 'g.center_lat') }}
    )
    where rn = 1
)

select
    d.area_nm,
    d.area_cd,
    '서울특별시' as sido,
    aa.gu,
    aa.admin_dong,
    aa.gu_code,
    aa.admin_dong_code,
    geo.center_lon as longitude,
    geo.center_lat as latitude,
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
    {{ asac_axes.kst_at('d.ppltn_time') }} as event_at,
    d.ppltn_time,
    d.fcst_yn,
    d.collected_at
from deduped d
left join {{ ref('seoul_ppltn_area_geo') }} geo
    on d.area_cd = geo.area_cd
left join area_admin aa
    on d.area_cd = aa.area_cd

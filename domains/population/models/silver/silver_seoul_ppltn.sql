-- silver: bronze의 원본 payload(citydata_ppltn 레코드 JSON)를 개별 필드로 파싱하고
-- (area_nm, ppltn_time) 기준 최신 1건으로 중복 제거한다.
--
-- 지금은 table(전체 재생성). 규모가 작아 15분 주기에 충분히 싸다.
-- (incremental(merge)은 dbt-trino + R2 Data Catalog에서 is_incremental 첫 run 이슈가 있어
--  향후 과제로 둔다 — docs 참고.)

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
)

select
    area_nm,
    area_cd,
    area_congest_lvl,
    area_congest_msg,
    area_ppltn_min,
    area_ppltn_max,
    male_ppltn_rate,
    female_ppltn_rate,
    ppltn_rate_0,
    ppltn_rate_10,
    ppltn_rate_20,
    ppltn_rate_30,
    ppltn_rate_40,
    ppltn_rate_50,
    ppltn_rate_60,
    ppltn_rate_70,
    resnt_ppltn_rate,
    non_resnt_ppltn_rate,
    replace_yn,
    ppltn_time,
    fcst_yn,
    collected_at
from ranked
where row_num = 1

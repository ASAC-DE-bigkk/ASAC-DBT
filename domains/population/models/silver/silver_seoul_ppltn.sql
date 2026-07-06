-- silver: bronze의 원본 payload(citydata_ppltn 레코드 JSON)를 개별 필드로 파싱하고
-- (area_nm, ppltn_time) 기준 최신 1건으로 중복 제거한다.
--
-- incremental(merge): 5분 주기에 맞춰 최근 수집분만 파싱해 (area_nm, ppltn_time)
-- 키로 merge한다(bronze 전체 재스캔 없음). 지연 도착 대비 30분 lookback을 두고,
-- 같은 키가 다시 오면 collected_at이 더 최신인 행으로 갱신된다.
--
-- ⚠ R2 Data Catalog eventual consistency: 테이블을 drop한 직후에는 카탈로그가
-- 잠시 "존재"로 응답해 is_incremental()이 잘못 true가 될 수 있다(README 참고).
-- 기존 테이블을 유지한 채 전환하면 해당 없음. drop이 필요하면 잠시 후 재실행.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['area_nm', 'ppltn_time'],
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
    -- 이미 반영된 시각 이후(-30분 여유)만 스캔. merge가 기존 키를 갱신하므로
    -- lookback으로 같은 행을 다시 읽어도 결과는 동일(멱등).
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

-- silver: citydata 실시간 상권(신한카드) 블록 파싱 (#69). grain = (area_cd, event_at).
--
-- bronze(bronze_seoul_citydata)의 LIVE_CMRCL_STTS 블록 payload 를 개별 필드로 분해하고
-- 블록 자체 갱신시각(CMRCL_TIME, "yyyyMMdd HHmm" — 실측 10분 주기)을 event_at 으로.
-- 수집(10분)이 갱신(10분)보다 촘촘하지 않아 같은 event_at 이 반복 수집될 수 있고,
-- 배치 내 dedup(최신 collected_at) + merge 가 이를 흡수한다(멱등).

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['area_cd', 'event_at'],
    on_table_exists='drop',
    post_hook=dedup_latest(['area_cd', 'event_at']),
) }}

with src as (
    select
        area_cd,
        area_nm,
        payload,
        {{ asac_axes.utc_to_kst('collected_at') }} as collected_at
    from {{ source('bronze_citydata', 'bronze_seoul_citydata') }}
    where block_name = 'LIVE_CMRCL_STTS'
    {% if is_incremental() %}
      -- 파티션 프루닝(ASK-Seoul#93): load_date 로 최근 파티션만 읽는다. bronze 는 load_date 로
      -- 파티셔닝되어 collected_at 술어만으로는 프루닝이 안 된다. 2일 창은 아래 30분
      -- collected_at 창의 상위집합(자정 경계·지연도착 커버) → 출력 불변, 스캔량만 준다.
      and load_date >= date_format(current_date - interval '2' day, '%Y-%m-%d')
      and {{ asac_axes.utc_to_kst('collected_at') }} >= (
          select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
          from {{ this }}
      )
    {% endif %}
),

parsed as (
    select
        area_cd,
        area_nm,
        {{ asac_axes.kst_at_from_parts(
            "substr(json_extract_scalar(payload, '$.CMRCL_TIME'), 1, 8)",
            "substr(json_extract_scalar(payload, '$.CMRCL_TIME'), 10, 4)") }} as event_at,
        json_extract_scalar(payload, '$.AREA_CMRCL_LVL') as cmrcl_lvl,
        try_cast(json_extract_scalar(payload, '$.AREA_SH_PAYMENT_CNT') as integer) as payment_count,
        try_cast(json_extract_scalar(payload, '$.AREA_SH_PAYMENT_AMT_MIN') as bigint) as payment_amt_min,
        try_cast(json_extract_scalar(payload, '$.AREA_SH_PAYMENT_AMT_MAX') as bigint) as payment_amt_max,
        try_cast(json_extract_scalar(payload, '$.CMRCL_MALE_RATE') as decimal(5, 2)) as male_rate,
        try_cast(json_extract_scalar(payload, '$.CMRCL_FEMALE_RATE') as decimal(5, 2)) as female_rate,
        try_cast(json_extract_scalar(payload, '$.CMRCL_10_RATE') as decimal(5, 2)) as rate_10,
        try_cast(json_extract_scalar(payload, '$.CMRCL_20_RATE') as decimal(5, 2)) as rate_20,
        try_cast(json_extract_scalar(payload, '$.CMRCL_30_RATE') as decimal(5, 2)) as rate_30,
        try_cast(json_extract_scalar(payload, '$.CMRCL_40_RATE') as decimal(5, 2)) as rate_40,
        try_cast(json_extract_scalar(payload, '$.CMRCL_50_RATE') as decimal(5, 2)) as rate_50,
        try_cast(json_extract_scalar(payload, '$.CMRCL_60_RATE') as decimal(5, 2)) as rate_60,
        try_cast(json_extract_scalar(payload, '$.CMRCL_PERSONAL_RATE') as decimal(5, 2)) as personal_rate,
        try_cast(json_extract_scalar(payload, '$.CMRCL_CORPORATION_RATE') as decimal(5, 2)) as corporation_rate,
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
    d.cmrcl_lvl,
    d.payment_count,
    d.payment_amt_min,
    d.payment_amt_max,
    d.male_rate,
    d.female_rate,
    d.rate_10, d.rate_20, d.rate_30, d.rate_40, d.rate_50, d.rate_60,
    d.personal_rate,
    d.corporation_rate,
    d.collected_at
from deduped d
left join {{ ref('dim_seoul_area') }} a on d.area_cd = a.area_cd

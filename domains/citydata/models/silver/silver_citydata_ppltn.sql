-- silver: bronze의 원본 payload(citydata_ppltn 레코드 JSON)를 개별 필드로 파싱하고
-- (area_nm, ppltn_time) 기준 최신 1건으로 중복 제거한 뒤, **위치(좌표)·행정구역·시간축**
-- 을 #48 공통축 표준(asac_axes)으로 보강한다. 사내에서 바로 활용 가능한 표준 형태.
--
-- incremental(merge): 5분 주기에 맞춰 최근 수집분만 파싱해 (area_nm, ppltn_time)
-- 키로 merge한다(bronze 전체 재스캔 없음). 지연 도착 대비 30분 lookback.
--
-- 보강(참조 조인, #48 공통축 표준):
--  * 공간축: dim_seoul_area(area_cd) 조인 → 좌표·분류·gu/admin_dong + 행안부
--    admin_dong_code(10, canonical)·gu_code(5). 다른 citydata silver 와 동일하게 공통
--    dim 을 조인원으로 써 point-in-polygon 을 한 곳(dim)에서만 계산한다(중복 로직 제거).
--  * 시간축: ppltn_time(varchar) → event_at(KST timestamp, asac_axes.kst_at) 신설(원본 유지).
--
-- 스키마: seoul_citydata (다른 citydata 신호와 통합 — 인구도 같은 citydata 번들 소스).
-- ⚠ 새 컬럼 추가 시 기존 테이블은 --full-refresh 로 재생성해야 한다.

{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['area_cd', 'event_at'],
    on_table_exists='drop',
    post_hook=dedup_latest(['area_cd', 'event_at']),
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
        -- 시간축: PPLTN_TIME(원본 문자열)을 KST timestamp 로 파싱해 event_at 으로.
        -- 원본 문자열은 bronze payload 에 보존되므로 silver 엔 파싱본만 둔다.
        {{ asac_axes.kst_at("json_extract_scalar(payload, '$[0].PPLTN_TIME')") }} as event_at,
        json_extract_scalar(payload, '$[0].FCST_YN') as fcst_yn,
        -- 시간축 표준: 수집시각도 KST 로 통일(다른 citydata silver 와 동일 — asac_axes.utc_to_kst).
        {{ asac_axes.utc_to_kst('collected_at') }} as collected_at
    from {{ source('bronze_citydata', 'bronze_seoul_citydata') }}
    -- 인구는 citydata 번들의 LIVE_PPLTN_STTS 블록에서 파싱한다(citydata_ppltn 과 필드 100%
    -- 동일 검증). 블록 payload 는 [{...}] 배열이라 위에서 $[0] 로 꺼낸다. 단일 수집원 통합.
    where block_name = 'LIVE_PPLTN_STTS'
    {% if is_incremental() %}
      -- 파티션 프루닝: bronze 는 load_date(varchar)로 파티셔닝 — collected_at 술어만으론
      -- 파티션을 못 쳐내 매 실행 bronze 전체를 스캔했다(ASK-Seoul#93). 최근 파티션만 읽게
      -- load_date 창을 먼저 건다. 2일 창은 아래 30분 collected_at 창의 안전한 상위집합
      -- (자정 경계·지연 도착 커버)이라 출력 행은 불변, 스캔량만 준다.
      and load_date >= date_format(current_date - interval '2' day, '%Y-%m-%d')
      and {{ asac_axes.utc_to_kst('collected_at') }} >= (
        select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
        from {{ this }}
    )
    {% endif %}
),

ranked as (
    select
        *,
        row_number() over (
            partition by area_cd, event_at
            order by collected_at desc
        ) as row_num
    from bronze
    where area_cd is not null
        and event_at is not null
),

deduped as (
    select * from ranked where row_num = 1
)

select
    d.area_cd,
    a.admin_dong_code,
    a.gu_code,
    a.longitude,
    a.latitude,
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
    d.event_at,
    d.fcst_yn,
    d.collected_at
from deduped d
left join {{ ref('dim_seoul_area') }} a
    on d.area_cd = a.area_cd

-- silver: 서울 문화행사 기간 fact. 자연키 부재 → event_key = md5(제목|시작일|장소) —
-- 제목 수정 시 분열은 알려진 한계(설계 §3-G). 좌표: LOT=경도, LAT=위도.
-- dedup 은 load_date 우선(§3-A) — 7/1 proxy(ingest_ts=7/6 수동)가 이후 관측을 못 가림.
--
-- **incremental — 새 load_date 파티션만 읽는다(#370).** bronze 는 매일 전체 목록을 append 하므로
-- 전량 스캔은 메모리가 누적일수에 비례해 늘고 상한이 없다. prod 684,759행에서 Trino per-node
-- 2GB 를 쳤고(ScanFilterAndProjectOperator-ConnectorPageSource 1.16GB) 하류 gold 4종이 스킵됐다.
--
-- **세종(#330)처럼 최신 파티션만 남기면 안 된다.** 세종은 원천이 매일 전량을 다시 주지만,
-- 문화행사 API 는 **끝난 행사를 다음 날 목록에서 뺀다** — 실측 19,699건 중 248건(1.26%)이
-- 최신 load_date 에 없고 그 대부분이 이미 종료된 행사다. 90일 룩백을 세는
-- gold_culture_activity_by_dong·calendar_density 가 그만큼 조용히 줄어든다. 그래서 잘라내지 않고
-- **누적을 테이블에 남긴 채 스캔만 줄인다**: 목록에서 빠진 과거 행사는 delete+insert 대상이 아니라
-- 그대로 보존된다. 첫 전환은 dev·prod 모두 테이블이 이미 차 있어 full-refresh 가 필요 없다.
--
-- `>=` 인 이유: 같은 load_date 재적재(수동 리로드)를 다시 처리해야 최신 관측이 반영된다.
-- unique_key 가 event_key 라 재처리해도 중복이 아니라 교체다. load_date 는 varchar('YYYY-MM-DD')라
-- 사전식 비교가 곧 시간순이다.
{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key='event_key',
    on_table_exists='drop',
) }}

with bronze as (
    select
        json_extract_scalar(record_json, '$.TITLE')    as title_raw,
        json_extract_scalar(record_json, '$.GUNAME')   as gu_raw,
        json_extract_scalar(record_json, '$.PLACE')    as place_raw,
        json_extract_scalar(record_json, '$.CODENAME') as category,
        json_extract_scalar(record_json, '$.IS_FREE')  as is_free,
        json_extract_scalar(record_json, '$.STRTDATE') as start_raw,
        json_extract_scalar(record_json, '$.END_DATE') as end_raw,
        json_extract_scalar(record_json, '$.LOT')      as lon_raw,   -- 경도
        json_extract_scalar(record_json, '$.LAT')      as lat_raw,   -- 위도
        ingest_ts,
        {{ culture_lineage('seoul') }}
    from {{ source('culture_bronze', 'bronze_seoul_cultural_event') }}
    {% if is_incremental() %}
    where load_date >= (select coalesce(max(load_date), '1900-01-01') from {{ this }})
    {% endif %}
),

typed as (
    select
        nullif(trim(title_raw), '') as event_title,
        nullif(trim(gu_raw), '')    as gu,
        nullif(trim(place_raw), '') as place,
        nullif(trim(category), '')  as category,
        nullif(trim(is_free), '')   as is_free,
        try(cast(substr(start_raw, 1, 10) as date)) as event_start_date,
        try(cast(substr(end_raw, 1, 10) as date))   as event_end_date,
        {{ asac_axes.seoul_lonlat('lon_raw', 'lat_raw') }},
        ingest_ts, source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date
    from bronze
    where nullif(trim(title_raw), '') is not null
),

keyed as (
    select
        to_hex(md5(to_utf8(concat_ws('|',
            coalesce(event_title, ''),
            coalesce(cast(event_start_date as varchar), ''),
            coalesce(place, ''))))) as event_key,
        typed.*
    from typed
),

latest as (
    select * from (
        select *, row_number() over (partition by event_key order by {{ culture_dedup_order() }}) as rn
        from keyed
    ) where rn = 1
),

dong_map as {{ culture_dong_map('latest') }},

{{ culture_admin_canon() }},

stamped as (
select
    l.event_key, l.event_title, l.place, l.category, l.is_free,
    l.event_start_date, l.event_end_date,
    cast(l.event_start_date as timestamp(6)) as event_at,
    l.longitude, l.latitude, l.gu,
    {{ culture_admin_stamp_cols() }},
    l.source_system, l.dag_run_id, l.raw_object_key, l.collected_at, l.ingested_at, l.load_date
from latest l
{{ culture_admin_stamp_joins('l') }}
)

select *, {{ culture_quality_status() }} as quality_status
from stamped

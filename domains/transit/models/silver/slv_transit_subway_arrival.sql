-- slv_transit_subway_arrival — 지하철 실시간 도착정보 정제.
--
-- grain: (statn_id=statnId, ordkey, recptn_dt=recptnDt). incremental(merge),
--   ingested_at 기준 -2h lookback.
-- 시간축: event_at = recptnDt KST(도착정보 수신시각, 도메인 대표시각).
-- 공간축: dim_transit_station 조인으로 부착. 조인 키는 '역명 + 노선':
--   - arrival subwayId → seoul_subway_line_code seed 로 route 라벨 변환(1002→2호선 등)
--   - 역명은 양쪽 괄호 부기 제거 후 매칭(dim.station_name_join)
--   - (statnNm_norm, line_name) 이 dim (station_name_join, route) 와 1:1 매칭됨을 실증.

{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['statn_id', 'ordkey', 'recptn_dt'],
) }}

with bronze as (
    select
        trim(json_extract_scalar(raw, '$.statnId')) as statn_id,
        trim(json_extract_scalar(raw, '$.ordkey')) as ordkey,
        json_extract_scalar(raw, '$.recptnDt') as recptn_dt,
        {{ asac_axes.kst_at("json_extract_scalar(raw, '$.recptnDt')") }} as event_at,
        trim(json_extract_scalar(raw, '$.subwayId')) as subway_id,
        trim(json_extract_scalar(raw, '$.statnNm')) as statn_nm,
        trim(regexp_replace(json_extract_scalar(raw, '$.statnNm'), '\(.*\)', '')) as statn_nm_join,
        json_extract_scalar(raw, '$.trainLineNm') as train_line_nm,
        json_extract_scalar(raw, '$.updnLine') as updn_line,
        json_extract_scalar(raw, '$.btrainNo') as btrain_no,
        json_extract_scalar(raw, '$.btrainSttus') as btrain_sttus,
        try(cast(json_extract_scalar(raw, '$.barvlDt') as integer)) as barvl_dt_sec,
        json_extract_scalar(raw, '$.arvlMsg2') as arvl_msg2,
        json_extract_scalar(raw, '$.arvlMsg3') as arvl_msg3,
        json_extract_scalar(raw, '$.arvlCd') as arvl_cd,
        cast(dag_run_id as varchar) as dag_run_id,
        ingested_at
    from {{ source('transit_bronze', 'subway_arrival') }}
    {% if is_incremental() %}
    where ingested_at >= (
        select coalesce(max(ingested_at), timestamp '1970-01-01') - interval '2' hour
        from {{ this }}
    )
    {% endif %}
),

ranked as (
    select
        *,
        row_number() over (
            partition by statn_id, ordkey, recptn_dt
            order by ingested_at desc
        ) as row_num
    from bronze
    where statn_id is not null
      and ordkey is not null
      and recptn_dt is not null
),

line as (
    select subway_id, line_name
    from {{ ref('seoul_subway_line_code') }}
)

select
    b.statn_id,
    b.ordkey,
    b.recptn_dt,
    b.event_at,
    b.subway_id,
    l.line_name as route,
    b.statn_nm,
    b.train_line_nm,
    b.updn_line,
    b.btrain_no,
    b.btrain_sttus,
    b.barvl_dt_sec,
    b.arvl_msg2,
    b.arvl_msg3,
    b.arvl_cd,
    d.station_id,
    d.latitude,
    d.longitude,
    d.admin_dong_code,
    d.gu_code,
    b.dag_run_id,
    b.ingested_at
from ranked b
left join line l
    on b.subway_id = l.subway_id
left join {{ ref('dim_transit_station') }} d
    on b.statn_nm_join = d.station_name_join
   and l.line_name = d.route
where b.row_num = 1

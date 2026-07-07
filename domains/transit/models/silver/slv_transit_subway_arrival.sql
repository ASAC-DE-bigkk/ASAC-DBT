-- slv_transit_subway_arrival — 지하철 실시간 도착정보 정제.
--
-- grain: (statn_id=statnId, ordkey, recptn_dt=recptnDt). incremental(merge),
--   ingested_at 기준 -2h lookback.
-- 시간축: event_at = recptnDt KST(도착정보 수신시각, 도메인 대표시각).
-- 공간축: dim_transit_station 조인으로 부착. 조인 키는 '역명 + 노선':
--   - seed(subway_id→line_name) × dim(route=line_name) 을 미리 조인해
--     station_by_line = (subway_id, station_name_join) → 역 단일 매핑을 만든다.
--     하나의 subwayId 가 복수 노선 라벨을 포괄하는 경우(1075→분당선·수인선,
--     1077→신분당선 계열)는 seed 다행으로 커버한다.
--   - arrival 은 (subway_id, statnNm_join) 으로 이 매핑에 1회 조인(다단 조인 제거).
--   - (subway_id, station_name_join) 유일성은 singular 테스트로 계약(실데이터 중복 0건 실증).
--   - route 표시는 매칭된 dim.route(정확 라벨), 미매칭 시 seed 대표 라벨로 fallback.

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
        -- lstcarAt 은 원문이 0/1 플래그. '_at' 접미사는 공통축 계약상 KST timestamp 전용이라
        -- 그대로 스네이크화(lstcar_at)하지 않고 여부형 이름(is_last_train)으로 캐스트한다.
        try(cast(json_extract_scalar(raw, '$.lstcarAt') as integer)) as is_last_train,
        trim(json_extract_scalar(raw, '$.bstatnNm')) as terminal_statn_nm,
        try(cast(json_extract_scalar(raw, '$.trnsitCo') as integer)) as transfer_line_cnt,
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

-- seed × dim 을 route=line_name 정확 매핑으로 미리 조인 → (subway_id, station_name_join) 단일 매핑.
station_by_line as (
    select
        s.subway_id,
        d.station_name_join,
        d.station_id,
        d.route,
        d.latitude,
        d.longitude,
        d.admin_dong_code,
        d.gu_code
    from {{ ref('seoul_subway_line_code') }} s
    join {{ ref('dim_transit_station') }} d
        on d.route = s.line_name
),

-- subwayId 당 대표 라벨(다행 seed 는 base 라벨이 최소값). 미매칭 행의 route fallback 용.
line_label as (
    select subway_id, min(line_name) as line_name
    from {{ ref('seoul_subway_line_code') }}
    group by subway_id
)

select
    b.statn_id,
    b.ordkey,
    b.recptn_dt,
    b.event_at,
    b.subway_id,
    coalesce(sbl.route, ll.line_name) as route,
    b.statn_nm,
    b.train_line_nm,
    b.updn_line,
    b.btrain_no,
    b.btrain_sttus,
    b.barvl_dt_sec,
    b.arvl_msg2,
    b.arvl_msg3,
    b.arvl_cd,
    b.is_last_train,
    b.terminal_statn_nm,
    b.transfer_line_cnt,
    sbl.station_id,
    sbl.latitude,
    sbl.longitude,
    sbl.admin_dong_code,
    sbl.gu_code,
    b.dag_run_id,
    b.ingested_at
from ranked b
left join station_by_line sbl
    on b.subway_id = sbl.subway_id
   and b.statn_nm_join = sbl.station_name_join
left join line_label ll
    on b.subway_id = ll.subway_id
where b.row_num = 1

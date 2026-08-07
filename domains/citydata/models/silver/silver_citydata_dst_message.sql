-- silver: citydata 재난문자/경보 — LIVE_DST_MESSAGE 블록 파싱. grain = (area_cd, event_at, dst_type).
--
-- 블록 payload 는 [{DST_SE_NM, EMRG_STEP_NM, MSG_CN, CRT_DT}, ...] **배열**(한 응답에 여러 재난문자
-- 가능)이라 UNNEST 로 분해한다. 같은 문자가 여러 area·5분마다 반복 수집되므로 grain 당 최신 1건만
-- (post_hook dedup_latest — R2 비원자성 이중삽입 방어, 다른 citydata silver 와 동일).
-- event_at = CRT_DT("yyyy-MM-dd HH:mm:ss", 이미 KST — 원 출처 행정안전부 재난문자 생성시각).
-- 빈 응답([])이 대부분인 평시엔 행 없음(정상 0건), 폭염·호우 등 재난기에만 채워진다.
{{ config(
    schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema),
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['area_cd', 'event_at', 'dst_type'],
    on_table_exists='drop',
    post_hook=dedup_latest(['area_cd', 'event_at', 'dst_type']),
) }}

with src as (
    select
        area_cd,
        payload,
        {{ asac_axes.utc_to_kst('collected_at') }} as collected_at
    from {{ source('bronze_citydata', 'bronze_seoul_citydata') }}
    where block_name = 'LIVE_DST_MESSAGE'
      and length(payload) > 10   -- 빈 배열([]) 제외 (평시 미수록)
    {% if is_incremental() %}
      -- 파티션 프루닝(ASK-Seoul#93): load_date 로 최근 파티션만. 2일 창은 아래 30분 창의 상위집합.
      and load_date >= date_format(current_date - interval '2' day, '%Y-%m-%d')
      and {{ asac_axes.utc_to_kst('collected_at') }} >= (
          select coalesce(max(collected_at), timestamp '1970-01-01') - interval '30' minute
          from {{ this }}
      )
    {% endif %}
),

exploded as (
    select
        s.area_cd,
        json_extract_scalar(msg, '$.DST_SE_NM') as dst_type,
        json_extract_scalar(msg, '$.EMRG_STEP_NM') as emrg_step,
        json_extract_scalar(msg, '$.MSG_CN') as msg_cn,
        try_cast(json_extract_scalar(msg, '$.CRT_DT') as timestamp(6)) as event_at,
        s.collected_at
    from src s
    cross join unnest(cast(json_parse(s.payload) as array(json))) as t(msg)
),

deduped as (
    select *
    from (
        select *, row_number() over (
            partition by area_cd, event_at, dst_type order by collected_at desc) as rn
        from exploded
        where area_cd is not null and event_at is not null and dst_type is not null
    )
    where rn = 1
)

select
    d.area_cd,
    a.admin_dong_code,
    a.gu_code,
    a.longitude,
    a.latitude,
    d.dst_type,
    d.emrg_step,
    d.msg_cn,
    d.event_at,
    d.collected_at
from deduped d
left join {{ ref('dim_seoul_area') }} a on d.area_cd = a.area_cd

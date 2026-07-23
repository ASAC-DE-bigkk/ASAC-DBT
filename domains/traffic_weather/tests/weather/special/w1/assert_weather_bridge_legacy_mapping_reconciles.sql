-- W1 격리 스모크 전용(#159): 브릿지 모델·시드와 동일한 모드 가드.
-- dev에는 브릿지 테이블이 없으므로(환경 가드가 빌드 금지) 셀렉터 유출 시 TABLE_NOT_FOUND로
-- transform이 정지한다 — 2026-07-12 14:30Z부터 4연속 실패 사례.
{{ config(enabled=(var('weather_w1_initial_build_mode', '') == 'bounded_isolated_smoke')) }}

with legacy as (
    select cast(place_id as varchar) as place_id,
           cast(source_admin_code as varchar) as source_admin_code,
           cast(nx as integer) as nx,
           cast(ny as integer) as ny
    from {{ ref('weather_place_grid_mapping') }}
),
bridge as (
    select place_id, source_admin_code, nx, ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where bridge_version = 'weather_admin_dong_grid_bridge_v1'
),
missing as (select * from legacy except select * from bridge),
extra as (select * from bridge except select * from legacy),
-- 용신동 수동 backfill(2026-07-23)은 legacy에 없는 유일한 허용 초과분이다.
unexpected_extra as (
    select * from extra
    where not (
        place_id = 'seoul_admd_1123053600'
        and source_admin_code = '1123053600'
        and nx = 61
        and ny = 127
    )
)
select * from missing
union all
select * from unexpected_extra

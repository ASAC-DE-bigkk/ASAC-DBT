-- W1 격리 스모크 전용(#159): 브릿지 모델·시드와 동일한 모드 가드.
-- dev에는 브릿지 테이블이 없으므로(환경 가드가 빌드 금지) 셀렉터 유출 시 TABLE_NOT_FOUND로
-- transform이 정지한다 — 2026-07-12 14:30Z부터 4연속 실패 사례.
{{ config(enabled=(var('weather_w1_initial_build_mode', '') == 'bounded_isolated_smoke')) }}

with invalid_interval as (
    select source_admin_code, bridge_version, nx, ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where valid_from_at is not null and valid_to_at is not null
      and valid_from_at >= valid_to_at
),
overlap as (
    select left_side.source_admin_code, left_side.bridge_version, left_side.nx, left_side.ny
    from {{ ref('bridge_weather_admin_dong_grid') }} left_side
    join {{ ref('bridge_weather_admin_dong_grid') }} right_side
      on left_side.source_admin_code = right_side.source_admin_code
     and left_side.nx = right_side.nx
     and left_side.ny = right_side.ny
     and left_side.bridge_version < right_side.bridge_version
     and left_side.valid_from_at < coalesce(right_side.valid_to_at, timestamp '9999-12-31 00:00:00')
     and right_side.valid_from_at < coalesce(left_side.valid_to_at, timestamp '9999-12-31 00:00:00')
    where left_side.valid_from_at is not null and right_side.valid_from_at is not null
)
select * from invalid_interval
union all
select * from overlap

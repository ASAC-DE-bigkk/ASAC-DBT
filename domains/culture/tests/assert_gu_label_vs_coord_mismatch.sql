-- 원본 구명(정답 라벨) vs 좌표 유래 구(admin_dong_code 앞 5자리) 불일치 실측.
-- 단순화 경계의 오배정률 데이터 축적(#48 코멘트) — 정밀 경계 교체 이슈의 근거·벤치마크.
-- warn: 경계 오배정은 v1 수용, 데이터만 쌓는다.
{{ config(severity = 'warn') }}

with cw as (select distinct gu_code, gu from {{ ref('seoul_admin_dong_crosswalk') }}),

unioned as (
    select 'silver_culture_event' as model, event_key as row_key, gu, admin_dong_code
    from {{ ref('silver_culture_event') }}
    union all
    select 'silver_culture_facility', facility_id, gu, admin_dong_code
    from {{ ref('silver_culture_facility') }}
    union all
    select 'silver_culture_space', space_key, gu, admin_dong_code
    from {{ ref('silver_culture_space') }}
    union all
    select 'silver_culture_reservation', service_id || '|' || load_date, gu, admin_dong_code
    from {{ ref('silver_culture_reservation') }}
)

select u.model, u.row_key, u.gu as label_gu, c.gu as coord_gu
from unioned u
join cw c on c.gu_code = substr(u.admin_dong_code, 1, 5)
where u.gu is not null
  and u.admin_dong_code is not null
  and u.gu <> c.gu

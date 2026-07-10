-- #48: 공간 silver 의 admin_dong_code 가 bronze canonical(dim_admin_dong)에 존재하는지.
-- 미존재 = boundary seed(좌표→코드) 가 bronze 개정과 어긋남(재편/drift). warn — 알려진
-- 재편 동(신설동/상일1·2동 등) 소수 미매칭 수용, 규모만 계측.
{{ config(severity = 'warn') }}

with silver_codes as (
    select admin_dong_code from {{ ref('silver_culture_event') }}
    union select admin_dong_code from {{ ref('silver_culture_exhibition') }}
    union select admin_dong_code from {{ ref('silver_culture_reservation') }}
    union select admin_dong_code from {{ ref('silver_culture_sejong') }}
    union select admin_dong_code from {{ ref('silver_culture_kcisa_event') }}
    union select admin_dong_code from {{ ref('silver_culture_facility') }}
    union select admin_dong_code from {{ ref('silver_culture_space') }}
),

canon as (select admin_dong_code from {{ ref('asac_axes', 'dim_admin_dong') }})

select s.admin_dong_code
from silver_codes s
where s.admin_dong_code is not null
  and s.admin_dong_code not in (select admin_dong_code from canon)

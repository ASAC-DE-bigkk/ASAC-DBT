-- dim: 서울 주요 121장소 정적 차원 (#69) — citydata 계열 silver 들의 공통축 조인원.
--
-- seed(seoul_ppltn_area_geo) 좌표를 공용 경계 seed(asac_axes)에 point-in-polygon 해
-- 행정구역(#48 공통축: gu/admin_dong + 행안부 코드)을 1회 계산해 둔다. silver 마다
-- ST_Contains 를 반복하지 않기 위한 테이블. 121행 고정이라 table 재생성이 가장 싸고 멱등.

{{ config(materialized='table', on_table_exists='drop', schema=env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata")) }}

with admin as (
    select area_cd, gu, admin_dong, gu_code, admin_dong_code
    from (
        select
            g.area_cd,
            b.sigungu as gu,
            b.dong as admin_dong,
            b.gu_code,
            b.admin_dong_code,
            row_number() over (partition by g.area_cd order by b.admin_dong_code) as rn
        from {{ ref('seoul_ppltn_area_geo') }} g
        left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} b
            on {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'g.center_lon', 'g.center_lat') }}
    )
    where rn = 1
)

select
    g.area_cd,
    g.area_nm,
    g.category as area_category,
    '서울특별시' as sido,
    a.gu,
    a.admin_dong,
    a.gu_code,
    a.admin_dong_code,
    g.center_lon as longitude,
    g.center_lat as latitude
from {{ ref('seoul_ppltn_area_geo') }} g
left join admin a on g.area_cd = a.area_cd

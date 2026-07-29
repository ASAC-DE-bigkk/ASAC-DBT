-- dim: 서울 주요 121장소 정적 차원 (#69/#115) — citydata silver 들의 공통축 조인원.
--
-- 공간축 구성(3조각):
--  ① 좌표: seed(seoul_hotspot_area_geo)의 중심 위경도.
--  ② 동 판정: 중심점을 공용 경계 seed(asac_axes.seoul_admin_dong_boundary)에
--     **point-in-polygon** → 어느 행정동인지(이름).
--  ③ 행안부 코드: 그 동 이름으로 **라이브 마스터(asac_axes.dim_admin_dong, #154 행안부
--     @weekly)** 를 조인 → 최신 admin_dong_code·gu_code. 재편으로 코드가 바뀌어도 이름이
--     같으면 자동 반영(B). 이름 미매칭 시 경계 seed 의 baked 코드로 폴백(안전).
--
-- 121행 고정이라 table 재생성이 가장 싸고 멱등.

{{ config(materialized='table', on_table_exists='drop', schema=env_var("SEOUL_CITYDATA_SCHEMA", target.schema)) }}

with area_dong as (
    -- ② 각 POI 중심점 → 경계 point-in-polygon 으로 행정동(이름) 판정.
    -- 코드가 아니라 이름을 얻는다(라이브 코드는 ③에서 이름으로 붙임). baked 코드는 폴백용.
    select area_cd, gu, admin_dong, baked_admin_dong_code, baked_gu_code
    from (
        select
            g.area_cd,
            b.sigungu as gu,
            b.dong as admin_dong,
            b.admin_dong_code as baked_admin_dong_code,
            b.gu_code as baked_gu_code,
            row_number() over (partition by g.area_cd order by b.dong) as rn
        from {{ ref('seoul_hotspot_area_geo') }} g
        left join {{ ref('asac_axes', 'seoul_admin_dong_boundary') }} b
            on {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'g.center_lon', 'g.center_lat') }}
    )
    where rn = 1
),

live as (
    -- ③ 동 이름으로 행안부 라이브 마스터 조인 → 최신 코드. 미매칭이면 baked 폴백.
    select
        ad.area_cd,
        coalesce(m.admin_dong_code, ad.baked_admin_dong_code) as admin_dong_code,
        coalesce(m.gu_code, ad.baked_gu_code) as gu_code
    from area_dong ad
    left join {{ ref('asac_axes', 'dim_admin_dong') }} m
        on ad.gu = m.gu and ad.admin_dong = m.admin_dong
)

select
    g.area_cd,
    g.area_nm,
    g.category as area_category,
    '서울특별시' as sido,
    ad.gu,
    ad.admin_dong,
    l.gu_code,
    l.admin_dong_code,
    g.center_lon as longitude,
    g.center_lat as latitude
from {{ ref('seoul_hotspot_area_geo') }} g
left join area_dong ad on g.area_cd = ad.area_cd
left join live l on g.area_cd = l.area_cd

{# dim_admin_dong.sql과 같은 조인을 재구성하되 seoul_admin_dong_crosswalk만
   FOR VERSION AS OF로 고정한다. dim_admin_dong 자체를 고치지 않는 이유: view라서
   snapshot을 박으면 그 순간에 굳어버려 평상시 용도로 못 쓴다(ASAC-DAG #480 설계
   docs/superpowers/specs/2026-07-23-shared-admin-dong-axis-version-pin-design.md).
   dim_admin_dong.sql이 바뀌면 이 매크로도 같이 갱신해야 한다. #}
{% macro pinned_dim_admin_dong() %}
{%- set snapshot_id = var('admin_dong_crosswalk_pin_snapshot_id', none) -%}
{%- if snapshot_id is none -%}
  {{ exceptions.raise_compiler_error(
      "pinned_dim_admin_dong() requires var('admin_dong_crosswalk_pin_snapshot_id')"
  ) }}
{%- endif -%}
{%- set snapshot_id_int = snapshot_id | int(-1) -%}
{%- if snapshot_id_int <= 0 or (snapshot_id_int | string) != (snapshot_id | string) -%}
  {{ exceptions.raise_compiler_error(
      "admin_dong_crosswalk_pin_snapshot_id must be a positive integer, got: " ~ snapshot_id
  ) }}
{%- endif -%}
(
    with latest as (
        select max(revision_date) as revision_date
        from {{ source('axes_bronze', 'admin_dong_master') }}
    ),
    dong as (
        select distinct
            admin_dong_code,
            admin_dong_nm as admin_dong,
            substr(admin_dong_code, 1, 5) as gu_code,
            sgg_nm as gu,
            stat_region_cd,
            revision_date
        from {{ source('axes_bronze', 'admin_dong_master') }}
        where sido_nm = '서울특별시'
          and revision_date = (select revision_date from latest)
          and substr(admin_dong_code, 6, 5) <> '00000'
    ),
    crosswalk as (
        select
            admin_dong_code,
            latitude,
            longitude
        from {{ ref('seoul_admin_dong_crosswalk') }} FOR VERSION AS OF {{ snapshot_id_int }}
    )
    select
        d.admin_dong_code,
        d.admin_dong,
        d.gu_code,
        d.gu,
        d.stat_region_cd,
        d.revision_date,
        x.latitude,
        x.longitude
    from dong d
    left join crosswalk x
        on d.admin_dong_code = x.admin_dong_code
)
{% endmacro %}

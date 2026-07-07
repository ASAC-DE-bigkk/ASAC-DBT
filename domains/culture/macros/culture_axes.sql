{#
  culture_axes.sql — culture silver 공통 조각 3종.
  - lineage: #48 컬럼 사전(계보) — 모든 _at 은 KST.
  - dedup 정렬: 관측일(load_date) 우선 — proxy/백필의 ingest_ts 역전이
    최신 관측을 가리지 않게(설계 §3-A). raw_object_key 는 결정적 tie-breaker.
  - dong_map: 좌표 → 행정동 point-in-polygon. 고유 좌표만 연산(비용),
    다중 매치는 admin_dong_code 최소값(결정적).
#}

{% macro culture_lineage(source_system) -%}
    '{{ source_system }}' as source_system,
    run_id as dag_run_id,
    raw_object_key,
    {{ asac_axes.utc_to_kst('collected_at') }} as collected_at,
    {{ asac_axes.utc_to_kst("try(cast(date_parse(ingest_ts, '%Y%m%dT%H%i%sZ') as timestamp(6)))") }} as ingested_at,
    load_date
{%- endmacro %}

{% macro culture_dedup_order() -%}
load_date desc, ingest_ts desc, raw_object_key desc
{%- endmacro %}

{% macro culture_dong_map(src) -%}
(
    select
        c.longitude,
        c.latitude,
        min(b.admin_dong_code)               as admin_dong_code,
        min_by(b.dong, b.admin_dong_code)    as admin_dong,
        min_by(b.gu_code, b.admin_dong_code) as coord_gu_code
    from (
        select distinct longitude, latitude
        from {{ src }}
        where longitude is not null and latitude is not null
    ) c
    join {{ ref('seoul_admin_dong_boundary') }} b
      on {{ asac_axes.admin_dong_contains('b.boundary_wkt', 'c.longitude', 'c.latitude') }}
    group by c.longitude, c.latitude
)
{%- endmacro %}

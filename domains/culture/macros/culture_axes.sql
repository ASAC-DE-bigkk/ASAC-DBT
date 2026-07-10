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

{#
  norm_title — 소스 간 제목 표기 차이(공백·괄호 부가어·대소문자)를 무력화한
  dedup 매칭 키(#85). silver_culture_kcisa_event 와 assert_kcisa_no_cross_duplicate 가 공유.
#}
{% macro culture_norm_title(expr) -%}
lower(regexp_replace({{ expr }}, '\s|\[.*?\]|\(.*?\)', ''))
{%- endmacro %}

{#
  culture_admin_canon — bronze 행정동 canonical(dim_admin_dong) stamp용 두 CTE(#48).
  - canon    : admin_dong_code 로 조인(좌표→행정동 결과에 canonical 코드·명칭 stamp)
  - canon_gu : gu 라벨로 조인(좌표 없는 행 gu_code 폴백 — facility 커버리지 방어)
  `with ... , {{ culture_admin_canon() }}` 형태로 선행 CTE 뒤에 배치.
#}
{% macro culture_admin_canon() -%}
canon as (
    select admin_dong_code, gu_code, admin_dong
    from {{ ref('asac_axes', 'dim_admin_dong') }}
),
canon_gu as (
    select distinct gu, gu_code
    from {{ ref('asac_axes', 'dim_admin_dong') }}
)
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

{#
  culture_admin_stamp — dong_map + culture_admin_canon 결과를 최종 select 에 stamp 하는
  공통 꼬리(#48). 공간 silver 8개가 바이트 동일하게 복붙하던 컬럼 3개 + 조인 3개를
  단일화한다. canon/canon_gu 별칭(cd/cg)은 culture_admin_canon 이 만든 CTE 이름에 고정.
  - _cols(dong)         : 최종 select 의 gu_code / admin_dong / admin_dong_code 3컬럼
  - _joins(driver, dong): dong_map·canon·canon_gu 세 left join
  ``driver`` = 최종 select 가 읽는 CTE 별칭(latest l / placed p / joined j / deduped d 등),
  ``dong``   = dong_map 별칭(대개 'd', 드라이버가 'd'인 경우 'm').
#}
{% macro culture_admin_stamp_cols(dong='d') -%}
coalesce(cd.gu_code, cg.gu_code, {{ dong }}.coord_gu_code) as gu_code,
    coalesce(cd.admin_dong, {{ dong }}.admin_dong) as admin_dong,
    {{ dong }}.admin_dong_code
{%- endmacro %}

{% macro culture_admin_stamp_joins(driver, dong='d') -%}
left join dong_map {{ dong }} on {{ driver }}.longitude = {{ dong }}.longitude and {{ driver }}.latitude = {{ dong }}.latitude
left join canon cd on cd.admin_dong_code = {{ dong }}.admin_dong_code
left join canon_gu cg on cg.gu = {{ driver }}.gu
{%- endmacro %}

{#
  culture_quality_status — 공간축 정밀도 3치 표식(#111). 최종 컬럼 null 여부로 순수 파생.
  - dong_precise : admin_dong_code 있음(좌표 point-in-polygon 성공, 행정동까지)
  - gu_only      : admin_dong_code 없고 gu_code 있음(좌표 없어 구 레벨 근사)
  - unmatched    : 둘 다 없음(구도 미확정)
  stamped CTE 뒤에서 표준 컬럼명으로 무인자 호출. #48 오배정 계측과 같은 "계측 전용" 철학.
#}
{% macro culture_quality_status(dong_col='admin_dong_code', gu_col='gu_code') -%}
case
    when {{ dong_col }} is not null then 'dong_precise'
    when {{ gu_col }}   is not null then 'gu_only'
    else                                'unmatched'
end
{%- endmacro %}

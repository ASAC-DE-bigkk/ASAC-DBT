{#
  generate_schema_name 오버라이드 — custom schema 를 **접두사 없이 그대로** 쓴다.

  dbt 기본값은 `<target.schema>_<custom>` 으로 접두사를 붙여(예: seoul_ppltn_citydata)
  스키마를 격리한다. 이 프로젝트는 도메인 스키마명을 명시적으로 관리하므로
  (population=seoul_ppltn, citydata=seoul_citydata), custom schema 가 있으면 그대로 쓴다.

  - config(schema=...) 없는 모델(population 계열) → target.schema (seoul_ppltn) 유지
  - config(schema='seoul_citydata') 인 citydata 모델 → seoul_citydata 로 그대로
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}

{#-
  단위 제외 필터 — dbt_project.yml vars(exclude_*) 목록에 있으면 해당 행을 silver 에서 제외.
  incremental history/full-refresh 백필 입력에서 "특정 dataset/일자/run 삭제·복원"을
  설정 변경만으로 구현한다. 정책·절차: docs/rebuild-and-ops.md
  값은 운영자가 관리하는 설정(외부 입력 아님). 목록이 비면 필터를 생성하지 않는다.
-#}
{% macro not_in_excluded(column, var_name) -%}
{%- set values = var(var_name, []) -%}
{%- if values %}
        and {{ column }} not in ({% for v in values %}'{{ v }}'{% if not loop.last %}, {% endif %}{% endfor %})
{%- endif -%}
{%- endmacro %}

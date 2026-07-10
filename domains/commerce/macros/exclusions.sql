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


{#-
  단위 선택(화이트리스트) — **청크(부분) 백필**용. include_datasets 목록이 있으면 그 dataset 만
  처리한다. 대용량을 한 번에 로드하면 Trino window 연산이 노드 메모리를 초과(OOM)하므로, 전체
  백필을 dataset 배치로 쪼개 순차 적재한다(각 배치=별도 dataset 이라 서로 격리 — 마킹 불필요).
  절차: docs/rebuild-and-ops.md §6. 목록이 비면 필터 없음(=평상시 증분/전체 동작 불변).
-#}
{% macro in_included(column, var_name='include_datasets') -%}
{%- set values = var(var_name, []) -%}
{%- if values %}
        and {{ column }} in ({% for v in values %}'{{ v }}'{% if not loop.last %}, {% endif %}{% endfor %})
{%- endif -%}
{%- endmacro %}

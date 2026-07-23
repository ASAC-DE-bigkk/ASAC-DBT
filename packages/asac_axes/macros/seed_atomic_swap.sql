{# asac_axes 소유 seed(seoul_admin_dong_crosswalk 등)를 Trino/Iceberg에서 원자적으로
   교체한다. dbt-core 기본 seed materialization은 DROP -> CREATE(빈 테이블) -> INSERT를
   별도 statement로 실행해, 재시딩 도중 "테이블 없음"과 "테이블은 있지만 비어있음" 두
   노출 창을 만든다(ASAC-DAG #480). 여기서는 dbt-trino의 table materialization이 이미
   쓰는 intermediate-build + rename swap 패턴을 그대로 이식해 두 창을 모두 없앤다. #}

{% macro _asac_axes_create_csv_table_as(relation, agate_table, model) %}
  {%- set column_override = model['config'].get('column_types', {}) -%}
  {%- set quote_seed_column = model['config'].get('quote_columns', None) -%}
  {% set sql %}
    create table {{ relation.render() }} (
        {%- for col_name in agate_table.column_names -%}
            {%- set inferred_type = adapter.convert_type(agate_table, loop.index0) -%}
            {%- set type = column_override.get(col_name, inferred_type) -%}
            {%- set column_name = (col_name | string) -%}
            {{ adapter.quote_seed_column(column_name, quote_seed_column) }} {{ type }} {%- if not loop.last -%}, {%- endif -%}
        {%- endfor -%}
    )
  {% endset %}
  {% call statement('_') -%}
    {{ sql }}
  {%- endcall %}
{% endmacro %}


{% macro _asac_axes_load_csv_rows_into(relation, agate_table, model) %}
  {%- set batch_size = get_batch_size() -%}
  {%- set cols_sql = get_seed_column_quoted_csv(model, agate_table.column_names) -%}
  {%- for chunk in agate_table.rows | batch(batch_size) -%}
    {%- set bindings = [] -%}
    {%- for row in chunk -%}
      {%- do bindings.extend(row) -%}
    {%- endfor -%}
    {% set sql %}
        insert into {{ relation.render() }} ({{ cols_sql }}) values
        {% for row in chunk -%}
            ({%- for column in agate_table.column_names -%}
                {{ get_binding_char() }}
                {%- if not loop.last%},{%- endif %}
            {%- endfor -%})
            {%- if not loop.last%},{%- endif %}
        {%- endfor %}
    {% endset %}
    {% do adapter.add_query(sql, bindings=bindings, abridge_sql_log=True) %}
  {%- endfor -%}
{% endmacro %}


{% materialization seed, adapter='trino' %}
  {%- set identifier = model['alias'] -%}
  {%- set full_refresh_mode = (should_full_refresh()) -%}
  {%- set old_relation = adapter.get_relation(database=database, schema=schema, identifier=identifier) -%}
  {%- set exists_as_table = (old_relation is not none and old_relation.is_table) -%}
  {%- set exists_as_view = (old_relation is not none and old_relation.is_view) -%}
  {%- set grant_config = config.get('grants') -%}
  {%- set agate_table = load_agate_table() -%}
  {%- do store_result('agate_table', response='OK', agate_table=agate_table) -%}

  {{ run_hooks(pre_hooks, inside_transaction=False) }}
  {{ run_hooks(pre_hooks, inside_transaction=True) }}

  {%- if exists_as_view -%}
    {{ exceptions.raise_compiler_error("Cannot seed to '{}', it is a view".format(old_relation.render())) }}
  {%- endif -%}

  {%- if not full_refresh_mode and exists_as_table -%}
    {# incremental seed load(--full-refresh 없이): 교체 대상이 아니라 in-place
       truncate+insert만 하면 되므로 swap이 필요 없다. #}
    {% call statement('main', 'INSERT', agate_table.rows | length) %}
      select 1
    {% endcall %}
    {{ adapter.truncate_relation(old_relation) }}
    {{ _asac_axes_load_csv_rows_into(old_relation, agate_table, model) }}
    {%- set target_relation = old_relation -%}
  {%- else -%}
    {# full-refresh(평소 dbt seed 경로): intermediate relation에 새 데이터를 전부
       채운 뒤 rename으로 교체한다. #}
    {%- set target_relation = this.incorporate(type='table') -%}
    {%- set intermediate_relation = make_intermediate_relation(target_relation) -%}
    {%- set backup_relation_type = 'table' if old_relation is none else old_relation.type -%}
    {%- set backup_relation = make_backup_relation(target_relation, backup_relation_type) -%}
    {{ drop_relation_if_exists(load_cached_relation(intermediate_relation)) }}
    {{ drop_relation_if_exists(load_cached_relation(backup_relation)) }}

    {% call statement('main', 'CREATE', agate_table.rows | length) %}
      select 1
    {% endcall %}
    {{ _asac_axes_create_csv_table_as(intermediate_relation, agate_table, model) }}
    {%- if (agate_table.rows | length) > 0 -%}
      {{ _asac_axes_load_csv_rows_into(intermediate_relation, agate_table, model) }}
    {%- endif -%}

    {%- if old_relation is not none -%}
      {{ adapter.rename_relation(old_relation, backup_relation) }}
    {%- endif -%}
    {{ adapter.rename_relation(intermediate_relation, target_relation) }}
    {{ drop_relation_if_exists(backup_relation) }}
  {%- endif -%}

  {%- set should_revoke = should_revoke(old_relation, full_refresh_mode) -%}
  {% do apply_grants(target_relation, grant_config, should_revoke=should_revoke) %}
  {% do persist_docs(target_relation, model) %}
  {%- if full_refresh_mode or not exists_as_table -%}
    {% do create_indexes(target_relation) %}
  {%- endif -%}

  {{ run_hooks(post_hooks, inside_transaction=True) }}
  {{ adapter.commit() }}
  {{ run_hooks(post_hooks, inside_transaction=False) }}

  {{ return({'relations': [target_relation]}) }}
{% endmaterialization %}

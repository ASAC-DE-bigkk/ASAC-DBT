{% macro get_incremental_traffic_publishability_reconcile_sql(arg_dict) -%}
  {%- set target_relation = arg_dict['target_relation'] -%}
  {%- set temp_relation = arg_dict['temp_relation'] -%}
  {%- set unique_key = arg_dict['unique_key'] -%}
  {%- set dest_columns = arg_dict['dest_columns'] -%}
  {%- if unique_key != ['source_record_id'] -%}
    {{ exceptions.raise_compiler_error('Traffic publishability reconcile requires source_record_id unique key.') }}
  {%- endif -%}
  {%- set preflight_sql -%}
    with temp_summary as (
      select count_if(source_record_id is null) as null_count,
             count(*) - count(distinct source_record_id) as duplicate_count
      from {{ temp_relation }}
    ), target_summary as (
      select count_if(source_record_id is null) as null_count,
             count(*) - count(distinct source_record_id) as duplicate_count
      from {{ target_relation }}
    )
    select temp_summary.null_count, temp_summary.duplicate_count,
           target_summary.null_count, target_summary.duplicate_count
    from temp_summary cross join target_summary
  {%- endset -%}
  {%- if execute -%}
    {%- set result = run_query(preflight_sql) -%}
    {%- set row = result.rows[0] -%}
    {%- if row[0] | int != 0 or row[1] | int != 0 or row[2] | int != 0 or row[3] | int != 0 -%}
      {{ exceptions.raise_compiler_error('Traffic publishability reconcile preflight failed: null or duplicate source_record_id.') }}
    {%- endif -%}
  {%- endif -%}

  {%- set dest_cols_csv = get_quoted_csv(dest_columns | map(attribute='name')) -%}
  {%- set update_columns = get_merge_update_columns(
      config.get('merge_update_columns'),
      config.get('merge_exclude_columns'),
      dest_columns
  ) -%}
merge into {{ target_relation }} as DBT_INTERNAL_DEST
using (
  with DBT_INTERNAL_LATEST_MANIFEST_STATE as (
    {{ latest_manifest_run_state('traffic_bronze', 'collection_run_manifest', 'seoul_traffic_incident') }}
  ),
  DBT_INTERNAL_PUBLISHABLE_UPSERT_ROWS as (
    select DBT_INTERNAL_UPSERT.*
    from {{ temp_relation }} as DBT_INTERNAL_UPSERT
    inner join DBT_INTERNAL_LATEST_MANIFEST_STATE as DBT_INTERNAL_MANIFEST
      on cast(DBT_INTERNAL_UPSERT.dag_run_id as varchar)
           = cast(DBT_INTERNAL_MANIFEST.dag_run_id as varchar)
     and DBT_INTERNAL_MANIFEST.manifest_status = 'SUCCESS'
     and coalesce(DBT_INTERNAL_MANIFEST.is_publishable, false)
  ),
  DBT_INTERNAL_STALE_KEYS as (
    select DBT_INTERNAL_DEST.source_record_id
    from {{ target_relation }} as DBT_INTERNAL_DEST
    left join DBT_INTERNAL_LATEST_MANIFEST_STATE as DBT_INTERNAL_MANIFEST
      on cast(DBT_INTERNAL_DEST.dag_run_id as varchar)
           = cast(DBT_INTERNAL_MANIFEST.dag_run_id as varchar)
    where (
      DBT_INTERNAL_MANIFEST.dag_run_id is null
      or DBT_INTERNAL_MANIFEST.manifest_status <> 'SUCCESS'
      or not coalesce(DBT_INTERNAL_MANIFEST.is_publishable, false)
    )
      and not exists (
        select 1
        from DBT_INTERNAL_PUBLISHABLE_UPSERT_ROWS as DBT_INTERNAL_UPSERT
        where DBT_INTERNAL_UPSERT.source_record_id
              = DBT_INTERNAL_DEST.source_record_id
      )
  ),
  DBT_INTERNAL_UPSERT_SOURCE as (
    select
      {% for column in dest_columns -%}
      DBT_INTERNAL_UPSERT.{{ column.quoted }} as {{ column.quoted }},
      {% endfor -%}
      false as __traffic_delete
    from DBT_INTERNAL_PUBLISHABLE_UPSERT_ROWS as DBT_INTERNAL_UPSERT
  ),
  DBT_INTERNAL_DELETE_SOURCE as (
    select
      {% for column in dest_columns -%}
      {% if column.name | lower == 'source_record_id' -%}
      DBT_INTERNAL_STALE.source_record_id as {{ column.quoted }},
      {% else -%}
      cast(null as {{ column.data_type }}) as {{ column.quoted }},
      {% endif -%}
      {% endfor -%}
      true as __traffic_delete
    from DBT_INTERNAL_STALE_KEYS as DBT_INTERNAL_STALE
  )
  select * from DBT_INTERNAL_UPSERT_SOURCE
  union all
  select * from DBT_INTERNAL_DELETE_SOURCE
) as DBT_INTERNAL_SOURCE
on DBT_INTERNAL_SOURCE.source_record_id = DBT_INTERNAL_DEST.source_record_id
when matched and DBT_INTERNAL_SOURCE.__traffic_delete then delete
when matched and not DBT_INTERNAL_SOURCE.__traffic_delete
  and (
    {% for column_name in update_columns -%}
    DBT_INTERNAL_DEST.{{ column_name }}
      is distinct from DBT_INTERNAL_SOURCE.{{ column_name }}
    {% if not loop.last %}or{% endif %}
    {% endfor -%}
  )
then update set
  {% for column_name in update_columns -%}
  {{ column_name }} = DBT_INTERNAL_SOURCE.{{ column_name }}
  {% if not loop.last %},{% endif %}
  {% endfor -%}
when not matched and not DBT_INTERNAL_SOURCE.__traffic_delete then insert (
  {{ dest_cols_csv }}
) values (
  {% for column in dest_columns -%}
  DBT_INTERNAL_SOURCE.{{ column.quoted }}{% if not loop.last %},{% endif %}
  {% endfor -%}
)
{%- endmacro %}

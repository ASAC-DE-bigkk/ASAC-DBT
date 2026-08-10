{% macro traffic_flow_snapshot_dag_run_id_sql_literal() -%}
  {%- set flow_snapshot_dag_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' -%}
  '{{ flow_snapshot_dag_run_id | replace("'", "''") }}'
{%- endmacro %}

{% macro traffic_flow_changed_rows() -%}
  {%- set flow_snapshot_dag_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' -%}
  select
      cast(request_id as varchar) as request_id,
      cast(source_id as varchar) as source_id,
      cast(request_params_json as varchar) as request_params_json,
      cast(link_id as varchar) as link_id,
      cast(parent_incident_run_id as varchar) as parent_incident_run_id,
      cast(flow_speed as double) as flow_speed,
      cast(flow_travel_time as double) as flow_travel_time,
      cast(flow_value_quality as varchar) as flow_value_quality,
      cast(observed_at as timestamp(6)) as observed_at,
      cast(raw_object_key as varchar) as raw_object_key,
      cast(payload_hash as varchar) as payload_hash,
      cast(collected_at as timestamp(6)) as collected_at,
      cast(dag_run_id as varchar) as dag_run_id
  from {{ ref('silver_seoul_traffic_flow') }}
  {%- if is_incremental() %}
    {%- if flow_snapshot_dag_run_id == '' %}
  where 1 = 0
    {%- else %}
  where cast(dag_run_id as varchar) = {{ traffic_flow_snapshot_dag_run_id_sql_literal() }}
    {%- endif %}
  {%- endif %}
{%- endmacro %}

{% macro traffic_flow_changed_links() -%}
  select distinct link_id
  from ({{ traffic_flow_changed_rows() }}) as changed_rows
  where link_id is not null
    and trim(link_id) <> ''
{%- endmacro %}

{% macro traffic_flow_changed_hours() -%}
  select distinct
      cast(date_trunc('hour', {{ asac_axes.utc_to_kst('observed_at') }}) as timestamp(6)) as hour_at
  from ({{ traffic_flow_changed_rows() }}) as changed_rows
  where observed_at is not null
{%- endmacro %}

{% macro traffic_flow_changed_profile_keys() -%}
  select distinct
      link_id,
      day_of_week(cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6))) as kst_day_of_week,
      hour(cast({{ asac_axes.utc_to_kst('observed_at') }} as timestamp(6))) as kst_hour
  from ({{ traffic_flow_changed_rows() }}) as changed_rows
  where link_id is not null
    and trim(link_id) <> ''
    and observed_at is not null
{%- endmacro %}

{% macro traffic_flow_assert_pinned_incremental_rows() -%}
  {%- set flow_snapshot_dag_run_id = var('traffic_flow_snapshot_dag_run_id', '') or '' -%}
  {%- if execute and is_incremental() and flow_snapshot_dag_run_id != '' -%}
    {%- set preflight_sql -%}
      select count(*) as pinned_row_count
      from {{ ref('silver_seoul_traffic_flow') }}
      where cast(dag_run_id as varchar) = {{ traffic_flow_snapshot_dag_run_id_sql_literal() }}
    {%- endset -%}
    {%- set result = run_query(preflight_sql) -%}
    {%- set row = result.rows[0] -%}
    {%- if row[0] | int == 0 -%}
      {{ exceptions.raise_compiler_error(
          'no silver_seoul_traffic_flow rows for pinned traffic_flow_snapshot_dag_run_id'
      ) }}
    {%- endif -%}
  {%- endif -%}
  {{ return('') }}
{%- endmacro %}

{% macro traffic_citydata_crowding_snapshot_id() -%}
  {%- set snapshot_id = var('traffic_citydata_crowding_snapshot_id', none) -%}
  {%- if snapshot_id is none and not execute -%}
    {{ return(0) }}
  {%- endif -%}
  {%- if snapshot_id is not integer or snapshot_id <= 0 -%}
    {{ exceptions.raise_compiler_error(
      'Traffic Citydata crowding source requires a positive traffic_citydata_crowding_snapshot_id.'
    ) }}
  {%- endif -%}
  {{ return(snapshot_id) }}
{%- endmacro %}

{% macro traffic_citydata_crowding_source_at_snapshot() -%}
  {%- set relation = source('traffic_citydata_gold', 'gold_citydata_ppltn_by_time') -%}
  {%- set snapshot_id = traffic_citydata_crowding_snapshot_id() -%}
  {{ return(relation ~ ' FOR VERSION AS OF ' ~ snapshot_id) }}
{%- endmacro %}

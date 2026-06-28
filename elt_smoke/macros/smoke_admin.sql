{% macro prepare_smoke_schema() %}
    {% set qualified_schema = target.database ~ "." ~ target.schema %}
    {% do run_query("CREATE SCHEMA IF NOT EXISTS " ~ qualified_schema) %}
{% endmacro %}

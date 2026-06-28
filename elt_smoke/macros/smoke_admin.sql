{% macro prepare_smoke_schema() %}
    {% set qualified_schema = target.database ~ "." ~ target.schema %}
    {% do run_query("CREATE SCHEMA IF NOT EXISTS " ~ qualified_schema) %}
{% endmacro %}

{% macro cleanup_smoke() %}
    {% set qualified_schema = target.database ~ "." ~ target.schema %}
    {% for table_name in ["smoke_event_counts", "sample_events"] %}
        {% do run_query("DROP TABLE IF EXISTS " ~ qualified_schema ~ "." ~ table_name) %}
    {% endfor %}
{% endmacro %}

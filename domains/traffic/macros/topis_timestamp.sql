{% macro topis_timestamp(date_col, time_col) -%}
case
    when regexp_like({{ date_col }}, '^[0-9]{8}$')
        and regexp_like({{ time_col }}, '^[0-9]{4}$')
        then cast(date_parse(concat({{ date_col }}, {{ time_col }}, '00'), '%Y%m%d%H%i%s') as timestamp(6))
    when regexp_like({{ date_col }}, '^[0-9]{8}$')
        and regexp_like({{ time_col }}, '^[0-9]{6}$')
        then cast(date_parse(concat({{ date_col }}, {{ time_col }}), '%Y%m%d%H%i%s') as timestamp(6))
end
{%- endmacro %}

{#-
  silver DONE marker helpers.

  Airflow `commerce_load_silver` creates and updates `silver_load_run_marker`.
  dbt history reads only DONE markers as the durable completion signal. This is
  intentionally separate from rows in `silver_license_history`: a run is marked
  DONE only after `dbt test` succeeds.
-#}

{% macro silver_run_marker_relation() -%}
{{ target.database }}.{{ target.schema }}.silver_load_run_marker
{%- endmacro %}

{% macro silver_unmarked_publishable_predicate(alias='b') -%}
not exists (
    select 1
    from {{ silver_run_marker_relation() }} as silver_marker
    where silver_marker.status = 'DONE'
      and cast(silver_marker.dataset as varchar) = cast({{ alias }}.dataset as varchar)
      and cast(silver_marker.bronze_run_id as varchar) = cast({{ alias }}.bronze_run_id as varchar)
)
{%- endmacro %}

{% macro delete_unmarked_silver_history_runs() -%}
{% if is_incremental() %}
delete from {{ this }}
where exists (
    select 1
    from (
        select distinct
            cast(b.dataset as varchar) as dataset,
            cast(b.bronze_run_id as varchar) as bronze_run_id
        from {{ source('commerce_bronze', 'localdata_license') }} as b
        inner join {{ source('commerce_bronze', 'collection_run_manifest') }} as m
            on cast(b.dataset as varchar) = cast(m.dataset as varchar)
            and cast(b.bronze_run_id as varchar) = cast(m.bronze_run_id as varchar)
            and m.status = 'SUCCESS'
            and m.is_publishable
        where 1 = 1
            {{ not_in_excluded("cast(b.dataset as varchar)", 'exclude_datasets') }}
            {{ in_included("cast(b.dataset as varchar)", 'include_datasets') }}
            {{ not_in_excluded("cast(b.observed_date as varchar)", 'exclude_observed_dates') }}
            {{ not_in_excluded("cast(b.load_date as varchar)", 'exclude_load_dates') }}
            {{ not_in_excluded("cast(b.bronze_run_id as varchar)", 'exclude_bronze_run_ids') }}
            and {{ silver_unmarked_publishable_predicate('b') }}
    ) as candidate
    where candidate.dataset = cast({{ this }}.dataset as varchar)
      and candidate.bronze_run_id = cast({{ this }}.bronze_run_id as varchar)
)
{% else %}
select 1
{% endif %}
{%- endmacro %}

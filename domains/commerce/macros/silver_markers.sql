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
{#- seed 서브청크(content_bucket/key_bucket) 중에는 삭제 스킵 — 버킷은 disjoint(content_bucket=history,
    key_bucket=current)이고 빈 테이블에서 시작하므로 삭제 대상이 없다(run 단위 삭제는 앞 버킷을 지운다).
    실패 시 테이블 drop 후 재빌드로 복구. -#}
{% if is_incremental() and not var('content_bucket', none) and not var('key_bucket', none) %}
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

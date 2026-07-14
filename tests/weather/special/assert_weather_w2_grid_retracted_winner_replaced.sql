-- depends_on: {{ ref('silver_kma_vilage_fcst_grid') }}

{% if weather_w2_is_repair() %}
with eligible_manifest_anchors(anchor_source_id, anchor_dag_run_id) as (
    values ('kma_vilage_fcst', 'eligible_run')
),

candidate as (
    select
        60 as nx,
        127 as ny,
        timestamp '2026-07-13 02:00:00.000000' as issued_at,
        timestamp '2026-07-13 03:00:00.000000' as forecast_at,
        cast('TMP' as varchar) as category,
        timestamp '2026-07-13 14:00:00.000000' as collected_at,
        cast('raw/eligible.json' as varchar) as raw_object_key,
        cast('request-eligible' as varchar) as request_id,
        cast('eligible_run' as varchar) as selected_dag_run_id,
        1 as selected_page_no,
        cast('item-eligible' as varchar) as selected_source_item_key
),

current_retracted as (
    select
        candidate.nx,
        candidate.ny,
        candidate.issued_at,
        candidate.forecast_at,
        candidate.category,
        timestamp '2026-07-13 14:30:00.000000' as collected_at,
        cast('raw/retracted.json' as varchar) as raw_object_key,
        cast('request-retracted' as varchar) as request_id,
        cast('kma_vilage_fcst' as varchar) as source_id,
        cast('retracted_run' as varchar) as selected_dag_run_id,
        1 as selected_page_no,
        cast('item-retracted' as varchar) as selected_source_item_key,
        timestamp '{{ weather_w2_publishable_cutoff_at() }}' as published_at
    from candidate
),

current_eligible as (
    select
        current_retracted.nx,
        current_retracted.ny,
        current_retracted.issued_at,
        current_retracted.forecast_at,
        current_retracted.category,
        current_retracted.collected_at,
        current_retracted.raw_object_key,
        current_retracted.request_id,
        current_retracted.source_id,
        cast('eligible_run' as varchar) as selected_dag_run_id,
        current_retracted.selected_page_no,
        current_retracted.selected_source_item_key,
        current_retracted.published_at
    from current_retracted
),

selected_after_retraction as (
    select candidate.*
    from candidate
    where not exists (
        select 1
        from current_retracted as current
        left join eligible_manifest_anchors as current_anchor
            on current.source_id = current_anchor.anchor_source_id
           and current.selected_dag_run_id = current_anchor.anchor_dag_run_id
        where current.nx = candidate.nx
          and current.ny = candidate.ny
          and current.issued_at = candidate.issued_at
          and current.forecast_at = candidate.forecast_at
          and current.category = candidate.category
          and {{ weather_w2_grid_winner_is_newer('current', 'candidate') }}
          and not (
              current.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
              and current.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
              and current_anchor.anchor_source_id is null
          )
    )
),

selected_against_eligible_current as (
    select candidate.*
    from candidate
    where not exists (
        select 1
        from current_eligible as current
        left join eligible_manifest_anchors as current_anchor
            on current.source_id = current_anchor.anchor_source_id
           and current.selected_dag_run_id = current_anchor.anchor_dag_run_id
        where current.nx = candidate.nx
          and current.ny = candidate.ny
          and current.issued_at = candidate.issued_at
          and current.forecast_at = candidate.forecast_at
          and current.category = candidate.category
          and {{ weather_w2_grid_winner_is_newer('current', 'candidate') }}
          and not (
              current.published_at >= timestamp '{{ weather_w2_repair_start_at() }}'
              and current.published_at <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
              and current_anchor.anchor_source_id is null
          )
    )
)

select cast('retracted newer current blocked the eligible repair candidate' as varchar) as failure_reason
where not exists (select 1 from selected_after_retraction)
union all
select cast('eligible newer current failed no-downgrade protection' as varchar) as failure_reason
where exists (select 1 from selected_against_eligible_current)
{% else %}
select cast(null as varchar) as failure_reason
where false
{% endif %}

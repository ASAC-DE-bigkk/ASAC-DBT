with core_categories(category) as (
    values ('TMP'), ('REH'), ('WSD'), ('POP'), ('SKY'), ('PTY'), ('PCP'), ('SNO')
),

core_summary as (
    select count(*) as core_category_count
    from core_categories
),

mapped_bridge as (
    select distinct
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = 'weather_admin_dong_grid_bridge_v1'
      and canonical_join_eligible = true
      and admin_dong_code is not null
),

bridge_summary as (
    select count(distinct admin_dong_code) as mapped_admin_dong_count
    from mapped_bridge
),

issue_date_counts as (
    select
        cast(grid.issued_at as timestamp(6)) as issued_at,
        date(cast(grid.forecast_at as timestamp(6))) as forecast_date,
        count(distinct cast(grid.forecast_at as timestamp(6))) as forecast_slot_count,
        count(distinct if(
            mapped_bridge.admin_dong_code is not null,
            row(
                cast(grid.forecast_at as timestamp(6)),
                mapped_bridge.admin_dong_code,
                cast(grid.category as varchar)
            ),
            null
        )) as observed_cell_count
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    left join mapped_bridge
        on cast(grid.nx as integer) = mapped_bridge.nx
       and cast(grid.ny as integer) = mapped_bridge.ny
    where grid.category in ('TMP', 'REH', 'WSD', 'POP', 'SKY', 'PTY', 'PCP', 'SNO')
    group by
        cast(grid.issued_at as timestamp(6)),
        date(cast(grid.forecast_at as timestamp(6)))
),

recomputed as (
    select
        issue_date_counts.issued_at,
        issue_date_counts.forecast_date,
        issue_date_counts.forecast_slot_count * bridge_summary.mapped_admin_dong_count * core_summary.core_category_count as expected_cell_count,
        issue_date_counts.observed_cell_count,
        issue_date_counts.forecast_slot_count * bridge_summary.mapped_admin_dong_count * core_summary.core_category_count
            - issue_date_counts.observed_cell_count as missing_cell_count,
        issue_date_counts.forecast_slot_count,
        bridge_summary.mapped_admin_dong_count,
        case
            when issue_date_counts.forecast_slot_count * bridge_summary.mapped_admin_dong_count * core_summary.core_category_count = 0
                then cast(null as double)
            else cast(issue_date_counts.observed_cell_count as double)
                / (issue_date_counts.forecast_slot_count * bridge_summary.mapped_admin_dong_count * core_summary.core_category_count)
        end as issue_cycle_coverage_ratio,
        case
            when bridge_summary.mapped_admin_dong_count <> 426 then 'bridge_contract_mismatch'
            when issue_date_counts.observed_cell_count
                = issue_date_counts.forecast_slot_count * bridge_summary.mapped_admin_dong_count * core_summary.core_category_count
                then 'complete'
            when issue_date_counts.observed_cell_count = 0 then 'missing'
            else 'partial'
        end as issue_cycle_coverage_state
    from issue_date_counts
    cross join bridge_summary
    cross join core_summary
),

missing_context as (
    select
        recomputed.issued_at,
        recomputed.forecast_date,
        'missing_model_row' as failure_reason
    from recomputed
    left join {{ ref('gold_weather_forecast_issue_cycle_coverage_daily') }} as model
        on recomputed.issued_at = model.issued_at
       and recomputed.forecast_date = model.forecast_date
    where model.issued_at is null
),

extra_context as (
    select
        model.issued_at,
        model.forecast_date,
        'extra_model_row' as failure_reason
    from {{ ref('gold_weather_forecast_issue_cycle_coverage_daily') }} as model
    left join recomputed
        on model.issued_at = recomputed.issued_at
       and model.forecast_date = recomputed.forecast_date
    where recomputed.issued_at is null
),

mismatched_counts as (
    select
        model.issued_at,
        model.forecast_date,
        'mismatched_counts' as failure_reason
    from {{ ref('gold_weather_forecast_issue_cycle_coverage_daily') }} as model
    inner join recomputed
        on model.issued_at = recomputed.issued_at
       and model.forecast_date = recomputed.forecast_date
    where model.expected_cell_count <> recomputed.expected_cell_count
       or model.observed_cell_count <> recomputed.observed_cell_count
       or model.missing_cell_count <> recomputed.missing_cell_count
       or model.forecast_slot_count <> recomputed.forecast_slot_count
       or model.mapped_admin_dong_count <> recomputed.mapped_admin_dong_count
       or model.mapped_admin_dong_count <> 426
       or model.issue_cycle_coverage_ratio is distinct from recomputed.issue_cycle_coverage_ratio
       or model.issue_cycle_coverage_state is distinct from recomputed.issue_cycle_coverage_state
)

select * from missing_context
union all
select * from extra_context
union all
select * from mismatched_counts

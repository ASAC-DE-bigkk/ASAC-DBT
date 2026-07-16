with expected_issue_dates as (
    select distinct
        cast(issued_at as timestamp(6)) as issued_at,
        date(cast(forecast_at as timestamp(6))) as forecast_date
    from {{ ref('silver_kma_vilage_fcst_grid') }}
    where category in ('TMP', 'REH', 'WSD', 'POP', 'SKY', 'PTY', 'PCP', 'SNO')
),

missing_context as (
    select
        expected_issue_dates.issued_at,
        expected_issue_dates.forecast_date,
        'missing_model_row' as failure_reason
    from expected_issue_dates
    left join {{ ref('gold_weather_forecast_issue_cycle_coverage_daily') }} as model
        on expected_issue_dates.issued_at = model.issued_at
       and expected_issue_dates.forecast_date = model.forecast_date
    where model.issued_at is null
)

select * from missing_context

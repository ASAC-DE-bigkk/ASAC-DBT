with core_categories(category) as (
    values ('TMP'), ('REH'), ('WSD'), ('POP'), ('SKY'), ('PTY'), ('PCP'), ('SNO')
),

expected_context as (
    select
        anchor.admin_dong_code,
        anchor.forecast_at,
        category
    from (
        select distinct admin_dong_code, forecast_at
        from {{ ref('gold_weather_forecast_by_admin_dong') }}
    ) as anchor
    cross join core_categories
),

recomputed as (
    select
        expected_context.admin_dong_code,
        expected_context.forecast_at,
        count(*) as expected_core_category_count,
        count(observed.category) as observed_core_category_count,
        count(*) - count(observed.category) as missing_core_category_count
    from expected_context
    left join (
        select distinct admin_dong_code, forecast_at, category
        from {{ ref('gold_weather_forecast_by_admin_dong') }}
        where category in ('TMP', 'REH', 'WSD', 'POP', 'SKY', 'PTY', 'PCP', 'SNO')
    ) as observed
        on expected_context.admin_dong_code = observed.admin_dong_code
       and expected_context.forecast_at = observed.forecast_at
       and expected_context.category = observed.category
    group by expected_context.admin_dong_code, expected_context.forecast_at
),

missing_context as (
    select
        recomputed.admin_dong_code,
        recomputed.forecast_at,
        'missing_model_row' as failure_reason
    from recomputed
    left join {{ ref('gold_weather_forecast_completeness_by_admin_dong_hourly') }} as model
        on recomputed.admin_dong_code = model.admin_dong_code
       and recomputed.forecast_at = model.forecast_at
    where model.admin_dong_code is null
),

mismatched_counts as (
    select
        model.admin_dong_code,
        model.forecast_at,
        'mismatched_counts' as failure_reason
    from {{ ref('gold_weather_forecast_completeness_by_admin_dong_hourly') }} as model
    inner join recomputed
        on model.admin_dong_code = recomputed.admin_dong_code
       and model.forecast_at = recomputed.forecast_at
    where model.expected_core_category_count <> recomputed.expected_core_category_count
       or model.observed_core_category_count <> recomputed.observed_core_category_count
       or model.missing_core_category_count <> recomputed.missing_core_category_count
)

select * from missing_context
union all
select * from mismatched_counts

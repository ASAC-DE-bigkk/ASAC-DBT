with core_categories(category) as (
    values
        ('TMP'),
        ('REH'),
        ('WSD'),
        ('POP'),
        ('SKY'),
        ('PTY'),
        ('PCP'),
        ('SNO')
),

weather as (
    select
        admin_dong_code,
        forecast_at,
        category,
        issued_at,
        collected_at,
        published_at
    from {{ ref('gold_weather_forecast_by_admin_dong') }}
),

observed_grains as (
    select distinct
        admin_dong_code,
        forecast_at
    from weather
),

expected as (
    select
        observed_grains.admin_dong_code,
        observed_grains.forecast_at,
        core_categories.category
    from observed_grains
    cross join core_categories
),

observed_core as (
    select distinct
        admin_dong_code,
        forecast_at,
        category
    from weather
    where category in ('TMP', 'REH', 'WSD', 'POP', 'SKY', 'PTY', 'PCP', 'SNO')
),

lineage as (
    select
        admin_dong_code,
        forecast_at,
        min(issued_at) as issued_at_min,
        max(issued_at) as issued_at_max,
        max(collected_at) as weather_collected_at_max,
        max(published_at) as weather_published_at_max
    from weather
    group by admin_dong_code, forecast_at
),

scored as (
    select
        expected.admin_dong_code,
        expected.forecast_at,
        count(*) as expected_core_category_count,
        count(observed_core.category) as observed_core_category_count,
        count(*) - count(observed_core.category) as missing_core_category_count,
        count_if(expected.category = 'TMP' and observed_core.category is not null) > 0 as tmp_present,
        count_if(expected.category = 'REH' and observed_core.category is not null) > 0 as reh_present,
        count_if(expected.category = 'WSD' and observed_core.category is not null) > 0 as wsd_present,
        count_if(expected.category = 'POP' and observed_core.category is not null) > 0 as pop_present,
        count_if(expected.category = 'SKY' and observed_core.category is not null) > 0 as sky_present,
        count_if(expected.category = 'PTY' and observed_core.category is not null) > 0 as pty_present,
        count_if(expected.category = 'PCP' and observed_core.category is not null) > 0 as pcp_present,
        count_if(expected.category = 'SNO' and observed_core.category is not null) > 0 as sno_present
    from expected
    left join observed_core
        on expected.admin_dong_code = observed_core.admin_dong_code
       and expected.forecast_at = observed_core.forecast_at
       and expected.category = observed_core.category
    group by expected.admin_dong_code, expected.forecast_at
)

select
    concat(scored.admin_dong_code, '|', to_iso8601(cast(scored.forecast_at as timestamp(6)))) as product_row_id,
    scored.admin_dong_code,
    scored.forecast_at,
    scored.tmp_present,
    scored.reh_present,
    scored.wsd_present,
    scored.pop_present,
    scored.sky_present,
    scored.pty_present,
    scored.pcp_present,
    scored.sno_present,
    scored.observed_core_category_count,
    scored.expected_core_category_count,
    scored.missing_core_category_count,
    cast(scored.observed_core_category_count as double) / scored.expected_core_category_count as core_category_coverage_ratio,
    case
        when scored.observed_core_category_count = scored.expected_core_category_count then 'complete'
        when scored.observed_core_category_count = 0 then 'missing_core'
        else 'partial'
    end as completeness_state,
    lineage.issued_at_min,
    lineage.issued_at_max,
    lineage.weather_collected_at_max,
    lineage.weather_published_at_max
from scored
inner join lineage
    on scored.admin_dong_code = lineage.admin_dong_code
   and scored.forecast_at = lineage.forecast_at

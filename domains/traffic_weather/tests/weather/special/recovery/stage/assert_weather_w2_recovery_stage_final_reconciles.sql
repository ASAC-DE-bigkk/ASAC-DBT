-- depends_on: {{ ref('weather_w2_observation_recovery_stage') }}

{% set repair_mode = weather_w2_is_repair() %}
{% if repair_mode %}
{% set checkpoint_id = weather_w2_recovery_checkpoint_id() %}
{% set target_admin_dong_code = weather_w2_recovery_target_admin_dong_code() %}

with expected as (
    {{ weather_w2_recovery_expected_rows_sql() }}
),
actual as (
    select *
    from {{ ref('weather_w2_observation_recovery_stage') }}
    where checkpoint_id = '{{ checkpoint_id }}'
),
invalid_actual as (
    select
        product_row_id,
        cast('unexpected_stage_row' as varchar) as failure_reason
    from actual
    where admin_dong_code != '1123053600'
       or admin_dong_code != '{{ target_admin_dong_code }}'
       or nx != 61
       or ny != 127
),
missing_or_different as (
    select
        expected.product_row_id,
        case
            when actual.product_row_id is null
                then 'missing_expected_stage_row'
            else 'stage_payload_differs_from_pinned_winner'
        end as failure_reason
    from expected
    left join actual
        on expected.admin_dong_code = actual.admin_dong_code
       and expected.forecast_at = actual.forecast_at
       and expected.category = actual.category
    where actual.product_row_id is null
       or {{ weather_w2_gold_candidate_row('actual') }}
          is distinct from {{ weather_w2_gold_candidate_row('expected') }}
),
unexpected_actual as (
    select
        actual.product_row_id,
        cast('unexpected_stage_row' as varchar) as failure_reason
    from actual
    left join expected
        on actual.admin_dong_code = expected.admin_dong_code
       and actual.forecast_at = expected.forecast_at
       and actual.category = expected.category
    where expected.product_row_id is null
)
select * from invalid_actual
union all
select * from missing_or_different
union all
select * from unexpected_actual
{% else %}
select
    cast(null as varchar) as product_row_id,
    cast(null as varchar) as failure_reason
where false
{% endif %}

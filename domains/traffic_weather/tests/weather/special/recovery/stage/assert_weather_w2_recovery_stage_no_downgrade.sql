-- depends_on: {{ ref('weather_w2_observation_recovery_stage') }}

{% set repair_mode = weather_w2_is_repair() %}
{% if repair_mode %}
{% set checkpoint_id = weather_w2_recovery_checkpoint_id() %}
{% set target_admin_dong_code = weather_w2_recovery_target_admin_dong_code() %}
{% set winner_bucket_count = var('weather_w2_winner_bucket_count', 8) | int %}
{% set winner_bucket_index = var('weather_w2_winner_bucket_index', 0) | int %}

{% if winner_bucket_count < 1
    or winner_bucket_index < 0
    or winner_bucket_index >= winner_bucket_count %}
  {{ exceptions.raise_compiler_error(
      'Weather W2 staged winner bucket index must be inside bucket count.'
  ) }}
{% endif %}

with expected as (
    {{ weather_w2_recovery_expected_rows_sql() }}
),
bucketed_expected as (
    select *
    from expected
    where {{ weather_w2_canonical_grain_bucket(
        'expected',
        winner_bucket_count
    ) }} = {{ winner_bucket_index }}
),
actual as (
    select *
    from {{ ref('weather_w2_observation_recovery_stage') }}
    where checkpoint_id = '{{ checkpoint_id }}'
      and admin_dong_code = '1123053600'
      and admin_dong_code = '{{ target_admin_dong_code }}'
)
select
    expected.product_row_id,
    cast('missing_or_downgraded_stage_winner' as varchar) as failure_reason
from bucketed_expected as expected
left join actual
    on expected.admin_dong_code = actual.admin_dong_code
   and expected.forecast_at = actual.forecast_at
   and expected.category = actual.category
where actual.product_row_id is null
   or not {{ weather_w2_gold_winner_is_not_older('actual', 'expected') }}
{% else %}
select
    cast(null as varchar) as product_row_id,
    cast(null as varchar) as failure_reason
where false
{% endif %}

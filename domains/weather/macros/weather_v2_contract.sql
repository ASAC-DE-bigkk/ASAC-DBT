{# W1 내부 모델 공통 계약: source item identity, bounded lookback, initial-build guard. #}

{% macro weather_kma_item_key_version() -%}
'weather_kma_item_v1'
{%- endmacro %}

{% macro weather_kma_item_signature(base_date, base_time, nx, ny, category, fcst_date, fcst_time, fcst_value) -%}
{%- set tagged = [
    "case when " ~ base_date ~ " is null then 'N:<NULL>' else concat('V:', trim(cast(" ~ base_date ~ " as varchar))) end",
    "case when " ~ base_time ~ " is null then 'N:<NULL>' else concat('V:', trim(cast(" ~ base_time ~ " as varchar))) end",
    "case when " ~ nx ~ " is null then 'N:<NULL>' else concat('V:', coalesce(cast(try_cast(" ~ nx ~ " as integer) as varchar), trim(cast(" ~ nx ~ " as varchar)))) end",
    "case when " ~ ny ~ " is null then 'N:<NULL>' else concat('V:', coalesce(cast(try_cast(" ~ ny ~ " as integer) as varchar), trim(cast(" ~ ny ~ " as varchar)))) end",
    "case when " ~ category ~ " is null then 'N:<NULL>' else concat('V:', upper(trim(cast(" ~ category ~ " as varchar)))) end",
    "case when " ~ fcst_date ~ " is null then 'N:<NULL>' else concat('V:', trim(cast(" ~ fcst_date ~ " as varchar))) end",
    "case when " ~ fcst_time ~ " is null then 'N:<NULL>' else concat('V:', trim(cast(" ~ fcst_time ~ " as varchar))) end",
    "case when " ~ fcst_value ~ " is null then 'N:<NULL>' else concat('V:', trim(cast(" ~ fcst_value ~ " as varchar))) end"
] -%}
lower(to_hex(sha256(to_utf8(json_format(cast(array[
    {{ tagged | join(',\n    ') }}
] as json))))))
{%- endmacro %}

{% macro weather_w1_lookback_minutes() -%}
{%- set raw = var('weather_w1_lookback_minutes', default=30) -%}
{%- set value = raw | string -%}
{%- if not modules.re.fullmatch('^[1-9][0-9]{0,3}$', value) or (value | int) > 1440 -%}
    {{ exceptions.raise_compiler_error('weather_w1_lookback_minutes는 1~1440 정수여야 합니다.') }}
{%- endif -%}
{{ return(value) }}
{%- endmacro %}

{% macro weather_w1_initial_build_guard() -%}
{%- if flags.FULL_REFRESH -%}
    {{ exceptions.raise_compiler_error('Weather W1은 --full-refresh를 허용하지 않습니다.') }}
{%- endif -%}
{%- if execute and not is_incremental() -%}
    {%- set mode = var('weather_w1_initial_build_mode', '') -%}
    {%- set source_schema = env_var('ASK_SEOUL_SCHEMA', 'ask_seoul') -%}
    {%- set target_schema = target.schema -%}
    {%- set namespace_pattern = '^dev_[a-z0-9_]+_weather_contract_test_[0-9a-f]{24}$' -%}
    {%- set isolated_smoke = (
        mode == 'bounded_isolated_smoke'
        and target.database == 'iceberg_dev'
        and source_schema == target_schema
        and modules.re.fullmatch(namespace_pattern, target_schema)
    ) -%}
    {%- if not isolated_smoke and not weather_w2_shared_dev_build_allowed() -%}
        {{ exceptions.raise_compiler_error(
            'Weather W1 최초 빌드는 동일한 unique isolated dev source/target와 '
            ~ 'weather_w1_initial_build_mode=bounded_isolated_smoke 또는 검증된 W2 bounded DEV repair에서만 허용됩니다.'
        ) }}
    {%- endif -%}
{%- endif -%}
{%- endmacro %}

{% macro weather_w1_candidate_environment_guard(candidate_name) -%}
{%- if flags.FULL_REFRESH -%}
    {{ exceptions.raise_compiler_error(candidate_name ~ '은 --full-refresh를 허용하지 않습니다.') }}
{%- endif -%}
{%- if execute -%}
    {%- set mode = var('weather_w1_initial_build_mode', '') -%}
    {%- set target_schema = target.schema -%}
    {%- set namespace_pattern = '^dev_[a-z0-9_]+_weather_contract_test_[0-9a-f]{24}$' -%}
    {%- set isolated_smoke = (
        mode == 'bounded_isolated_smoke'
        and target.database == 'iceberg_dev'
        and modules.re.fullmatch(namespace_pattern, target_schema)
    ) -%}
    {%- if not isolated_smoke and not weather_w2_shared_dev_build_allowed() -%}
        {{ exceptions.raise_compiler_error(
            candidate_name ~ '은 unique isolated iceberg_dev namespace와 '
            ~ 'weather_w1_initial_build_mode=bounded_isolated_smoke 또는 검증된 W2 bounded DEV repair에서만 실행할 수 있습니다.'
        ) }}
    {%- endif -%}
{%- endif -%}
{{ return('') }}
{%- endmacro %}

{% macro weather_w1_candidate_seed_guard() -%}
{%- do weather_w1_candidate_environment_guard('weather_admin_dong_grid_bridge_history') -%}
select 1
{%- endmacro %}

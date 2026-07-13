{# W2 public Gold/repair shared contract: exact inputs, bounded evidence, winner order. #}

{% macro weather_w2_repair_context() -%}
{%- set raw_mode = var('weather_w2_repair_mode', 'normal') -%}
{%- set raw_start = var('weather_w2_repair_start_at', none) -%}
{%- set raw_cutoff = var('weather_w2_publishable_cutoff_at', none) -%}
{%- set raw_bridge_version = var('weather_w2_bridge_version', none) -%}
{%- set mode = raw_mode | string -%}
{%- set timestamp_pattern = '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}$' -%}
{%- set expected_bridge_version = 'weather_admin_dong_grid_bridge_v1' -%}

{%- if flags.FULL_REFRESH -%}
    {{ exceptions.raise_compiler_error('Weather W2는 --full-refresh를 허용하지 않습니다.') }}
{%- endif -%}

{%- if mode == 'normal' -%}
    {%- if raw_start is not none or raw_cutoff is not none -%}
        {{ exceptions.raise_compiler_error(
            'Weather W2 repair endpoint는 weather_w2_repair_mode=bounded_reconcile과 함께 지정해야 합니다.'
        ) }}
    {%- endif -%}
    {%- if raw_bridge_version is not none
        and (raw_bridge_version | string) != expected_bridge_version -%}
        {{ exceptions.raise_compiler_error(
            'weather_w2_bridge_version은 weather_admin_dong_grid_bridge_v1이어야 합니다.'
        ) }}
    {%- endif -%}
    {{ return({
        'mode': mode,
        'start_at': none,
        'cutoff_at': none,
        'bridge_version': expected_bridge_version,
    }) }}
{%- elif mode != 'bounded_reconcile' -%}
    {{ exceptions.raise_compiler_error(
        'weather_w2_repair_mode는 normal 또는 bounded_reconcile이어야 합니다.'
    ) }}
{%- endif -%}

{%- if raw_start is none or raw_cutoff is none or raw_bridge_version is none -%}
    {{ exceptions.raise_compiler_error(
        'bounded_reconcile은 start, cutoff, bridge version 세 입력을 모두 요구합니다.'
    ) }}
{%- endif -%}
{%- set start_at = raw_start | string -%}
{%- set cutoff_at = raw_cutoff | string -%}
{%- set bridge_version = raw_bridge_version | string -%}
{%- if not modules.re.fullmatch(timestamp_pattern, start_at)
    or not modules.re.fullmatch(timestamp_pattern, cutoff_at) -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 repair 시각은 KST YYYY-MM-DD HH:MM:SS.ffffff timestamp(6) 형식이어야 합니다.'
    ) }}
{%- endif -%}
{%- if bridge_version != expected_bridge_version -%}
    {{ exceptions.raise_compiler_error(
        'weather_w2_bridge_version은 weather_admin_dong_grid_bridge_v1이어야 합니다.'
    ) }}
{%- endif -%}
{%- if target.name != 'dev'
    or target.database != 'iceberg_dev'
    or target.schema != 'weather' -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 bounded repair는 dev/iceberg_dev/weather에서만 실행할 수 있습니다.'
    ) }}
{%- endif -%}

{{ return({
    'mode': mode,
    'start_at': start_at,
    'cutoff_at': cutoff_at,
    'bridge_version': bridge_version,
}) }}
{%- endmacro %}

{% macro weather_w2_repair_mode() -%}
{{ return(weather_w2_repair_context()['mode']) }}
{%- endmacro %}

{% macro weather_w2_is_repair() -%}
{{ return(weather_w2_repair_mode() == 'bounded_reconcile') }}
{%- endmacro %}

{% macro weather_w2_repair_start_at() -%}
{%- set context = weather_w2_repair_context() -%}
{%- if context['start_at'] is none -%}
    {{ exceptions.raise_compiler_error('normal mode에는 weather_w2_repair_start_at이 없습니다.') }}
{%- endif -%}
{{ return(context['start_at']) }}
{%- endmacro %}

{% macro weather_w2_publishable_cutoff_at() -%}
{%- set context = weather_w2_repair_context() -%}
{%- if context['cutoff_at'] is none -%}
    {{ exceptions.raise_compiler_error('normal mode에는 weather_w2_publishable_cutoff_at이 없습니다.') }}
{%- endif -%}
{{ return(context['cutoff_at']) }}
{%- endmacro %}

{% macro weather_w2_bridge_version() -%}
{{ return(weather_w2_repair_context()['bridge_version']) }}
{%- endmacro %}

{% macro weather_w2_shared_dev_build_allowed() -%}
{%- set context = weather_w2_repair_context() -%}
{{ return(
    context['mode'] == 'bounded_reconcile'
    and target.name == 'dev'
    and target.database == 'iceberg_dev'
    and target.schema == 'weather'
) }}
{%- endmacro %}

{% macro weather_w2_assert_repair_evidence() -%}
{%- if not weather_w2_is_repair() or not execute -%}
    {{ return('') }}
{%- endif -%}
{%- set start_literal = weather_w2_repair_start_at() -%}
{%- set cutoff_literal = weather_w2_publishable_cutoff_at() -%}
{%- set evidence_sql -%}
with params as (
    select
        timestamp '{{ start_literal }}' as start_at,
        timestamp '{{ cutoff_literal }}' as cutoff_at,
        cast(current_timestamp at time zone 'Asia/Seoul' as timestamp(6)) as current_kst_at
),
manifest_events as (
    select
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(dag_id as varchar) as dag_id,
        cast(status as varchar) as manifest_status,
        cast(is_publishable as boolean) as is_publishable,
        cast(expected_rows as bigint) as expected_rows,
        cast(actual_rows as bigint) as actual_rows,
        cast(expected_raw_objects as bigint) as expected_raw_objects,
        cast(actual_raw_objects as bigint) as actual_raw_objects,
        cast(event_at as timestamp(6)) as manifest_event_at_utc,
        cast(event_at as timestamp(6)) + interval '9' hour as event_at
    from {{ source('weather_bronze', 'collection_run_manifest') }}
    where cast(source_id as varchar) = 'kma_vilage_fcst'
),
manifest_before_cutoff as (
    select manifest_events.*
    from manifest_events
    cross join params
    where event_at <= cutoff_at
),
manifest_state_ranked as (
    select
        manifest_before_cutoff.*,
        event_at as manifest_published_at,
        row_number() over (
            partition by cast(source_id as varchar), cast(dag_run_id as varchar)
            order by event_at desc, dag_id desc, manifest_status desc
        ) as manifest_row_num
    from manifest_before_cutoff
),
manifest_at_cutoff as (
    select *
    from manifest_state_ranked
    where manifest_row_num = 1
),
eligible_anchors as (
    select manifest_at_cutoff.*
    from manifest_at_cutoff
    cross join params
    where manifest_status = 'SUCCESS'
      and is_publishable
      and manifest_published_at >= start_at
      and manifest_published_at <= cutoff_at
),
manifest_summary as (
    select
        count(*) as anchor_count,
        count_if(
            expected_rows is null
            or actual_rows is null
            or expected_raw_objects is null
            or actual_raw_objects is null
            or not (
                expected_rows = actual_rows
                and expected_rows > 0
                and expected_raw_objects = actual_raw_objects
                and expected_raw_objects > 0
            )
        ) as invalid_manifest_count
    from eligible_anchors
),
bronze_kma_vilage_fcst as (
    select
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(raw_object_key as varchar) as raw_object_key
    from {{ source('weather_bronze', 'kma_vilage_fcst') }}
),
bronze_counts as (
    select
        anchor.source_id,
        anchor.dag_run_id,
        anchor.actual_rows,
        anchor.actual_raw_objects,
        count(bronze.dag_run_id) as bronze_row_count,
        count(distinct raw_object_key) as bronze_raw_object_count
    from eligible_anchors as anchor
    left join bronze_kma_vilage_fcst as bronze
      on cast(bronze.source_id as varchar) = anchor.source_id
     and cast(bronze.dag_run_id as varchar) = anchor.dag_run_id
    group by anchor.source_id, anchor.dag_run_id, anchor.actual_rows, anchor.actual_raw_objects
),
evidence_summary as (
    select
        manifest_summary.anchor_count,
        manifest_summary.invalid_manifest_count,
        coalesce(sum(case when bronze_row_count != actual_rows then 1 else 0 end), 0) as bronze_row_mismatch_count,
        coalesce(sum(case when bronze_raw_object_count != actual_raw_objects then 1 else 0 end), 0) as bronze_raw_mismatch_count
    from manifest_summary
    left join bronze_counts on true
    group by manifest_summary.anchor_count, manifest_summary.invalid_manifest_count
)
select
    case
        when start_at > cutoff_at
          or cutoff_at > start_at + interval '24' hour
          or cutoff_at > current_kst_at
        then 1 else 0
    end as invalid_window_count,
    case when anchor_count = 0 then 1 else 0 end as empty_anchor_count,
    invalid_manifest_count,
    bronze_row_mismatch_count,
    bronze_raw_mismatch_count
from evidence_summary
cross join params
{%- endset -%}
{%- set evidence = run_query(evidence_sql) -%}
{%- if evidence is none or evidence.rows | length != 1 -%}
    {{ exceptions.raise_compiler_error('Weather W2 repair evidence query가 단일 summary를 반환하지 않았습니다.') }}
{%- endif -%}
{%- set row = evidence.rows[0] -%}
{%- if (row[0] | int) != 0
    or (row[1] | int) != 0
    or (row[2] | int) != 0
    or (row[3] | int) != 0
    or (row[4] | int) != 0 -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 repair evidence가 window, anchor, manifest 또는 Bronze completeness 검증에 실패했습니다.'
    ) }}
{%- endif -%}
{{ return('') }}
{%- endmacro %}

{% macro weather_w2_grid_winner_is_newer(left_alias, right_alias) -%}
(
    {{ left_alias }}.collected_at > {{ right_alias }}.collected_at
    or (
        {{ left_alias }}.collected_at = {{ right_alias }}.collected_at
        and {{ left_alias }}.raw_object_key > {{ right_alias }}.raw_object_key
    )
    or (
        {{ left_alias }}.collected_at = {{ right_alias }}.collected_at
        and {{ left_alias }}.raw_object_key = {{ right_alias }}.raw_object_key
        and {{ left_alias }}.request_id > {{ right_alias }}.request_id
    )
    or (
        {{ left_alias }}.collected_at = {{ right_alias }}.collected_at
        and {{ left_alias }}.raw_object_key = {{ right_alias }}.raw_object_key
        and {{ left_alias }}.request_id = {{ right_alias }}.request_id
        and {{ left_alias }}.selected_dag_run_id > {{ right_alias }}.selected_dag_run_id
    )
    or (
        {{ left_alias }}.collected_at = {{ right_alias }}.collected_at
        and {{ left_alias }}.raw_object_key = {{ right_alias }}.raw_object_key
        and {{ left_alias }}.request_id = {{ right_alias }}.request_id
        and {{ left_alias }}.selected_dag_run_id = {{ right_alias }}.selected_dag_run_id
        and {{ left_alias }}.selected_page_no > {{ right_alias }}.selected_page_no
    )
    or (
        {{ left_alias }}.collected_at = {{ right_alias }}.collected_at
        and {{ left_alias }}.raw_object_key = {{ right_alias }}.raw_object_key
        and {{ left_alias }}.request_id = {{ right_alias }}.request_id
        and {{ left_alias }}.selected_dag_run_id = {{ right_alias }}.selected_dag_run_id
        and {{ left_alias }}.selected_page_no = {{ right_alias }}.selected_page_no
        and {{ left_alias }}.selected_source_item_key > {{ right_alias }}.selected_source_item_key
    )
)
{%- endmacro %}

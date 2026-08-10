{# W2 public Gold/repair shared contract: exact inputs, bounded evidence, winner order. #}

{% macro weather_w2_repair_context() -%}
{%- set raw_mode = var('weather_w2_repair_mode', 'normal') -%}
{%- set raw_start = var('weather_w2_repair_start_at', none) -%}
{%- set raw_cutoff = var('weather_w2_publishable_cutoff_at', none) -%}
{%- set raw_bridge_version = var('weather_w2_bridge_version', none) -%}
{%- set raw_canonical_revision_date = var('weather_w2_canonical_revision_date', none) -%}
{%- set mode = raw_mode | string -%}
{%- set timestamp_pattern = '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}$' -%}
{%- set expected_bridge_version = 'weather_admin_dong_grid_bridge_v1' -%}
{%- set approved_revision_date = '2025-04-01' -%}
{%- set is_test_node = model is defined and model.resource_type == 'test' -%}

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
    {%- if raw_canonical_revision_date is not none
        and (raw_canonical_revision_date | string) != approved_revision_date -%}
        {{ exceptions.raise_compiler_error(
            'weather_w2_canonical_revision_date는 승인 revision 2025-04-01이어야 합니다.'
        ) }}
    {%- endif -%}
    {{ return({
        'mode': mode,
        'start_at': none,
        'cutoff_at': none,
        'bridge_version': expected_bridge_version,
        'canonical_revision_date': approved_revision_date,
    }) }}
{%- elif mode != 'bounded_reconcile' -%}
    {{ exceptions.raise_compiler_error(
        'weather_w2_repair_mode는 normal 또는 bounded_reconcile이어야 합니다.'
    ) }}
{%- endif -%}

{%- if raw_start is none
    or raw_cutoff is none
    or raw_bridge_version is none
    or raw_canonical_revision_date is none -%}
    {{ exceptions.raise_compiler_error(
        'bounded_reconcile은 start, cutoff, bridge version, canonical revision 네 입력을 모두 요구합니다.'
    ) }}
{%- endif -%}
{%- set start_at = raw_start | string -%}
{%- set cutoff_at = raw_cutoff | string -%}
{%- set bridge_version = raw_bridge_version | string -%}
{%- set canonical_revision_date = raw_canonical_revision_date | string -%}
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
{%- if canonical_revision_date != approved_revision_date -%}
    {{ exceptions.raise_compiler_error(
        'weather_w2_canonical_revision_date는 승인 revision 2025-04-01이어야 합니다.'
    ) }}
{%- endif -%}
{%- if target.name != 'dev'
    or target.database != 'iceberg_dev'
    or (
        execute
        and not is_test_node
        and this.schema != weather_schema_name()
    ) -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 bounded repair는 dev/iceberg_dev/weather에서만 실행할 수 있습니다.'
    ) }}
{%- endif -%}

{{ return({
    'mode': mode,
    'start_at': start_at,
    'cutoff_at': cutoff_at,
    'bridge_version': bridge_version,
    'canonical_revision_date': canonical_revision_date,
}) }}
{%- endmacro %}

{% macro weather_w2_canonical_contract() -%}
{%- set approved_revision_date = '2025-04-01' -%}
{%- set requested_revision_date = var('weather_w2_canonical_revision_date', none) -%}
{%- if execute and requested_revision_date is none -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 public Gold 실행에는 weather_w2_canonical_revision_date가 필요합니다.'
    ) }}
{%- endif -%}
{%- if requested_revision_date is not none
    and (requested_revision_date | string) != approved_revision_date -%}
    {{ exceptions.raise_compiler_error(
        'weather_w2_canonical_revision_date는 승인 revision 2025-04-01이어야 합니다.'
    ) }}
{%- endif -%}
{{ return({
    'revision_date': approved_revision_date,
    'bridge_count': 428,
    'canonical_count': 426,
    'mapped_canonical_count': 426,
}) }}
{%- endmacro %}

{% macro weather_w2_repair_mode() -%}
{{ return(weather_w2_repair_context()['mode']) }}
{%- endmacro %}

{% macro weather_w2_is_repair() -%}
{{ return(weather_w2_repair_mode() == 'bounded_reconcile') }}
{%- endmacro %}

{% macro weather_w2_historical_snapshot_context() -%}
{%- set raw_enabled = var('weather_w2_historical_transform', false) -%}
{%- set enabled_text = raw_enabled | string | lower | trim -%}
{%- if enabled_text not in ['true', 'false'] -%}
    {{ exceptions.raise_compiler_error(
        'weather_w2_historical_transform은 true 또는 false여야 합니다.'
    ) }}
{%- endif -%}
{%- set enabled = enabled_text == 'true' -%}
{%- set snapshot_dag_run_id = var('weather_snapshot_dag_run_id', '') | string | trim -%}
{%- if enabled -%}
    {%- if weather_w2_is_repair() -%}
        {{ exceptions.raise_compiler_error(
            'Weather W2 historical snapshot과 bounded_reconcile은 함께 실행할 수 없습니다.'
        ) }}
    {%- endif -%}
    {%- if not modules.re.fullmatch('^[A-Za-z0-9_.:+-]{1,250}$', snapshot_dag_run_id) -%}
        {{ exceptions.raise_compiler_error(
            'Weather W2 historical snapshot은 하나의 명시적 Airflow dag_run_id가 필요합니다.'
        ) }}
    {%- endif -%}
    {%- if not weather_w1_prod_snapshot_bootstrap_allowed() -%}
        {{ exceptions.raise_compiler_error(
            'Weather W2 historical snapshot은 prod Iceberg Weather 대상에서만 실행할 수 있습니다.'
        ) }}
    {%- endif -%}
{%- endif -%}
{{ return({'enabled': enabled, 'snapshot_dag_run_id': snapshot_dag_run_id}) }}
{%- endmacro %}

{% macro weather_w2_is_historical_snapshot() -%}
{{ return(weather_w2_historical_snapshot_context()['enabled']) }}
{%- endmacro %}

{% macro weather_w2_historical_snapshot_dag_run_id() -%}
{{ return(weather_w2_historical_snapshot_context()['snapshot_dag_run_id']) }}
{%- endmacro %}

{% macro weather_w2_assert_historical_snapshot_evidence() -%}
{%- if execute and weather_w2_is_historical_snapshot() -%}
    {%- do weather_w1_assert_prod_snapshot_bootstrap_evidence() -%}
{%- endif -%}
{{ return('') }}
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
    and this.schema == weather_schema_name()
) }}
{%- endmacro %}

{% macro weather_w2_latest_publishable_anchors_sql() -%}
with params as (
    select
        timestamp '{{ weather_w2_repair_start_at() }}' as start_at,
        timestamp '{{ weather_w2_publishable_cutoff_at() }}' as cutoff_at
),
manifest_events as (
    select
        cast(source_id as varchar) as source_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(dag_id as varchar) as dag_id,
        cast(status as varchar) as manifest_status,
        cast(is_publishable as boolean) as is_publishable,
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
            partition by source_id, dag_run_id
            order by event_at desc, dag_id desc
        ) as manifest_row_num
    from manifest_before_cutoff
),
eligible_manifest_anchors as (
    select manifest_state_ranked.*
    from manifest_state_ranked
    cross join params
    where manifest_row_num = 1
      and manifest_status = 'SUCCESS'
      and is_publishable
      and manifest_published_at >= start_at
      and manifest_published_at <= cutoff_at
)
select
    source_id as anchor_source_id,
    dag_run_id as anchor_dag_run_id,
    manifest_published_at as anchor_published_at
from eligible_manifest_anchors
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
manifest_order_key_counts as (
    select
        source_id,
        dag_run_id,
        event_at,
        dag_id,
        count(*) as state_count
    from manifest_before_cutoff
    group by source_id, dag_run_id, event_at, dag_id
),
manifest_order_key_ranked as (
    select
        manifest_order_key_counts.*,
        row_number() over (
            partition by source_id, dag_run_id
            order by event_at desc, dag_id desc
        ) as order_key_num
    from manifest_order_key_counts
),
manifest_ambiguous_ties as (
    select manifest_order_key_ranked.*
    from manifest_order_key_ranked
    cross join params
    where order_key_num = 1
      and state_count > 1
      and event_at >= start_at
      and event_at <= cutoff_at
),
manifest_state_ranked as (
    select
        manifest_before_cutoff.*,
        event_at as manifest_published_at,
        row_number() over (
            partition by cast(source_id as varchar), cast(dag_run_id as varchar)
            order by event_at desc, dag_id desc
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
        (select count(*) from manifest_ambiguous_ties) as ambiguous_state_count,
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
        manifest_summary.ambiguous_state_count,
        manifest_summary.invalid_manifest_count,
        coalesce(sum(case when bronze_row_count != actual_rows then 1 else 0 end), 0) as bronze_row_mismatch_count,
        coalesce(sum(case when bronze_raw_object_count != actual_raw_objects then 1 else 0 end), 0) as bronze_raw_mismatch_count
    from manifest_summary
    left join bronze_counts on true
    group by
        manifest_summary.anchor_count,
        manifest_summary.ambiguous_state_count,
        manifest_summary.invalid_manifest_count
)
select
    case
        when start_at > cutoff_at
          or cutoff_at > start_at + interval '24' hour
          or cutoff_at > current_kst_at
        then 1 else 0
    end as invalid_window_count,
    case when anchor_count = 0 then 1 else 0 end as empty_anchor_count,
    ambiguous_state_count,
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
    or (row[4] | int) != 0
    or (row[5] | int) != 0 -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 repair evidence가 window, anchor, manifest 또는 Bronze completeness 검증에 실패했습니다.'
    ) }}
{%- endif -%}
{{ return('') }}
{%- endmacro %}

{% macro weather_w2_grid_winner_is_newer(left_alias, right_alias) -%}
{# Equal winners also block a repair rewrite; NULL is total-ordered last, matching Trino DESC. #}
{%- set winner_columns = [
    'collected_at',
    'raw_object_key',
    'request_id',
    'selected_dag_run_id',
    'selected_page_no',
    'selected_source_item_key',
] -%}
(
    {%- for column_name in winner_columns %}
    (
        {%- for prior_column in winner_columns[:loop.index0] %}
        {{ left_alias }}.{{ prior_column }} is not distinct from {{ right_alias }}.{{ prior_column }}
        and
        {%- endfor %}
        (
            (
                {{ left_alias }}.{{ column_name }} is not null
                and {{ right_alias }}.{{ column_name }} is null
            )
            or (
                {{ left_alias }}.{{ column_name }} is not null
                and {{ right_alias }}.{{ column_name }} is not null
                and {{ left_alias }}.{{ column_name }} > {{ right_alias }}.{{ column_name }}
            )
        )
    )
    or
    {%- endfor %}
    (
        {%- for column_name in winner_columns %}
        {{ left_alias }}.{{ column_name }} is not distinct from {{ right_alias }}.{{ column_name }}
        {{ 'and' if not loop.last }}
        {%- endfor %}
    )
)
{%- endmacro %}

{% macro weather_w2_assert_gold_target(relation=none) -%}
{%- if relation is none -%}
    {%- set relation = this -%}
{%- endif -%}
{%- set approved_dev_target = (
    target.name == 'dev'
    and target.database == 'iceberg_dev'
    and relation.schema == weather_schema_name()
) -%}
{%- set approved_prod_snapshot = (
    relation.schema == weather_schema_name()
    and weather_w1_prod_snapshot_bootstrap_allowed()
) -%}
{%- if execute and not approved_dev_target and not approved_prod_snapshot -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 public Gold는 승인된 dev/iceberg_dev/weather 또는 '
        ~ 'pinned canonical prod snapshot에서만 실행할 수 있습니다.'
    ) }}
{%- endif -%}
{%- if execute and approved_prod_snapshot -%}
    {%- do weather_w1_assert_prod_snapshot_bootstrap_evidence() -%}
{%- endif -%}
{{ return('') }}
{%- endmacro %}

{% macro weather_w2_gold_initial_build_guard() -%}
{%- if (
    execute
    and not is_incremental()
    and not weather_w2_is_repair()
    and not weather_w1_prod_snapshot_bootstrap_allowed()
) -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 shared Gold 최초 빌드는 검증된 bounded_reconcile 또는 '
        ~ 'pinned canonical prod snapshot에서만 허용됩니다.'
    ) }}
{%- endif -%}
{{ return('') }}
{%- endmacro %}

{% macro weather_w2_assert_gold_source_contract() -%}
{%- if not execute -%}
    {{ return('') }}
{%- endif -%}
{%- set bridge_version = weather_w2_bridge_version() -%}
{%- set canonical_contract = weather_w2_canonical_contract() -%}
{%- set repair_mode = weather_w2_is_repair() -%}
{%- set source_contract_sql -%}
with active_bridge as (
    select
        cast(source_admin_code as varchar) as source_admin_code,
        cast(nx as integer) as nx,
        cast(ny as integer) as ny
    from {{ ref('bridge_weather_admin_dong_grid') }}
    where cast(bridge_version as varchar) = '{{ bridge_version }}'
),
bridge_duplicate_grain as (
    select source_admin_code, nx, ny
    from active_bridge
    group by source_admin_code, nx, ny
    having count(*) > 1
),
bridge_duplicate_admin as (
    select source_admin_code
    from active_bridge
    group by source_admin_code
    having count(*) > 1
),
canonical as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        cast(revision_date as date) as admin_dong_revision_date
    from {{ ref('asac_axes', 'dim_admin_dong') }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),
canonical_duplicate_grain as (
    select admin_dong_code
    from canonical
    group by admin_dong_code
    having count(*) > 1
),
bridge_canonical as (
    select
        bridge.source_admin_code,
        bridge.nx,
        bridge.ny,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date
    from active_bridge as bridge
    inner join canonical
        on bridge.source_admin_code = canonical.admin_dong_code
)
{% if repair_mode %}
,
eligible_manifest_anchors as (
    {{ weather_w2_latest_publishable_anchors_sql() }}
),
repair_candidates as (
    select
        bridge.source_admin_code as admin_dong_code,
        cast(grid.forecast_at as timestamp(6)) as forecast_at,
        cast(grid.category as varchar) as category,
        canonical.admin_dong,
        canonical.gu_code,
        canonical.gu,
        canonical.admin_dong_revision_date,
        cast('{{ bridge_version }}' as varchar) as bridge_version,
        cast(grid.nx as integer) as nx,
        cast(grid.ny as integer) as ny,
        cast(grid.source_grid_place_id as varchar) as source_grid_place_id,
        cast(grid.issued_at as timestamp(6)) as issued_at,
        cast(grid.collected_at as timestamp(6)) as collected_at,
        cast(grid.published_at as timestamp(6)) as published_at,
        cast(grid.value_representation as varchar) as value_representation,
        cast(grid.forecast_lead_hours as bigint) as forecast_lead_hours,
        cast(grid.source_id as varchar) as source_id,
        cast(grid.selected_dag_run_id as varchar) as dag_run_id,
        cast(grid.raw_object_key as varchar) as raw_object_key,
        cast(grid.request_id as varchar) as request_id
    from {{ ref('silver_kma_vilage_fcst_grid') }} as grid
    inner join eligible_manifest_anchors as anchor
        on cast(grid.source_id as varchar) = anchor.anchor_source_id
       and cast(grid.selected_dag_run_id as varchar) = anchor.anchor_dag_run_id
    inner join active_bridge as bridge
        on cast(grid.nx as integer) = bridge.nx
       and cast(grid.ny as integer) = bridge.ny
    inner join canonical
        on bridge.source_admin_code = canonical.admin_dong_code
    where cast(grid.published_at as timestamp(6))
          >= timestamp '{{ weather_w2_repair_start_at() }}'
      and cast(grid.published_at as timestamp(6))
          <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
),
repair_expected as (
    select
        admin_dong_code,
        forecast_at,
        category,
        max_by(
            cast(row(
                admin_dong,
                gu_code,
                gu,
                admin_dong_revision_date,
                bridge_version,
                nx,
                ny,
                source_grid_place_id,
                issued_at,
                collected_at,
                published_at,
                value_representation,
                forecast_lead_hours,
                source_id,
                dag_run_id,
                raw_object_key,
                request_id
            ) as row(
                admin_dong varchar,
                gu_code varchar,
                gu varchar,
                admin_dong_revision_date date,
                bridge_version varchar,
                nx integer,
                ny integer,
                source_grid_place_id varchar,
                issued_at timestamp(6),
                collected_at timestamp(6),
                published_at timestamp(6),
                value_representation varchar,
                forecast_lead_hours bigint,
                source_id varchar,
                dag_run_id varchar,
                raw_object_key varchar,
                request_id varchar
            )),
            {{ weather_w2_grid_winner_order_key('repair_candidates') }}
        ) as winner
    from repair_candidates
    group by admin_dong_code, forecast_at, category
),
repair_expected_rows as (
    select
        admin_dong_code,
        forecast_at,
        category,
        winner.admin_dong as admin_dong,
        winner.gu_code as gu_code,
        winner.gu as gu,
        winner.admin_dong_revision_date as admin_dong_revision_date,
        winner.bridge_version as bridge_version,
        winner.nx as nx,
        winner.ny as ny,
        winner.source_grid_place_id as source_grid_place_id,
        winner.issued_at as issued_at,
        winner.collected_at as collected_at,
        winner.published_at as published_at,
        winner.value_representation as value_representation,
        winner.forecast_lead_hours as forecast_lead_hours,
        winner.source_id as source_id,
        winner.dag_run_id as dag_run_id,
        winner.raw_object_key as raw_object_key,
        winner.request_id as request_id
    from repair_expected
),
repair_expected_duplicate_grain as (
    select admin_dong_code, forecast_at, category
    from repair_expected_rows
    group by admin_dong_code, forecast_at, category
    having count(*) > 1
),
repair_expected_summary as (
    select
        count(*) as repair_expected_count,
        count_if(
            admin_dong_code is null
            or forecast_at is null
            or category is null
            or admin_dong is null
            or gu_code is null
            or gu is null
            or admin_dong_revision_date is null
            or bridge_version is null
            or nx is null
            or ny is null
            or source_grid_place_id is null
            or issued_at is null
            or collected_at is null
            or published_at is null
            or value_representation is null
            or forecast_lead_hours is null
            or source_id is null
            or dag_run_id is null
            or raw_object_key is null
            or request_id is null
        ) as repair_null_contract_count,
        (select count(*) from repair_expected_duplicate_grain) as repair_duplicate_count
    from repair_expected_rows
)
{% endif %}
,
source_summary as (
    select
        count(*) as bridge_count,
        count_if(source_admin_code is null or nx is null or ny is null) as bridge_null_count,
        (select count(*) from bridge_duplicate_grain) as bridge_duplicate_count,
        (select count(*) from bridge_duplicate_admin) as bridge_admin_duplicate_count,
        (select count(*) from canonical) as canonical_count,
        (
            (select count_if(admin_dong_code is null) from canonical)
            + (
                select count_if(
                    admin_dong is null
                    or gu_code is null
                    or gu is null
                    or admin_dong_revision_date is null
                )
                from bridge_canonical
            )
        ) as canonical_null_count,
        (select count(*) from canonical_duplicate_grain) as canonical_duplicate_count,
        (select count(*) from bridge_canonical) as bridge_canonical_count
    from active_bridge
)
select
    bridge_count,
    bridge_null_count,
    bridge_duplicate_count,
    bridge_admin_duplicate_count,
    canonical_count,
    canonical_null_count,
    canonical_duplicate_count,
    bridge_canonical_count,
    {% if repair_mode %}
    (select repair_expected_count from repair_expected_summary),
    (select repair_null_contract_count from repair_expected_summary),
    (select repair_duplicate_count from repair_expected_summary)
    {% else %}
    cast(null as bigint),
    cast(null as bigint),
    cast(null as bigint)
    {% endif %}
from source_summary
{%- endset -%}
{%- set source_contract = run_query(source_contract_sql) -%}
{%- if source_contract is none or source_contract.rows | length != 1 -%}
    {{ exceptions.raise_compiler_error('Weather W2 Gold source contract query가 단일 summary를 반환하지 않았습니다.') }}
{%- endif -%}
{%- set row = source_contract.rows[0] -%}
{%- set repair_expected_count = (row[8] | int) if repair_mode else 1 -%}
{%- set repair_null_contract_count = (row[9] | int) if repair_mode else 0 -%}
{%- set repair_duplicate_count = (row[10] | int) if repair_mode else 0 -%}
{%- if (row[0] | int) != canonical_contract['bridge_count']
    or (row[1] | int) != 0
    or (row[2] | int) != 0
    or (row[3] | int) != 0
    or (row[4] | int) != canonical_contract['canonical_count']
    or (row[5] | int) != 0
    or (row[6] | int) != 0
    or (row[7] | int) != canonical_contract['mapped_canonical_count']
    or repair_expected_count == 0
    or repair_null_contract_count != 0
    or repair_duplicate_count != 0 -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 Gold source contract가 explicit bridge v1 또는 canonical grain 검증에 실패했습니다.'
    ) }}
{%- endif -%}
{{ return('') }}
{%- endmacro %}

{% macro weather_w2_canonical_grain_bucket(candidate_alias, bucket_count) -%}
mod(
    mod(
        from_big_endian_64(
            xxhash64(
                to_utf8(
                    json_format(cast(row(
                        cast({{ candidate_alias }}.admin_dong_code as varchar),
                        cast({{ candidate_alias }}.forecast_at as timestamp(6)),
                        cast({{ candidate_alias }}.category as varchar)
                    ) as json))
                )
            )
        ),
        cast({{ bucket_count }} as bigint)
    ) + cast({{ bucket_count }} as bigint),
    cast({{ bucket_count }} as bigint)
)
{%- endmacro %}

{% macro weather_w2_gold_winner_is_not_older(source_alias, dest_alias) -%}
{%- set winner_columns = [
    'issued_at',
    'collected_at',
    'raw_object_key',
    'request_id',
    'dag_run_id',
    'source_grid_place_id',
    'nx',
    'ny',
] -%}
(
    {%- for column_name in winner_columns %}
    (
        {%- for prior_column in winner_columns[:loop.index0] %}
        {{ source_alias }}.{{ prior_column }} is not distinct from {{ dest_alias }}.{{ prior_column }}
        and
        {%- endfor %}
        (
            (
                {{ source_alias }}.{{ column_name }} is not null
                and {{ dest_alias }}.{{ column_name }} is null
            )
            or (
                {{ source_alias }}.{{ column_name }} is not null
                and {{ dest_alias }}.{{ column_name }} is not null
                and {{ source_alias }}.{{ column_name }} > {{ dest_alias }}.{{ column_name }}
            )
        )
    )
    or
    {%- endfor %}
    (
        {%- for column_name in winner_columns %}
        {{ source_alias }}.{{ column_name }} is not distinct from {{ dest_alias }}.{{ column_name }}
        {{ 'and' if not loop.last }}
        {%- endfor %}
    )
)
{%- endmacro %}

{% macro weather_w2_grid_winner_order_key(candidate_alias) -%}
row(
    cast({{ candidate_alias }}.issued_at is not null as tinyint),
    cast({{ candidate_alias }}.issued_at as timestamp(6)),
    cast({{ candidate_alias }}.collected_at is not null as tinyint),
    cast({{ candidate_alias }}.collected_at as timestamp(6)),
    cast({{ candidate_alias }}.raw_object_key is not null as tinyint),
    cast({{ candidate_alias }}.raw_object_key as varchar),
    cast({{ candidate_alias }}.request_id is not null as tinyint),
    cast({{ candidate_alias }}.request_id as varchar),
    cast({{ candidate_alias }}.dag_run_id is not null as tinyint),
    cast({{ candidate_alias }}.dag_run_id as varchar),
    cast({{ candidate_alias }}.source_grid_place_id is not null as tinyint),
    cast({{ candidate_alias }}.source_grid_place_id as varchar),
    cast({{ candidate_alias }}.nx is not null as tinyint),
    cast({{ candidate_alias }}.nx as integer),
    cast({{ candidate_alias }}.ny is not null as tinyint),
    cast({{ candidate_alias }}.ny as integer)
)
{%- endmacro %}

{% macro weather_w2_gold_candidate_row(candidate_alias) -%}
cast(row(
    cast({{ candidate_alias }}.admin_dong_code as varchar),
    cast({{ candidate_alias }}.admin_dong as varchar),
    cast({{ candidate_alias }}.gu_code as varchar),
    cast({{ candidate_alias }}.gu as varchar),
    cast({{ candidate_alias }}.admin_dong_revision_date as date),
    cast({{ candidate_alias }}.bridge_version as varchar),
    cast({{ candidate_alias }}.nx as integer),
    cast({{ candidate_alias }}.ny as integer),
    cast({{ candidate_alias }}.source_grid_place_id as varchar),
    cast({{ candidate_alias }}.issued_at as timestamp(6)),
    cast({{ candidate_alias }}.forecast_at as timestamp(6)),
    cast({{ candidate_alias }}.category as varchar),
    cast({{ candidate_alias }}.collected_at as timestamp(6)),
    cast({{ candidate_alias }}.published_at as timestamp(6)),
    cast({{ candidate_alias }}.fcst_value_raw as varchar),
    cast({{ candidate_alias }}.fcst_value_num as double),
    cast({{ candidate_alias }}.value_representation as varchar),
    cast({{ candidate_alias }}.value_num as double),
    cast({{ candidate_alias }}.value_lower_bound as double),
    cast({{ candidate_alias }}.value_upper_bound as double),
    cast({{ candidate_alias }}.qualitative_code as varchar),
    cast({{ candidate_alias }}.forecast_lead_hours as bigint),
    cast({{ candidate_alias }}.source_id as varchar),
    cast({{ candidate_alias }}.dag_run_id as varchar),
    cast({{ candidate_alias }}.raw_object_key as varchar),
    cast({{ candidate_alias }}.request_id as varchar)
) as row(
    admin_dong_code varchar,
    admin_dong varchar,
    gu_code varchar,
    gu varchar,
    admin_dong_revision_date date,
    bridge_version varchar,
    nx integer,
    ny integer,
    source_grid_place_id varchar,
    issued_at timestamp(6),
    forecast_at timestamp(6),
    category varchar,
    collected_at timestamp(6),
    published_at timestamp(6),
    fcst_value_raw varchar,
    fcst_value_num double,
    value_representation varchar,
    value_num double,
    value_lower_bound double,
    value_upper_bound double,
    qualitative_code varchar,
    forecast_lead_hours bigint,
    source_id varchar,
    dag_run_id varchar,
    raw_object_key varchar,
    request_id varchar
))
{%- endmacro %}

{% macro get_incremental_weather_w2_reconcile_sql(arg_dict) -%}
{%- do weather_w2_assert_gold_target() -%}
{%- set canonical_contract = weather_w2_canonical_contract() -%}
{%- set target_relation = arg_dict['target_relation'] -%}
{%- set temp_relation = arg_dict['temp_relation'] -%}
{%- set canonical_relation = ref('asac_axes', 'dim_admin_dong') -%}
{%- set repair_mode = weather_w2_is_repair() -%}
{%- if repair_mode -%}
    {%- set start_literal = weather_w2_repair_start_at() -%}
    {%- set cutoff_literal = weather_w2_publishable_cutoff_at() -%}
{%- endif -%}

{%- set preflight_sql -%}
with DBT_INTERNAL_CANONICAL as (
    select
        cast(admin_dong_code as varchar) as admin_dong_code,
        cast(admin_dong as varchar) as admin_dong,
        cast(gu_code as varchar) as gu_code,
        cast(gu as varchar) as gu,
        cast(revision_date as date) as admin_dong_revision_date
    from {{ canonical_relation }}
    where cast(revision_date as date) = date '{{ canonical_contract['revision_date'] }}'
),
temp_summary as (
    select
        count_if(
            admin_dong_code is null
            or forecast_at is null
            or category is null
            or product_row_id is null
        ) as null_grain_count,
        count_if(
            admin_dong is null
            or gu_code is null
            or gu is null
            or admin_dong_revision_date is null
            or bridge_version is null
            or issued_at is null
            or collected_at is null
            or published_at is null
            or value_representation is null
            or forecast_lead_hours is null
            or source_id is null
            or raw_object_key is null
            or request_id is null
            or dag_run_id is null
            or source_grid_place_id is null
            or nx is null
            or ny is null
        ) as null_lineage_count,
        {% if repair_mode %}
        count_if(
            published_at >= timestamp '{{ start_literal }}'
            and published_at <= timestamp '{{ cutoff_literal }}'
        )
        {% else %}
        cast(null as bigint)
        {% endif %} as in_window_expected_count
    from {{ temp_relation }}
),
temp_canonical_summary as (
    select
        count_if(
            canonical.admin_dong_code is null
            or temp.admin_dong is distinct from canonical.admin_dong
            or temp.gu_code is distinct from canonical.gu_code
            or temp.gu is distinct from canonical.gu
            or temp.admin_dong_revision_date is distinct from canonical.admin_dong_revision_date
        ) as temp_canonical_mismatch_count
    from {{ temp_relation }} as temp
    left join DBT_INTERNAL_CANONICAL as canonical
        on temp.admin_dong_code = canonical.admin_dong_code
),
canonical_summary as (
    select
        count(*) as canonical_count,
        count(distinct admin_dong_code) as canonical_code_count,
        count(distinct admin_dong_revision_date) as canonical_revision_count,
        min(admin_dong_revision_date) as canonical_min_revision,
        max(admin_dong_revision_date) as canonical_max_revision,
        count_if(
            admin_dong_code is null
            or admin_dong is null
            or gu_code is null
            or gu is null
            or admin_dong_revision_date is null
        ) as canonical_null_count
    from DBT_INTERNAL_CANONICAL
),
DBT_INTERNAL_AFFECTED_KEYS as (
    select distinct
        admin_dong_code,
        forecast_at,
        category
    from {{ temp_relation }}
),
affected_target_grain as (
    select
        target.admin_dong_code,
        target.forecast_at,
        target.category,
        count(*) as target_row_count,
        count_if(
            target.product_row_id is null
            or target.admin_dong is null
            or target.gu_code is null
            or target.gu is null
            or target.admin_dong_revision_date is null
            or target.bridge_version is null
            or target.nx is null
            or target.ny is null
            or target.source_grid_place_id is null
            or target.issued_at is null
            or target.collected_at is null
            or target.published_at is null
            or target.value_representation is null
            or target.forecast_lead_hours is null
            or target.source_id is null
            or target.dag_run_id is null
            or target.raw_object_key is null
            or target.request_id is null
        ) as affected_target_null_contract_count,
        count_if(
            canonical.admin_dong_code is null
            or target.admin_dong is distinct from canonical.admin_dong
            or target.gu_code is distinct from canonical.gu_code
            or target.gu is distinct from canonical.gu
            or target.admin_dong_revision_date
                is distinct from canonical.admin_dong_revision_date
        ) as affected_target_canonical_mismatch_count
    from {{ target_relation }} as target
    inner join DBT_INTERNAL_AFFECTED_KEYS as DBT_INTERNAL_KEY
        on DBT_INTERNAL_KEY.admin_dong_code = target.admin_dong_code
       and DBT_INTERNAL_KEY.forecast_at = target.forecast_at
       and DBT_INTERNAL_KEY.category = target.category
    left join DBT_INTERNAL_CANONICAL as canonical
        on target.admin_dong_code = canonical.admin_dong_code
    group by target.admin_dong_code, target.forecast_at, target.category
),
affected_target_summary as (
    select
        coalesce(sum(affected_target_null_contract_count), 0)
            as affected_target_null_contract_count,
        coalesce(sum(affected_target_canonical_mismatch_count), 0)
            as affected_target_canonical_mismatch_count,
        count_if(target_row_count > 1) as affected_target_duplicate_count
    from affected_target_grain
),
temp_duplicate_grain as (
    select admin_dong_code, forecast_at, category
    from {{ temp_relation }}
    group by admin_dong_code, forecast_at, category
    having count(*) > 1
)
select
    temp_summary.null_grain_count,
    temp_summary.null_lineage_count,
    temp_canonical_summary.temp_canonical_mismatch_count,
    affected_target_summary.affected_target_null_contract_count,
    affected_target_summary.affected_target_canonical_mismatch_count,
    (select count(*) from temp_duplicate_grain) as temp_duplicate_count,
    affected_target_summary.affected_target_duplicate_count,
    canonical_summary.canonical_count,
    canonical_summary.canonical_code_count,
    canonical_summary.canonical_revision_count,
    canonical_summary.canonical_min_revision,
    canonical_summary.canonical_max_revision,
    canonical_summary.canonical_null_count,
    temp_summary.in_window_expected_count
from temp_summary
cross join temp_canonical_summary
cross join affected_target_summary
cross join canonical_summary
{%- endset -%}
{%- set preflight = run_query(preflight_sql) -%}
{%- if preflight is none or preflight.rows | length != 1 -%}
    {{ exceptions.raise_compiler_error('Weather W2 Gold preflight query가 단일 summary를 반환하지 않았습니다.') }}
{%- endif -%}
{%- set preflight_row = preflight.rows[0] -%}
{%- set null_grain_count = preflight_row[0] | int -%}
{%- set null_lineage_count = preflight_row[1] | int -%}
{%- set temp_canonical_mismatch_count = preflight_row[2] | int -%}
{%- set affected_target_null_contract_count = preflight_row[3] | int -%}
{%- set affected_target_canonical_mismatch_count = preflight_row[4] | int -%}
{%- set temp_duplicate_count = preflight_row[5] | int -%}
{%- set affected_target_duplicate_count = preflight_row[6] | int -%}
{%- set canonical_count = preflight_row[7] | int -%}
{%- set canonical_code_count = preflight_row[8] | int -%}
{%- set canonical_revision_count = preflight_row[9] | int -%}
{%- set canonical_min_revision = preflight_row[10] | string -%}
{%- set canonical_max_revision = preflight_row[11] | string -%}
{%- set canonical_null_count = preflight_row[12] | int -%}
{%- set in_window_expected_count = preflight_row[13] | int if repair_mode else none -%}
{%- if null_grain_count > 0
    or null_lineage_count > 0
    or temp_canonical_mismatch_count > 0
    or affected_target_null_contract_count > 0
    or temp_duplicate_count > 0
    or affected_target_duplicate_count > 0
    or canonical_count != canonical_contract['canonical_count']
    or canonical_code_count != canonical_contract['canonical_count']
    or canonical_revision_count != 1
    or canonical_min_revision != canonical_contract['revision_date']
    or canonical_max_revision != canonical_contract['revision_date']
    or canonical_null_count > 0 -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 Gold preflight가 null grain/lineage 또는 duplicate grain을 발견했습니다.'
    ) }}
{%- endif -%}
{%- if affected_target_canonical_mismatch_count > 0 -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 target canonical revision이 승인 축과 다릅니다. 정규 run의 자동 restamp는 금지되며 명시적 keyed canonical migration이 필요합니다.'
    ) }}
{%- endif -%}
{%- if repair_mode and in_window_expected_count == 0 -%}
    {{ exceptions.raise_compiler_error(
        'Weather W2 bounded repair는 window 내부 expected Gold 행이 1개 이상이어야 합니다.'
    ) }}
{%- endif -%}

merge into {{ target_relation }} as DBT_INTERNAL_DEST
using (
    with
    {% if repair_mode %}
    DBT_INTERNAL_ELIGIBLE_ANCHORS as (
        select distinct
            cast(DBT_INTERNAL_ANCHOR_SOURCE.source_id as varchar) as anchor_source_id,
            cast(DBT_INTERNAL_ANCHOR_SOURCE.dag_run_id as varchar) as anchor_dag_run_id
        from {{ temp_relation }} as DBT_INTERNAL_ANCHOR_SOURCE
        where DBT_INTERNAL_ANCHOR_SOURCE.published_at
              >= timestamp '{{ weather_w2_repair_start_at() }}'
          and DBT_INTERNAL_ANCHOR_SOURCE.published_at
              <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
    ),
    DBT_INTERNAL_UPSERT_CLASSIFIED as (
        select
            DBT_INTERNAL_UPSERT.*,
            case
                when DBT_INTERNAL_CURRENT.admin_dong_code is not null
                 and DBT_INTERNAL_CURRENT.published_at
                     >= timestamp '{{ weather_w2_repair_start_at() }}'
                 and DBT_INTERNAL_CURRENT.published_at
                     <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
                 and DBT_INTERNAL_CURRENT_ANCHOR.anchor_source_id is null
                then true
                else false
            end as __w2_force_replace
        from {{ temp_relation }} as DBT_INTERNAL_UPSERT
        left join {{ target_relation }} as DBT_INTERNAL_CURRENT
            on DBT_INTERNAL_UPSERT.admin_dong_code = DBT_INTERNAL_CURRENT.admin_dong_code
           and DBT_INTERNAL_UPSERT.forecast_at = DBT_INTERNAL_CURRENT.forecast_at
           and DBT_INTERNAL_UPSERT.category = DBT_INTERNAL_CURRENT.category
        left join DBT_INTERNAL_ELIGIBLE_ANCHORS as DBT_INTERNAL_CURRENT_ANCHOR
            on DBT_INTERNAL_CURRENT.source_id = DBT_INTERNAL_CURRENT_ANCHOR.anchor_source_id
           and DBT_INTERNAL_CURRENT.dag_run_id = DBT_INTERNAL_CURRENT_ANCHOR.anchor_dag_run_id
    ),
    {% else %}
    DBT_INTERNAL_UPSERT_CLASSIFIED as (
        select
            DBT_INTERNAL_UPSERT.*,
            false as __w2_force_replace
        from {{ temp_relation }} as DBT_INTERNAL_UPSERT
    ),
    {% endif %}
    DBT_INTERNAL_UPSERT_ROWS as (
        select DBT_INTERNAL_SOURCE.*
        from DBT_INTERNAL_UPSERT_CLASSIFIED as DBT_INTERNAL_SOURCE
    )
    {% if repair_mode %}
    ,
    -- The complete desired key set inside the bounded repair window. Rows
    -- outside the window are retained by definition and never enter delete input.
    DBT_INTERNAL_DESIRED_KEYS as (
        select
            DBT_INTERNAL_DESIRED.admin_dong_code,
            DBT_INTERNAL_DESIRED.forecast_at,
            DBT_INTERNAL_DESIRED.category
        from {{ temp_relation }} as DBT_INTERNAL_DESIRED
    ),
    DBT_INTERNAL_DELETE_KEYS as (
        select distinct
            DBT_INTERNAL_DEST.admin_dong_code,
            DBT_INTERNAL_DEST.forecast_at,
            DBT_INTERNAL_DEST.category
        from {{ target_relation }} as DBT_INTERNAL_DEST
        where DBT_INTERNAL_DEST.published_at
                  >= timestamp '{{ weather_w2_repair_start_at() }}'
          and DBT_INTERNAL_DEST.published_at
                  <= timestamp '{{ weather_w2_publishable_cutoff_at() }}'
          and not exists (
              select 1
              from DBT_INTERNAL_DESIRED_KEYS as DBT_INTERNAL_DESIRED
              where DBT_INTERNAL_DESIRED.admin_dong_code
                        = DBT_INTERNAL_DEST.admin_dong_code
                and DBT_INTERNAL_DESIRED.forecast_at
                        = DBT_INTERNAL_DEST.forecast_at
                and DBT_INTERNAL_DESIRED.category
                        = DBT_INTERNAL_DEST.category
          )
    )
    {% endif %}
    select
        DBT_INTERNAL_UPSERT.product_row_id,
        DBT_INTERNAL_UPSERT.admin_dong_code,
        DBT_INTERNAL_UPSERT.forecast_at,
        DBT_INTERNAL_UPSERT.category,
        DBT_INTERNAL_UPSERT.admin_dong,
        DBT_INTERNAL_UPSERT.gu_code,
        DBT_INTERNAL_UPSERT.gu,
        DBT_INTERNAL_UPSERT.admin_dong_revision_date,
        DBT_INTERNAL_UPSERT.bridge_version,
        DBT_INTERNAL_UPSERT.nx,
        DBT_INTERNAL_UPSERT.ny,
        DBT_INTERNAL_UPSERT.source_grid_place_id,
        DBT_INTERNAL_UPSERT.issued_at,
        DBT_INTERNAL_UPSERT.collected_at,
        DBT_INTERNAL_UPSERT.published_at,
        DBT_INTERNAL_UPSERT.fcst_value_raw,
        DBT_INTERNAL_UPSERT.fcst_value_num,
        DBT_INTERNAL_UPSERT.value_representation,
        DBT_INTERNAL_UPSERT.value_num,
        DBT_INTERNAL_UPSERT.value_lower_bound,
        DBT_INTERNAL_UPSERT.value_upper_bound,
        DBT_INTERNAL_UPSERT.qualitative_code,
        DBT_INTERNAL_UPSERT.forecast_lead_hours,
        DBT_INTERNAL_UPSERT.source_id,
        DBT_INTERNAL_UPSERT.dag_run_id,
        DBT_INTERNAL_UPSERT.raw_object_key,
        false as __w2_delete,
        DBT_INTERNAL_UPSERT.__w2_force_replace,
        DBT_INTERNAL_UPSERT.request_id
    from DBT_INTERNAL_UPSERT_ROWS as DBT_INTERNAL_UPSERT
    {% if repair_mode %}
    union all
    select
        cast(null as varchar) as product_row_id,
        DBT_INTERNAL_DELETE.admin_dong_code,
        DBT_INTERNAL_DELETE.forecast_at,
        DBT_INTERNAL_DELETE.category,
        cast(null as varchar) as admin_dong,
        cast(null as varchar) as gu_code,
        cast(null as varchar) as gu,
        cast(null as date) as admin_dong_revision_date,
        cast(null as varchar) as bridge_version,
        cast(null as integer) as nx,
        cast(null as integer) as ny,
        cast(null as varchar) as source_grid_place_id,
        cast(null as timestamp(6)) as issued_at,
        cast(null as timestamp(6)) as collected_at,
        cast(null as timestamp(6)) as published_at,
        cast(null as varchar) as fcst_value_raw,
        cast(null as double) as fcst_value_num,
        cast(null as varchar) as value_representation,
        cast(null as double) as value_num,
        cast(null as double) as value_lower_bound,
        cast(null as double) as value_upper_bound,
        cast(null as varchar) as qualitative_code,
        cast(null as bigint) as forecast_lead_hours,
        cast(null as varchar) as source_id,
        cast(null as varchar) as dag_run_id,
        cast(null as varchar) as raw_object_key,
        true as __w2_delete,
        false as __w2_force_replace,
        cast(null as varchar) as request_id
    from DBT_INTERNAL_DELETE_KEYS as DBT_INTERNAL_DELETE
    {% endif %}
) as DBT_INTERNAL_SOURCE
on DBT_INTERNAL_SOURCE.admin_dong_code = DBT_INTERNAL_DEST.admin_dong_code
and DBT_INTERNAL_SOURCE.forecast_at = DBT_INTERNAL_DEST.forecast_at
and DBT_INTERNAL_SOURCE.category = DBT_INTERNAL_DEST.category
when matched and DBT_INTERNAL_SOURCE.__w2_delete then delete
when matched
  and not DBT_INTERNAL_SOURCE.__w2_delete
  and (
      DBT_INTERNAL_SOURCE.__w2_force_replace
      or {{ weather_w2_gold_winner_is_not_older(
          'DBT_INTERNAL_SOURCE', 'DBT_INTERNAL_DEST'
      ) }}
  )
  and (
      DBT_INTERNAL_DEST.product_row_id is distinct from DBT_INTERNAL_SOURCE.product_row_id
      or DBT_INTERNAL_DEST.admin_dong is distinct from DBT_INTERNAL_SOURCE.admin_dong
      or DBT_INTERNAL_DEST.gu_code is distinct from DBT_INTERNAL_SOURCE.gu_code
      or DBT_INTERNAL_DEST.gu is distinct from DBT_INTERNAL_SOURCE.gu
      or DBT_INTERNAL_DEST.admin_dong_revision_date is distinct from DBT_INTERNAL_SOURCE.admin_dong_revision_date
      or DBT_INTERNAL_DEST.bridge_version is distinct from DBT_INTERNAL_SOURCE.bridge_version
      or DBT_INTERNAL_DEST.nx is distinct from DBT_INTERNAL_SOURCE.nx
      or DBT_INTERNAL_DEST.ny is distinct from DBT_INTERNAL_SOURCE.ny
      or DBT_INTERNAL_DEST.source_grid_place_id is distinct from DBT_INTERNAL_SOURCE.source_grid_place_id
      or DBT_INTERNAL_DEST.issued_at is distinct from DBT_INTERNAL_SOURCE.issued_at
      or DBT_INTERNAL_DEST.collected_at is distinct from DBT_INTERNAL_SOURCE.collected_at
      or DBT_INTERNAL_DEST.published_at is distinct from DBT_INTERNAL_SOURCE.published_at
      or DBT_INTERNAL_DEST.fcst_value_raw is distinct from DBT_INTERNAL_SOURCE.fcst_value_raw
      or DBT_INTERNAL_DEST.fcst_value_num is distinct from DBT_INTERNAL_SOURCE.fcst_value_num
      or DBT_INTERNAL_DEST.value_representation is distinct from DBT_INTERNAL_SOURCE.value_representation
      or DBT_INTERNAL_DEST.value_num is distinct from DBT_INTERNAL_SOURCE.value_num
      or DBT_INTERNAL_DEST.value_lower_bound is distinct from DBT_INTERNAL_SOURCE.value_lower_bound
      or DBT_INTERNAL_DEST.value_upper_bound is distinct from DBT_INTERNAL_SOURCE.value_upper_bound
      or DBT_INTERNAL_DEST.qualitative_code is distinct from DBT_INTERNAL_SOURCE.qualitative_code
      or DBT_INTERNAL_DEST.forecast_lead_hours is distinct from DBT_INTERNAL_SOURCE.forecast_lead_hours
      or DBT_INTERNAL_DEST.source_id is distinct from DBT_INTERNAL_SOURCE.source_id
      or DBT_INTERNAL_DEST.dag_run_id is distinct from DBT_INTERNAL_SOURCE.dag_run_id
      or DBT_INTERNAL_DEST.raw_object_key is distinct from DBT_INTERNAL_SOURCE.raw_object_key
      or DBT_INTERNAL_DEST.request_id is distinct from DBT_INTERNAL_SOURCE.request_id
  )
then update set
    product_row_id = DBT_INTERNAL_SOURCE.product_row_id,
    admin_dong = DBT_INTERNAL_SOURCE.admin_dong,
    gu_code = DBT_INTERNAL_SOURCE.gu_code,
    gu = DBT_INTERNAL_SOURCE.gu,
    admin_dong_revision_date = DBT_INTERNAL_SOURCE.admin_dong_revision_date,
    bridge_version = DBT_INTERNAL_SOURCE.bridge_version,
    nx = DBT_INTERNAL_SOURCE.nx,
    ny = DBT_INTERNAL_SOURCE.ny,
    source_grid_place_id = DBT_INTERNAL_SOURCE.source_grid_place_id,
    issued_at = DBT_INTERNAL_SOURCE.issued_at,
    collected_at = DBT_INTERNAL_SOURCE.collected_at,
    published_at = DBT_INTERNAL_SOURCE.published_at,
    fcst_value_raw = DBT_INTERNAL_SOURCE.fcst_value_raw,
    fcst_value_num = DBT_INTERNAL_SOURCE.fcst_value_num,
    value_representation = DBT_INTERNAL_SOURCE.value_representation,
    value_num = DBT_INTERNAL_SOURCE.value_num,
    value_lower_bound = DBT_INTERNAL_SOURCE.value_lower_bound,
    value_upper_bound = DBT_INTERNAL_SOURCE.value_upper_bound,
    qualitative_code = DBT_INTERNAL_SOURCE.qualitative_code,
    forecast_lead_hours = DBT_INTERNAL_SOURCE.forecast_lead_hours,
    source_id = DBT_INTERNAL_SOURCE.source_id,
    dag_run_id = DBT_INTERNAL_SOURCE.dag_run_id,
    raw_object_key = DBT_INTERNAL_SOURCE.raw_object_key,
    request_id = DBT_INTERNAL_SOURCE.request_id
when not matched and not DBT_INTERNAL_SOURCE.__w2_delete then insert (
    product_row_id,
    admin_dong_code,
    forecast_at,
    category,
    admin_dong,
    gu_code,
    gu,
    admin_dong_revision_date,
    bridge_version,
    nx,
    ny,
    source_grid_place_id,
    issued_at,
    collected_at,
    published_at,
    fcst_value_raw,
    fcst_value_num,
    value_representation,
    value_num,
    value_lower_bound,
    value_upper_bound,
    qualitative_code,
    forecast_lead_hours,
    source_id,
    dag_run_id,
    raw_object_key,
    request_id
) values (
    DBT_INTERNAL_SOURCE.product_row_id,
    DBT_INTERNAL_SOURCE.admin_dong_code,
    DBT_INTERNAL_SOURCE.forecast_at,
    DBT_INTERNAL_SOURCE.category,
    DBT_INTERNAL_SOURCE.admin_dong,
    DBT_INTERNAL_SOURCE.gu_code,
    DBT_INTERNAL_SOURCE.gu,
    DBT_INTERNAL_SOURCE.admin_dong_revision_date,
    DBT_INTERNAL_SOURCE.bridge_version,
    DBT_INTERNAL_SOURCE.nx,
    DBT_INTERNAL_SOURCE.ny,
    DBT_INTERNAL_SOURCE.source_grid_place_id,
    DBT_INTERNAL_SOURCE.issued_at,
    DBT_INTERNAL_SOURCE.collected_at,
    DBT_INTERNAL_SOURCE.published_at,
    DBT_INTERNAL_SOURCE.fcst_value_raw,
    DBT_INTERNAL_SOURCE.fcst_value_num,
    DBT_INTERNAL_SOURCE.value_representation,
    DBT_INTERNAL_SOURCE.value_num,
    DBT_INTERNAL_SOURCE.value_lower_bound,
    DBT_INTERNAL_SOURCE.value_upper_bound,
    DBT_INTERNAL_SOURCE.qualitative_code,
    DBT_INTERNAL_SOURCE.forecast_lead_hours,
    DBT_INTERNAL_SOURCE.source_id,
    DBT_INTERNAL_SOURCE.dag_run_id,
    DBT_INTERNAL_SOURCE.raw_object_key,
    DBT_INTERNAL_SOURCE.request_id
)
{%- endmacro %}

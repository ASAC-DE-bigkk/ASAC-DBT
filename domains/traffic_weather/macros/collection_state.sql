{#
  Common collection-state projection for already materialized relations.

  The expected-slot relation is the source of truth for coverage.  The event
  relation is append-only, so the latest event is selected deterministically
  and timestamp ties remain visible through event_state_tie_count.  This macro
  intentionally has no schedule generation, environment lookup, or serving
  side effect.
#}
{% macro collection_slot_latest_state(expected_relation, event_relation) -%}
with expected_slots as (
    select
        cast(expected_slot_id as varchar) as expected_slot_id,
        cast(contract_version as varchar) as contract_version,
        cast(domain as varchar) as domain,
        cast(collection_contract_id as varchar) as collection_contract_id,
        cast(source_id as varchar) as source_id,
        cast(collection_slot_at as timestamp(6)) as collection_slot_at,
        cast(grain_key as varchar) as grain_key,
        cast(grain_json as varchar) as grain_json,
        cast(schedule_version as varchar) as schedule_version,
        cast(scheduled_at as timestamp(6)) as scheduled_at,
        cast(deadline_at as timestamp(6)) as deadline_at,
        cast(is_scheduled as boolean) as is_scheduled,
        cast(recovery_boundary_type as varchar) as recovery_boundary_type,
        cast(recovery_boundary as varchar) as recovery_boundary,
        cast(declared_at as timestamp(6)) as declared_at,
        cast(declared_by as varchar) as declared_by
    from {{ expected_relation }}
), ranked_events as (
    select
        cast(event_id as varchar) as event_id,
        cast(expected_slot_id as varchar) as expected_slot_id,
        cast(event_type as varchar) as event_type,
        cast(collection_state as varchar) as event_collection_state,
        cast(recovery_state as varchar) as event_recovery_state,
        cast(recovery_class as varchar) as event_recovery_class,
        cast(recovery_evidence_code as varchar) as recovery_evidence_code,
        cast(gap_reason_code as varchar) as event_gap_reason_code,
        cast(dag_id as varchar) as dag_id,
        cast(dag_run_id as varchar) as dag_run_id,
        cast(task_id as varchar) as task_id,
        cast(raw_manifest_key as varchar) as raw_manifest_key,
        cast(raw_object_count as bigint) as raw_object_count,
        cast(row_count as bigint) as row_count,
        cast(source_result_code as varchar) as source_result_code,
        cast(recovery_run_id as varchar) as recovery_run_id,
        cast(recovered_at as timestamp(6)) as recovered_at,
        cast(event_at as timestamp(6)) as event_at,
        count(*) over (
            partition by
                cast(expected_slot_id as varchar),
                cast(event_at as timestamp(6))
        ) as event_state_tie_count,
        row_number() over (
            partition by cast(expected_slot_id as varchar)
            order by
                cast(event_at as timestamp(6)) desc,
                cast(event_id as varchar) desc
        ) as event_rank
    from {{ event_relation }}
), latest_events as (
    select *
    from ranked_events
    where event_rank = 1
), projected as (
    select
        expected.*,
        latest.event_id,
        latest.event_type,
        latest.dag_id,
        latest.dag_run_id,
        latest.task_id,
        latest.raw_manifest_key,
        latest.raw_object_count,
        latest.row_count,
        latest.source_result_code,
        latest.recovery_run_id,
        latest.recovered_at,
        latest.recovery_evidence_code,
        latest.event_at,
        coalesce(latest.event_state_tie_count, 1) as event_state_tie_count,
        case
            when expected.is_scheduled = false then 'not_scheduled'
            when latest.expected_slot_id is null then 'missing_unknown'
            else latest.event_collection_state
        end as collection_state,
        case
            when expected.is_scheduled = false then 'not_required'
            when latest.expected_slot_id is null then 'pending'
            else coalesce(latest.event_recovery_state, 'pending')
        end as recovery_state,
        case
            when expected.is_scheduled = false then 'none'
            when latest.expected_slot_id is null then 'none'
            else coalesce(latest.event_recovery_class, 'none')
        end as recovery_class,
        case
            when expected.is_scheduled = false then cast(null as varchar)
            when latest.expected_slot_id is null then 'missing_event'
            else latest.event_gap_reason_code
        end as gap_reason_code
    from expected_slots as expected
    left join latest_events as latest
      on expected.expected_slot_id = latest.expected_slot_id
)
select *
from projected
{%- endmacro %}

{# Return violating rows; a valid relation produces zero rows. #}
{% macro collection_slot_state_assertions(relation, expected_domain) -%}
with state as (
    select
        *,
        count(*) over (
            partition by expected_slot_id
        ) as expected_slot_id_count
    from {{ relation }}
)
select *
from state
where expected_slot_id is null
   or expected_slot_id_count <> 1
   or domain is null
   or domain <> '{{ expected_domain }}'
   or source_id is null
   or collection_state is null
   or collection_state not in (
          'observed', 'source_empty_valid', 'collection_failed',
          'not_scheduled', 'missing_unknown'
      )
   or recovery_state is null
   or recovery_state not in (
          'not_required', 'pending', 'recovered', 'unrecoverable'
      )
   or recovery_class is null
   or recovery_class not in (
          'raw_replay', 'historical_query', 'rolling_window',
          'full_refresh', 'next_snapshot_diff', 'none'
      )
   or event_state_tie_count is null
   or event_state_tie_count <> 1
   or (
          collection_state in ('collection_failed', 'missing_unknown')
          and nullif(trim(cast(gap_reason_code as varchar)), '') is null
      )
   or (
          collection_state in ('observed', 'source_empty_valid')
          and (recovery_state <> 'not_required' or recovery_class <> 'none')
      )
   or (
          collection_state = 'not_scheduled'
          and (recovery_state <> 'not_required' or recovery_class <> 'none')
      )
   or (
          recovery_state = 'recovered'
          and (
              collection_state not in ('collection_failed', 'missing_unknown')
              or recovery_class = 'none'
          )
      )
   or (
          recovery_state = 'unrecoverable'
          and (
              collection_state not in ('collection_failed', 'missing_unknown')
              or recovery_class <> 'none'
          )
      )
   or (
          event_id is not null
          and event_at is null
      )
{%- endmacro %}

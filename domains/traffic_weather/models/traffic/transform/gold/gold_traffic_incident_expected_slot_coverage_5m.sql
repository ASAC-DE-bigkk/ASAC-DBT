-- Traffic expected-slot coverage is derived only from the materialized state Gold.

{{ config(
    materialized='table',
    tags=['ask_seoul_collection_state'],
    meta={
        'collection_coverage_product': true,
        'support_only': true,
        'serving_publication': false
    }
) }}

with state as (
    select
        cast(source_id as varchar) as source_id,
        cast(collection_slot_at as timestamp(6)) as collection_slot_at,
        cast(is_scheduled as boolean) as is_scheduled,
        cast(collection_state as varchar) as collection_state,
        cast(recovery_state as varchar) as recovery_state
    from {{ ref('gold_traffic_collection_slot_state') }}
),

classified as (
    select
        *,
        case
            when coalesce(is_scheduled, false)
             and coalesce(collection_state <> 'not_scheduled', false)
                then true
            else false
        end as is_eligible
    from state
),

aggregated as (
    select
        source_id,
        collection_slot_at,
        count(*) as expected_slot_count,
        count_if(collection_state = 'not_scheduled') as not_scheduled_count,
        count_if(is_eligible) as eligible_expected,
        count_if(is_eligible and collection_state = 'observed') as observed_count,
        count_if(is_eligible and collection_state = 'source_empty_valid')
            as source_empty_valid_count,
        count_if(is_eligible and collection_state = 'collection_failed')
            as collection_failed_count,
        count_if(is_eligible and collection_state = 'missing_unknown')
            as missing_unknown_count,
        count_if(is_eligible and recovery_state = 'recovered') as recovered_count,
        count_if(is_eligible and recovery_state = 'pending') as pending,
        count_if(is_eligible and recovery_state = 'unrecoverable') as unrecoverable
    from classified
    group by source_id, collection_slot_at
),

metrics as (
    select
        *,
        observed_count + source_empty_valid_count + recovered_count as covered
    from aggregated
)

select
    source_id,
    collection_slot_at,
    expected_slot_count,
    not_scheduled_count,
    eligible_expected,
    observed_count,
    source_empty_valid_count,
    collection_failed_count,
    missing_unknown_count,
    recovered_count,
    pending,
    unrecoverable,
    covered,
    case
        when eligible_expected = 0 then cast(0.0 as double)
        else cast(covered as double) / cast(eligible_expected as double)
    end as coverage_ratio,
    case
        when eligible_expected = 0 then 'not_scheduled'
        when unrecoverable > 0 then 'unrecoverable'
        when pending > 0 then 'pending'
        when covered = eligible_expected then 'covered'
        else 'partial'
    end as coverage_status
from metrics

-- Persistent Weather collection-state projection from materialized control evidence.
-- The expected-slot relation is the universe; dbt never invents schedule rows.

{{ config(
    materialized='table',
    tags=['ask_seoul_collection_state'],
    meta={
        'collection_state_product': true,
        'support_only': true,
        'serving_publication': false
    }
) }}

with projected as (
    {{ collection_slot_latest_state(
        source('collection_state_bronze', 'collection_expected_slot'),
        source('collection_state_bronze', 'collection_slot_event')
    ) }}
)

select *
from projected
where domain = 'weather'

{{ config(tags=['ask_seoul_collection_state']) }}

{{ collection_slot_state_assertions(ref('gold_traffic_collection_slot_state'), 'traffic') }}

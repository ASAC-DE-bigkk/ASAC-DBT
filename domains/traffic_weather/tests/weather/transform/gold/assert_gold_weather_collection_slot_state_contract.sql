{{ config(tags=['weather_gold_gate', 'ask_seoul_collection_state']) }}

{{ collection_slot_state_assertions(ref('gold_weather_collection_slot_state'), 'weather') }}

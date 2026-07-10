-- silver 는 자신이 처리한 시점(watermark = max(collected_at))까지의 최신 publishable
-- 레코드를 정확히 골랐는지 검증한다. transform 이 hourly cron 으로 돌면서(2026-07-10)
-- silver 가 bronze 절대 최신보다 최대 1시간 뒤처지는 것은 의도된 계약이므로,
-- watermark 이후에 수집된 bronze 배치는 비교 대상에서 제외한다(신선도는
-- dbt_source_freshness 가 별도 감시). 상한 없이 비교하면 5분 주기 bronze 와
-- 경합해 갓 커밋된 배치만큼 어긋난다 — 2026-07-10 03:10Z 첫 cron 런 FAIL 22 사례.

with silver_watermark as (
    select max(collected_at) as max_collected_at
    from {{ ref('silver_seoul_traffic_incident') }}
),

publishable_runs as (
    select distinct cast(dag_run_id as varchar) as dag_run_id
    from {{ source('traffic_bronze', 'collection_run_manifest') }}
    where source_id = 'seoul_traffic_incident'
      and status = 'SUCCESS'
      and is_publishable
),

bronze_candidates as (
    select
        cast(bronze.acc_id as varchar) as source_record_id,
        cast(bronze.request_id as varchar) as request_id,
        cast(bronze.raw_object_key as varchar) as raw_object_key,
        cast(bronze.collected_at as timestamp(6)) as collected_at,
        row_number() over (
            partition by cast(bronze.acc_id as varchar)
            order by
                cast(bronze.collected_at as timestamp(6)) desc,
                cast(bronze.raw_object_key as varchar) desc,
                cast(bronze.request_id as varchar) desc
        ) as row_num
    from {{ source('traffic_bronze', 'seoul_traffic_incident') }} as bronze
    inner join publishable_runs
        on cast(bronze.dag_run_id as varchar) = publishable_runs.dag_run_id
    where cast(bronze.result_code as varchar) = 'INFO-000'
      and cast(bronze.acc_id as varchar) is not null
      and {{ asac_axes.kst_at_from_parts('cast(bronze.occr_date as varchar)', 'cast(bronze.occr_time as varchar)') }} is not null
      and cast(bronze.collected_at as timestamp(6)) <= (select max_collected_at from silver_watermark)
),

bronze_latest as (
    select *
    from bronze_candidates
    where row_num = 1
)

select
    silver.source_record_id,
    silver.request_id as silver_request_id,
    bronze_latest.request_id as expected_request_id,
    silver.raw_object_key as silver_raw_object_key,
    bronze_latest.raw_object_key as expected_raw_object_key,
    silver.collected_at as silver_collected_at,
    bronze_latest.collected_at as expected_collected_at
from {{ ref('silver_seoul_traffic_incident') }} as silver
inner join bronze_latest
    on silver.source_record_id = bronze_latest.source_record_id
where silver.request_id <> bronze_latest.request_id
   or silver.raw_object_key <> bronze_latest.raw_object_key
   or silver.collected_at <> bronze_latest.collected_at

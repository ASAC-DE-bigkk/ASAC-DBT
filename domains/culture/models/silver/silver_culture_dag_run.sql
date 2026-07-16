-- silver: DAG run 그레인(dag_id × run_id). 소스가 이미 타입드+KST ISO 문자열(로더 stamp)이라
-- 캐스팅만. dedup 불필요(로더가 14일 윈도우 delete+insert 멱등). 도메인 중립.
{{ config(tags=['slo']) }}

with bronze as (
    select * from {{ source('culture_bronze', 'bronze_culture_dag_runs') }}
)

select
    domain,
    dag_id,
    run_id,
    state,
    run_type,
    (run_type = 'scheduled')                as is_scheduled,
    try(cast(start_at as timestamp(6)))     as started_at,
    try(cast(end_at as timestamp(6)))       as ended_at,
    try(cast(duration_sec as double))       as duration_sec,
    try(cast(load_date as date))            as load_date
from bronze

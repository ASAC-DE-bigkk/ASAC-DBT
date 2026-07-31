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
    -- 로더 stamp 는 오프셋 포함 ISO(…+09:00) — cast(varchar as timestamp) 는 못 파싱(#240).
    -- from_iso8601 로 tstz 를 얻고 KST 벽시계로 고정한다(설계: _at = KST).
    try(cast(from_iso8601_timestamp(start_at) at time zone 'Asia/Seoul' as timestamp(6)))
                                            as started_at,
    try(cast(from_iso8601_timestamp(end_at) at time zone 'Asia/Seoul' as timestamp(6)))
                                            as ended_at,
    try(cast(duration_sec as double))       as duration_sec,
    -- 재시도 축(#201·#633, #619 확정안 '지표'). run 의 state 만 보면 재시도로 살아난 런과
    -- 처음부터 깨끗한 런이 **둘 다 success** 라 구분되지 않는다 — KOPIS 400 이 7일 중 4일
    -- 재발하는 동안 성공률은 100% 였다. 로더는 이미 싣고 있었고 여기서 안 꺼내 쓰던 값이다.
    -- 집계가 없는 런(구 표·조인 실패)은 0 이 아니라 NULL — 0 은 "재시도 없었다"는 주장이다.
    try(cast(retried_tasks as bigint))      as retried_tasks,
    try(cast(max_try as bigint))            as max_try,
    try(cast(load_date as date))            as load_date
from bronze

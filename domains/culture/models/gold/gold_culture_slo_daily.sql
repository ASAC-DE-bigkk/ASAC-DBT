-- gold: 날짜 1행 SLO 사실. scheduled/eod 가용률 둘 다(분모 확정)·초록위장·적재추세.
-- 도메인 중립(domain 컬럼, culture 접두어 없는 metric). population 복사 채택 대비(§6).
-- 가용률(주간 99.5% 등)은 이 마트 위 window 쿼리 — gold 는 일 단위 사실만.
{{ config(tags=['slo']) }}

with runs as (
    select * from {{ ref('silver_culture_slo_run') }}
),

dag_runs as (
    select * from {{ ref('silver_culture_dag_run') }}
),

run_daily as (
    select
        domain,
        cast(load_date as date)                                              as event_date,
        -- 자정 스케줄런 기준(그 날 scheduled run 이 모두 통과). scheduled 없으면 null→false.
        bool_and(case when run_kind = 'scheduled' then slo_passed end)        as scheduled_slo_passed,
        -- 일 최종(그 날 아무 run 이든 하나라도 통과 = 복구 성공 인정).
        bool_or(slo_passed)                                                   as eod_slo_passed,
        max(coverage_pct)                                                     as best_coverage_pct,
        coalesce(sum(failed), 0)                                              as failed_dataset_count,
        coalesce(sum(violation_count), 0)                                     as violation_count,
        coalesce(max(total_rows), 0)                                          as total_rows,
        -- 초록 위장: raw 통과인데 expected=0 (Airflow success ∧ 전멸). 7/7 실사례.
        cast(sum(case when slo_passed_raw and coalesce(expected, 0) = 0 then 1 else 0 end) as bigint)
                                                                             as green_disguise_runs
    from runs
    group by domain, load_date
),

dag_daily as (
    select
        domain,
        cast(started_at as date)                                             as event_date,
        cast(count(case when dag_id = 'culture_transform' then 1 end) as bigint)  as transform_runs,
        bool_and(case when dag_id = 'culture_transform' then state = 'success' end) as transform_all_success,
        bool_or(dag_id = 'culture_maintenance' and state = 'success')         as maintenance_ran,
        sum(case when dag_id = 'culture_bronze' then coalesce(duration_sec, 0) else 0 end) / 60.0
                                                                             as ingest_duration_min
    from dag_runs
    where started_at is not null
    group by domain, cast(started_at as date)
)

select
    r.domain,
    r.event_date,
    coalesce(r.scheduled_slo_passed, false)                     as scheduled_slo_passed,
    coalesce(r.eod_slo_passed, false)                           as eod_slo_passed,
    cast(coalesce(r.best_coverage_pct, 0) as decimal(38, 18))   as best_coverage_pct,
    r.failed_dataset_count,
    r.violation_count,
    r.total_rows,
    cast(coalesce(d.ingest_duration_min, 0) as decimal(38, 18)) as ingest_duration_min,
    coalesce(d.transform_runs, 0)                               as transform_runs,
    coalesce(d.transform_all_success, false)                    as transform_all_success,
    coalesce(d.maintenance_ran, false)                          as maintenance_ran,
    r.green_disguise_runs
from run_daily r
left join dag_daily d
    on r.domain = d.domain and r.event_date = d.event_date

# gold_culture_slo_daily — 대표 쿼리 (SLO 마트 소비)

`gold_culture_slo_daily` 는 **날짜 1행**의 사실만 담는다. 가용률·추세 같은 **집계 지표는
이 표 위 window 쿼리**로 뽑는다(계획안 slide 9 "가용 99.5%" 의 실측).

## 주간 자정 수집 가용률

```sql
select
    count_if(scheduled_slo_passed) * 1.0 / count(*)  as scheduled_availability_7d,  -- 자정 스케줄런 기준
    count_if(eod_slo_passed)       * 1.0 / count(*)  as eod_availability_7d          -- 일 최종(복구 포함)
from culture.gold_culture_slo_daily
where domain = 'culture'
  and event_date >= current_date - interval '7' day;
```

## 적재 시간 추세 (병목 감시)

```sql
select event_date, ingest_duration_min
from culture.gold_culture_slo_daily
where domain = 'culture'
order by event_date desc
limit 14;   -- 7/5 14분 → 7/7 28분 같은 추이
```

## 초록 위장 감사 (Airflow success ∧ 실제 전멸)

```sql
select event_date, green_disguise_runs
from culture.gold_culture_slo_daily
where domain = 'culture' and green_disguise_runs > 0
order by event_date desc;   -- 7/7 = 1 이 회귀 케이스
```

## 데이터셋별 병목 (silver_culture_slo_dataset)

```sql
select dataset_name,
       avg(duration_sec) as avg_sec,
       max(duration_sec) as max_sec
from culture.silver_culture_slo_dataset
where load_date >= current_date - interval '7' day
group by dataset_name
order by avg_sec desc;
```

> dev 는 `iceberg_dev.culture.*`, prod 는 `iceberg.culture.*`. 위 예시는 스키마 한정 생략형.

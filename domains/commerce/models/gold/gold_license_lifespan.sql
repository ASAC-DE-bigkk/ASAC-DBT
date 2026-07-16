-- gold_license_lifespan — 업소 수명(개업→폐업 일수) 분포 × 업종 3단 × 자치구.
--
-- 인사이트(#discovery): "이 업종/지역 업소는 보통 몇 년 버티나" — 폐업 완결분(개업·폐업일 모두
-- 보유, 실측 1.7M)만으로 수명 통계(avg/p50/p90/조기폐업률). 생존곡선은 gold_license_cohort_survival.
-- materialized=table(소형 요약 — 전량 재계산=멱등, D1 은 스냅샷 교체).
-- 날짜: try(from_iso8601_date) 단순형(무효 날짜 NULL 처리 — Trino 482 복합식 버그 회피 규약).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with e as (
    select t.major, t.category, t.name_ko, e.dataset, e.gu, coalesce(e.gu_code, 'UNK') as gu_code,
           try(from_iso8601_date(case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$')
                                      then trim(e.apvpermymd) end)) as o_d,
           try(from_iso8601_date(case when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{4}-\d{2}-\d{2}$')
                                      then trim(e.dcbymd) end)) as c_d
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
),

life as (
    select major, category, name_ko, dataset, gu, gu_code,
           date_diff('day', o_d, c_d) as days
    from e
    where o_d is not null and c_d is not null
      and c_d >= o_d                                   -- 역전(원천 오류) 제외
)

select major, {{ label_major_ko('major') }} as major_ko,
       category, {{ label_category_ko('category') }} as category_ko,
       dataset, max(name_ko) as dataset_ko,
       gu_code, max(gu) as gu,
       count(*)                                   as n_closed,
       round(avg(days), 1)                        as avg_days,
       approx_percentile(days, 0.5)               as p50_days,
       approx_percentile(days, 0.9)               as p90_days,
       count_if(days < 365)                       as closed_within_1y,
       round(1.0 * count_if(days < 365) / count(*), 4)  as early_close_ratio,
       count_if(days >= 3650)                     as survived_10y_then_closed
from life
group by major, category, dataset, gu_code

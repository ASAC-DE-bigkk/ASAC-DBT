-- gold_license_cohort_survival — 개업연도 코호트 생존곡선 × 업종(대/중분류).
--
-- 인사이트(#discovery 최상위): "Y년에 개업한 업소가 k년 후 몇 % 생존하나" — 코호트 분석의 정본.
-- 연 단위 근사(생존판정 = 폐업연도-개업연도 > k, 폐업 없음=생존) — 문서 명시. 관측 가능한
-- k(현재연도-코호트연도)까지만 전개해 우측 검열(right-censoring) 왜곡을 차단한다.
--
-- 메모리 안전 2단 집계: ① (업종, 코호트연, 폐업연) 카운트로 축약(수만 행) ② k 전개 후 합산 —
-- 290만 행을 k배 전개하지 않는다. materialized=table(소형 — 과거 코호트도 매일 생존자가
-- 변하므로 스냅샷 재계산이 정합. D1 은 스냅샷 교체).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with e as (
    select t.major, t.category,
           substr(trim(e.apvpermymd), 1, 4) as cohort_y,
           case when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{4}') then substr(trim(e.dcbymd), 1, 4) end as close_y
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
    where regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$')
      and substr(trim(e.apvpermymd), 1, 4) between '1990' and
          substr(cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar), 1, 4)
),

-- ① 축약: (업종, 코호트, 폐업연) 카운트 — close_y null = 현재 생존
compact as (
    select major, category, cohort_y, close_y, count(*) as n
    from e group by 1, 2, 3, 4
),

now_y as (
    select cast(substr(cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar), 1, 4) as integer) as y
),

-- ② 관측 가능한 k(0~min(코호트 경과, 30)) 전개 후 생존 합산
expanded as (
    select c.major, c.category, c.cohort_y, k.years_elapsed,
           sum(c.n) as cohort_n,
           sum(case when c.close_y is null
                      or cast(c.close_y as integer) - cast(c.cohort_y as integer) > k.years_elapsed
                    then c.n else 0 end) as survivors
    from compact c
    cross join now_y
    cross join unnest(sequence(0, 30)) as k(years_elapsed)
    where k.years_elapsed <= now_y.y - cast(c.cohort_y as integer)
    group by 1, 2, 3, 4
)

select major, {{ label_major_ko('major') }} as major_ko,
       category, {{ label_category_ko('category') }} as category_ko,
       cast(cohort_y as integer) as cohort_y, years_elapsed,
       cohort_n, survivors,
       round(1.0 * survivors / cohort_n, 4) as survival_rate
from expanded
where cohort_n > 0

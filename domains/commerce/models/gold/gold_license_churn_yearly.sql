-- gold_license_churn_yearly — 연도별 순증·교체율·신생비 × 업종 3단 × 자치구.
--
-- 인사이트(#discovery/churn): flow(개업/폐업 절대수)를 넘어선 **파생 비율** — 순증(net),
-- 교체율(그 해 폐업 / 그 해 시작 시점 영업스톡 근사), 신생비(그 해 개업 / 스톡).
-- 스톡 근사 = 해당 연도 이전 개업 − 이전 폐업(연 단위 문자열 연산 — 문서 규약).
-- 완결연도만. materialized=table(소형 — 과거 연도도 소급 신고로 변하므로 스냅샷 재계산).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with e as (
    select t.major, t.category, e.dataset, coalesce(e.gu_code, 'UNK') as gu_code,
           t.name_ko, e.gu,
           case when regexp_like(trim(coalesce(e.apvpermymd,'')), '^\d{4}-\d{2}-\d{2}$')
                then substr(trim(e.apvpermymd), 1, 4) end as o_y,
           case when regexp_like(trim(coalesce(e.dcbymd,'')), '^\d{4}')
                then substr(trim(e.dcbymd), 1, 4) end as c_y
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
),

years as (
    -- 최근 20개 완결연도
    select cast(y as varchar) as y
    from unnest(sequence(
        cast(substr(cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar), 1, 4) as integer) - 20,
        cast(substr(cast(cast(current_timestamp at time zone 'Asia/Seoul' as date) as varchar), 1, 4) as integer) - 1
    )) as t(y)
),

agg as (
    select y.y, e.major, e.category, e.dataset, e.gu_code,
           max(e.name_ko) as name_ko, max(e.gu) as gu,
           count_if(e.o_y = y.y)                          as opened,
           count_if(e.c_y = y.y)                          as closed,
           count_if(e.o_y < y.y and (e.c_y is null or e.c_y >= y.y)) as stock_start
    from e cross join years y
    where e.o_y is not null
    group by 1, 2, 3, 4, 5
)

select y, major, {{ label_major_ko('major') }} as major_ko,
       category, {{ label_category_ko('category') }} as category_ko,
       dataset, name_ko as dataset_ko, gu_code, gu,
       opened, closed,
       opened - closed                                            as net_change,
       stock_start,
       case when stock_start > 0 then round(1.0 * closed / stock_start, 4) end as churn_rate,
       case when stock_start > 0 then round(1.0 * opened / stock_start, 4) end as birth_rate
from agg
where opened > 0 or closed > 0 or stock_start > 0

-- gold_license_gu_specialization — 자치구 업종 특화지수(LQ) + 구성비.
--
-- 인사이트(#discovery/geo): "이 구는 어떤 업종에 특화됐나" — LQ(입지계수) = (구의 업종 비중) /
-- (서울 전체 업종 비중). LQ>1 = 서울 평균보다 그 업종이 밀집. 영업 중(01) 스톡 기준.
-- materialized=table(소형 스냅샷. D1 은 스냅샷 교체).

{{ config(materialized='table', tags=['gold', 'insight']) }}

with active as (
    select t.major, t.category, coalesce(e.gu_code, 'UNK') as gu_code, max(e.gu) as gu,
           count(*) as n
    from {{ ref('silver_license_entity') }} e
    join {{ ref('commerce_dataset_taxonomy') }} t on t.short = e.dataset
    where substr(trim(coalesce(e.trdstategbn, '')), 1, 2) = '01'
    group by 1, 2, 3
),

totals as (
    select gu_code, sum(n) as gu_total from active group by 1
),

seoul as (
    select category, sum(n) as seoul_cat_n from active group by 1
),

seoul_all as (
    select sum(n) as seoul_total from active
)

select a.gu_code, max(a.gu) as gu, a.major, a.category,
       sum(a.n)                                          as active_cnt,
       round(1.0 * sum(a.n) / max(t.gu_total), 4)        as share_in_gu,
       round((1.0 * sum(a.n) / max(t.gu_total))
             / (1.0 * max(s.seoul_cat_n) / max(sa.seoul_total)), 3) as lq
from active a
join totals t on t.gu_code = a.gu_code
join seoul  s on s.category = a.category
cross join seoul_all sa
group by a.gu_code, a.major, a.category

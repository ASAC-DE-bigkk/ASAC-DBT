-- gold: 일별 서울/전국 영화 관객 비중 ("서울 쏠림"). 그레인 = boxoffice_date (날짜 1행).
-- 서울 top10 ≠ 전국 top10(서로 다른 영화 집합) → 비중 = top10 관객 합의 비율.
-- 공간 시도(서울시)까지라 자치구 gold 미편입 — 일 단위 서울 영화소비 축 전용.

with bo as (
    select region, boxoffice_date, rank, movie_nm, audience_count
    from {{ ref('silver_culture_movie_boxoffice') }}
),

agg as (
    select
        boxoffice_date,
        sum(case when region = 'nation' then audience_count end)        as nation_top_audience,
        sum(case when region = 'seoul'  then audience_count end)        as seoul_top_audience,
        max(case when region = 'nation' and rank = 1 then movie_nm end) as nation_top_movie,
        max(case when region = 'seoul'  and rank = 1 then movie_nm end) as seoul_top_movie
    from bo
    group by boxoffice_date
)

select
    boxoffice_date,
    nation_top_audience,
    seoul_top_audience,
    round(1.0 * seoul_top_audience / nullif(nation_top_audience, 0), 3) as seoul_audience_share,
    nation_top_movie,
    seoul_top_movie
from agg

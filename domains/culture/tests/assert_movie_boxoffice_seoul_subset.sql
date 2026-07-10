-- AC 불변식: 같은 관객일·영화(movie_cd)가 전국·서울 양쪽 top10에 있으면 서울 관객 ≤ 전국 관객(서울⊂전국).
-- 위반 행이 있으면 실패(>0행).
with nation as (
    select boxoffice_date, movie_cd, audience_count
    from {{ ref('silver_culture_movie_boxoffice') }} where region = 'nation'
),
seoul as (
    select boxoffice_date, movie_cd, audience_count
    from {{ ref('silver_culture_movie_boxoffice') }} where region = 'seoul'
)
select
    s.boxoffice_date, s.movie_cd,
    s.audience_count as seoul_audience, n.audience_count as nation_audience
from seoul s
join nation n on s.boxoffice_date = n.boxoffice_date and s.movie_cd = n.movie_cd
where s.audience_count > n.audience_count

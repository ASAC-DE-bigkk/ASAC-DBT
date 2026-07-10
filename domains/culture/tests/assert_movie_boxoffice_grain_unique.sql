-- 영화 박스오피스 그레인 (region, boxoffice_date, rank) 유일성 단언. 중복(>0행)이면 실패.
select region, boxoffice_date, rank, count(*) as n
from {{ ref('silver_culture_movie_boxoffice') }}
group by region, boxoffice_date, rank
having count(*) > 1

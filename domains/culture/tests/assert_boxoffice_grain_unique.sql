-- 랭킹 그레인 (load_date, rank_no) 유일성 단언.
select load_date, rank_no, count(*) as n
from {{ ref('silver_culture_boxoffice') }}
group by load_date, rank_no
having count(*) > 1

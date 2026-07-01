-- boxoffice gold 그레인(snapshot_date × rank_no) 유일성 단언. 중복 행이 있으면 실패(>0행).
select
    snapshot_date,
    rank_no,
    count(*) as n
from {{ ref('gold_culture_boxoffice_daily') }}
group by snapshot_date, rank_no
having count(*) > 1

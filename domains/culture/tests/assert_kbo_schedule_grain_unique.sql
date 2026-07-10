-- KBO 일정 그레인 (game_date, stadium, game_time) 유일성 단언 — 더블헤더는 시각으로 구분.
select game_date, stadium, game_time, count(*) as n
from {{ ref('kbo_seoul_schedule') }}
group by game_date, stadium, game_time
having count(*) > 1

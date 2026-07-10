-- silver: KBO 서울 홈경기 일정 fact (잠실 LG/두산·고척 키움). 원천 = seed(공개 일정 수기, 월 1회 갱신).
-- 그레인 = (game_date, stadium, game_time) — 더블헤더는 시각으로 구분.
-- 문화행사 축과 분리(sports 구분): gold_culture_location_daily union에 편입하지 않는다.
-- bronze 계보 없음 → source_system='kbo_seed' 상수만.

with placed as (
    select
        s.game_date,
        s.game_time,
        s.stadium,
        s.home_team,
        s.away_team,
        l.gu,
        l.latitude,
        l.longitude
    from {{ ref('kbo_seoul_schedule') }} s
    left join {{ ref('kbo_stadium_location') }} l on l.stadium = s.stadium
),

dong_map as {{ culture_dong_map('placed') }},

{{ culture_admin_canon() }}

select
    p.game_date,
    p.game_time,
    p.stadium,
    p.home_team,
    p.away_team,
    try(cast(date_parse(cast(p.game_date as varchar) || ' ' || p.game_time, '%Y-%m-%d %H:%i') as timestamp(6))) as event_at,
    p.longitude, p.latitude, p.gu,
    coalesce(cd.gu_code, cg.gu_code, d.coord_gu_code) as gu_code,
    coalesce(cd.admin_dong, d.admin_dong) as admin_dong, d.admin_dong_code,
    'kbo_seed' as source_system
from placed p
left join dong_map d on p.longitude = d.longitude and p.latitude = d.latitude
left join canon cd on cd.admin_dong_code = d.admin_dong_code
left join canon_gu cg on cg.gu = p.gu

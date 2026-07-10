-- gold: 서울 야구 경기 일정 질의 표면 (경기 1행). "오늘 이후 가장 가까운 경기" =
--   where game_date >= current_date order by event_at limit 1
-- 문화행사 gold(location_daily)와 분리 — 시각·대진 그레인이 필요해 집계하지 않는다.

select
    game_date,
    event_at,
    game_time,
    stadium,
    home_team,
    away_team,
    gu,
    gu_code,
    latitude,
    longitude,
    admin_dong,
    admin_dong_code
from {{ ref('silver_culture_sports_event') }}

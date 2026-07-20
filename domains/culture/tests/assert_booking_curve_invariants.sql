-- booking_curve 불변식(#274): best_rank 는 최소이므로 first/last 이하, days_to_peak≥0,
--   days_on_chart≥1, best_rank_date 는 first~last 범위 안. 위반 행 하나라도 있으면 실패.
select
    performance_id, best_rank, first_rank, last_rank,
    days_to_peak, days_on_chart, first_seen_date, best_rank_date, last_seen_date
from {{ ref('gold_culture_booking_curve') }}
where best_rank > first_rank
   or best_rank > last_rank
   or days_to_peak < 0
   or days_on_chart < 1
   or best_rank_date < first_seen_date
   or best_rank_date > last_seen_date

-- #308: dine_around 정합 — pctl/score 범위(0~1)와 has_dining_data ↔ null 동조. 위반 행 반환 시 실패.
select *
from {{ ref('gold_culture_dine_around') }}
where (culture_events_pctl < 0 or culture_events_pctl > 1)
   or (dining_stock_pctl is not null and (dining_stock_pctl < 0 or dining_stock_pctl > 1))
   or (dine_around_score is not null and (dine_around_score < 0 or dine_around_score > 1))
   or (has_dining_data and (dining_active_cnt is null or dining_stock_pctl is null or dine_around_score is null))
   or ((not has_dining_data) and (dining_active_cnt is not null or dining_stock_pctl is not null or dine_around_score is not null))

-- free/edu 카운트 불변식(#280): event 부분집합이므로 events_count 이하 + 비음수.
select admin_dong_code, event_date
from {{ ref('gold_culture_activity_by_dong') }}
where free_events_count > events_count
   or edu_experience_events_count > events_count
   or free_events_count < 0
   or edu_experience_events_count < 0

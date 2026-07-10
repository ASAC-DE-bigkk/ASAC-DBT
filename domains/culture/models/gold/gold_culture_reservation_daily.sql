-- gold: gu_code × 스냅샷일 공공예약 가용 현황. 가용률 = 접수중/전체.

with svc as (
    select * from {{ ref('silver_culture_reservation') }}
    where gu_code is not null
)

select
    gu_code,
    max(gu) as gu,
    load_date as snapshot_date,
    count(*)                                                  as total_services,
    count(case when reservation_type = 'culture' then 1 end) as culture_services,
    count(case when reservation_type = 'sport' then 1 end)   as sport_services,
    count(case when status = '접수중' then 1 end)            as open_services,
    round(1.0 * count(case when status = '접수중' then 1 end) / nullif(count(*), 0), 3) as availability_rate,
    count(case when quality_status = 'dong_precise' then 1 end) as dong_precise_count
from svc
group by gu_code, load_date

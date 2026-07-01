-- gold: 자치구 × 스냅샷일 공공예약 가용 현황 (스냅샷 append).
-- 구간형 gold_culture_location_daily 와 그레인이 다르다(여기는 적재 스냅샷 일자 기준 상태).
-- 가용률(availability_rate) = 접수중 서비스 / 전체 서비스. (명시적 충원율 미제공 대체 지표)
-- 그레인: location_key(자치구) × snapshot_date.

with svc as (
    select *
    from {{ ref('silver_culture_reservation') }}
    where location_key is not null
)

select
    location_key,
    load_date as snapshot_date,
    count(*)                                                          as total_services,
    count(case when reservation_type = 'culture' then 1 end)         as culture_services,
    count(case when reservation_type = 'sport' then 1 end)           as sport_services,
    count(case when status = '접수중' then 1 end)                    as open_services,
    round(
        1.0 * count(case when status = '접수중' then 1 end) / nullif(count(*), 0),
        3
    )                                                                as availability_rate
from svc
group by location_key, load_date

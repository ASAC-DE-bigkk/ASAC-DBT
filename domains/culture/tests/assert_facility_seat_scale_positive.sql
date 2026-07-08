-- seat_scale 정규화 계약: 값이 있으면 양수여야 한다(0/공백 미상은 이미 null 로 치환).
-- KOPIS seatscale 이 음수나 0 을 실어 보내면(스키마 오염) 여기서 잡는다.
select facility_id, seat_scale
from {{ ref('silver_culture_facility') }}
where seat_scale is not null
  and seat_scale <= 0

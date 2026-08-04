-- dim_transit_parking: 주소 자치구 토큰(addr_gu)과 경계 point-in-polygon 조인 자치구(gu)의 일치 검증.
-- 좌표·주소가 모두 있는 행에서 불일치 시 반환 → warn(소수 경계 근처 오배정 허용).
{{ config(severity='warn', tags=['hourly']) }}
select
    parking_id,
    addr_gu,
    gu,
    addr
from {{ ref('dim_transit_parking') }}
where addr_gu is not null
  and gu is not null
  and addr_gu <> gu

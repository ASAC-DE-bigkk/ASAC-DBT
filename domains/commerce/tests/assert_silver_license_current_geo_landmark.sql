-- 좌표 변환 회귀 가드(warn): 서울시청(세종대로 110) 레코드의 변환 위경도가 실좌표
-- (37.5663, 126.9779) 인근(±0.005° ≈ 500m)이어야 한다. EPSG:5174 판별/파라미터가
-- 회귀하면(예: 2097 로 바뀌면 경도 -257m 시프트) 이 테스트가 경고를 낸다.
-- 데이터 의존(시청 인허가 행 존재 전제)이라 error 가 아닌 warn 으로 둔다.
{{ config(severity='warn') }}

select dataset, mgtno, road_address, latitude, longitude
from {{ ref('silver_license_current') }}
where road_address like '서울특별시 중구 세종대로 110,%'
  and latitude is not null
  and (abs(latitude - 37.5666) > 0.005 or abs(longitude - 126.9782) > 0.005)

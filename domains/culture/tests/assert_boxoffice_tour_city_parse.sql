-- tour_city 파싱 정합(#509) — silver 의 tour_city 는 같은 행 performance_name 에
-- 동일 정규식을 다시 걸어 나온 값과 정확히 일치해야 한다(파서 회귀 오라클).
--
-- #116 리뷰 교정: 이전 LIKE 비교는 대괄호 안 공백에서 오탐(trim 차이),
-- tour_city 에 %·_ 유입 시 미탐(와일드카드) 결함이 있었다 — 재계산 등가 비교는
-- 두 문제가 구조적으로 없다.

select rank_no, load_date, performance_name, tour_city
from {{ ref('silver_culture_boxoffice') }}
where tour_city is distinct from
      nullif(trim(regexp_extract(trim(performance_name), '\[([^\[\]]+)\]$', 1)), '')

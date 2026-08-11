-- tour_city 파싱 정합(#509) — tour_city 는 반드시 공연명 끝 "[tour_city]" 접미사에서
-- 왔어야 하고, 괄호 문자를 포함할 수 없다. 위반 행이 있으면 파서 회귀.

select rank_no, load_date, performance_name, tour_city
from {{ ref('silver_culture_boxoffice') }}
where tour_city is not null
  and (
        tour_city like '%[%' or tour_city like '%]%'
        or performance_name not like '%[' || tour_city || ']'
      )

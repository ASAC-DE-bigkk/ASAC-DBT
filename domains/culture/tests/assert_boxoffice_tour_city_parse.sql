-- tour_city 파싱 정합(#509) — tour_city 는 반드시 공연명 끝 "[tour_city]" 접미사에서
-- 왔어야 하고, 괄호 문자를 포함할 수 없다. 위반 행이 있으면 파서 회귀.
--
-- 🔴 원문 대조는 **다듬은 뒤** 한다. 모델은 추출값을 `trim` 해서 저장하는데(그게 맞다),
--    원문에는 `[서울 (앵콜) ]` 처럼 닫는 대괄호 앞에 공백이 있는 제목이 있다. 원문을
--    그대로 재구성해 비교하면 그 한 칸 때문에 **정상 파싱이 위반으로 잡힌다**
--    (2026-08-11 운영 실측 99행 · 공연 4편). 파서가 아니라 이 단언이 틀렸던 자리다.
--
-- 느슨해진 건 공백뿐이고, 잡아야 할 회귀는 그대로 잡는다:
--   · 접미사가 아예 없는데 tour_city 가 채워짐  → 두 번째 조건(추출 결과 NULL)
--   · 다른 자리·다른 필드에서 값을 가져옴        → 세 번째 조건(추출값 ≠ 저장값)
--   · 대괄호 문자가 값에 섞임                     → 첫 번째 조건

with parsed as (
    select
        rank_no, load_date, performance_name, tour_city,
        -- 모델과 같은 규칙으로 다시 뽑는다 — "저장값이 이 접미사에서 왔나"를 묻는 게 이 테스트다
        nullif(trim(regexp_extract(trim(performance_name), '\[([^\[\]]+)\]$', 1)), '') as suffix
    from {{ ref('silver_culture_boxoffice') }}
    where tour_city is not null
)

select rank_no, load_date, performance_name, tour_city, suffix
from parsed
where tour_city like '%[%' or tour_city like '%]%'   -- 값에 대괄호가 섞였다
   or suffix is null                                  -- 접미사가 없는데 값이 있다
   or suffix <> tour_city                             -- 접미사와 저장값이 다르다

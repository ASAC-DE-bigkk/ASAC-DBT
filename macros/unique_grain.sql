-- 복합 grain 유일성 제네릭 테스트 (dbt_utils 미사용 — 자체 구현).
-- incremental merge 중복 누적 같은 회귀를 grain 단위로 잡는다.
-- 사용(schema.yml):
--   data_tests:
--     - unique_grain:
--         arguments:
--           columns: [area_cd, event_at]
-- 반환 행(중복 grain)이 있으면 테스트 실패.
{% test unique_grain(model, columns) %}

select {{ columns | join(', ') }}
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1

{% endtest %}

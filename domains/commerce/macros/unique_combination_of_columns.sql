{#
  복합키(grain) 유일성 generic test — commerce 자체 구현.
  commerce dbt 프로젝트는 외부 패키지(dbt_utils) 무의존 방침이라 동등 테스트를 자체 매크로로 둔다.
  용도: 도메인 공통 Serving Contract(ASAC-DAG #478, docs/contracts/serving-contract-v1.md)의
  primary_key 복합키 근거. ASAC-DBT serving_contract Validator 는 모델레벨 test 이름에
  "unique_combination" 이 포함되면 복합 PK 근거로 인정한다.
  gold 집계는 combination_of_columns 로 GROUP BY 되므로 이 테스트는 구조적으로 통과한다(중복=0).
#}
{% test unique_combination_of_columns(model, combination_of_columns) %}

with validation as (
    select
        {{ combination_of_columns | join(', ') }},
        count(*) as n_rows
    from {{ model }}
    group by {{ combination_of_columns | join(', ') }}
    having count(*) > 1
)

select * from validation

{% endtest %}

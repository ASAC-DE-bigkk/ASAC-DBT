{#- R2 Data Catalog 뷰 이름 툼스톤 우회 (2026-07-28, #525 계열 벤더 이슈).

    Trino OOM 크래시(05:56Z) 잔재로 `silver_transit_subway_arrival__dbt_tmp` 이름이
    카탈로그 내부 불일치 상태로 봉인됨 — 실측: list/GET/DELETE 는 404 인데
    CREATE(Trino·REST POST 모두)는 409 EntityAlreadyExists
    (R2 지원 문의용 stack id: 019fa7b5-c89b-7f12-924b-3fdc5252d4d5).

    dbt-trino incremental 은 merge 스테이징을 `<model>__dbt_tmp` 뷰로 만들므로
    접미사에 `_r1` 을 더해 봉인된 이름을 피한다. 프로젝트 전 모델의 tmp 이름이
    함께 바뀌지만 tmp 는 런 종료 시 drop 되는 일회성 이름이라 영향 없음.
    벤더가 봉인 해소를 확인해 주기 전에는 되돌리지 말 것. -#}
{% macro trino__make_temp_relation(base_relation, suffix) %}
    {%- set temp_identifier = base_relation.identifier ~ suffix ~ '_r1' -%}
    {%- set temp_relation = base_relation.incorporate(
                                path={"identifier": temp_identifier}) -%}

    {{ return(temp_relation) }}
{% endmacro %}

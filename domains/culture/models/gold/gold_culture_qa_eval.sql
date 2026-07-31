-- gold(Q&A 거버넌스): 페르소나 질문 카탈로그 × 라우팅 실측(티어링 #20, #284). 그레인 question_id.
-- 계획안 "답 가능 → 평가셋(커버리지%), 답 불가 → 로드맵"의 데이터 구현 — W7 에이전트 트랙의 입력.
-- answerable(큐레이션 의도) vs mart_exists(information_schema 실측) 분리 —
--   라우팅 대상 마트가 rename/drop 되면 eval_ready가 자동으로 꺼져 드리프트가 드러난다(governed).
-- 커버리지 소비 예: count_if(eval_ready)/count_if(answerable)=라우팅 건전성,
--   count_if(answerable)/count(*)=질문 커버리지. meta.external=false(내부 전용).

with q as (
    select * from {{ ref('seed_culture_qa_questions') }}
),

-- 현행 카탈로그의 실존 테이블 — 티어링 v2(#310)부터 채택 마트(타 도메인 소유, Q&A 소비)도
--   라우팅 대상이라 검사 스코프 = culture + 채택 도메인 스키마. read 전용(information_schema).
--
-- 스코프를 **컴파일 시점에 실존 스키마로 좁힌다**. 없는 스키마 이름을 그대로 술어에 넣으면
-- R2 Data Catalog 가 빈 목록이 아니라 오류를 던진다(ICEBERG_CATALOG_ERROR "Failed to list views").
-- 2026-07-28 prod(iceberg) 실측: weather·transit 미진입 → 모델 빌드 실패. `system` 도 같은 오류라
-- 서브쿼리(`in (select … from schemata)`)로는 못 피한다 — Trino 가 술어를 밀어넣지 못하고 전 스키마를
-- 훑기 때문. 그래서 리터럴 목록으로 굳혀 넣는다. 미진입 도메인의 마트는 자연히 mart_exists=false 가
-- 되고, 그게 이 모델이 원래 드러내려는 드리프트 신호와 같은 의미다.
{%- set wanted = [
    target.schema,
    env_var("SEOUL_CITYDATA_SCHEMA", "seoul_citydata"),
    env_var("WEATHER_SCHEMA", "weather"),
    env_var("TRANSIT_SCHEMA", "transit"),
] %}
{%- set scoped = [] %}
{%- if execute %}
  {%- set present = run_query(
        "select schema_name from " ~ target.database ~ ".information_schema.schemata"
     ).columns[0].values() %}
  {%- for s in wanted %}
    {%- if s in present and s not in scoped %}{% do scoped.append(s) %}{% endif %}
  {%- endfor %}
{%- else %}
  {%- do scoped.append(target.schema) %}
{%- endif %}
{#- 최초 빌드로 자기 스키마조차 없을 때 `in ()` 문법 오류를 막는다(결과는 마트 0개 = mart_exists 전부 false). -#}
{%- if scoped | length == 0 %}{% do scoped.append(target.schema) %}{% endif %}
marts as (
    select distinct table_name
    from {{ target.database }}.information_schema.tables
    where table_schema in (
        {%- for s in scoped %}'{{ s }}'{{ "," if not loop.last }}{% endfor %}
    )
),

joined as (
    select
        q.question_id,
        q.persona_uuid,
        q.persona_summary,
        q.home_region,
        q.visit_context,
        q.persona_lens,
        q.question_text,
        q.target_mart,
        q.target_columns,
        q.answerable,
        q.unanswerable_reason,
        (m.table_name is not null)                  as mart_exists,
        (q.answerable and m.table_name is not null) as eval_ready
    from q
    left join marts m on m.table_name = q.target_mart
)

select * from joined

-- gold(Q&A 거버넌스): 페르소나 질문 카탈로그 × 라우팅 실측(티어링 #20, #284). 그레인 question_id.
-- 계획안 "답 가능 → 평가셋(커버리지%), 답 불가 → 로드맵"의 데이터 구현 — W7 에이전트 트랙의 입력.
-- answerable(큐레이션 의도) vs mart_exists(information_schema 실측) 분리 —
--   라우팅 대상 마트가 rename/drop 되면 eval_ready가 자동으로 꺼져 드리프트가 드러난다(governed).
-- 커버리지 소비 예: count_if(eval_ready)/count_if(answerable)=라우팅 건전성,
--   count_if(answerable)/count(*)=질문 커버리지. meta.external=false(내부 전용).

with q as (
    select * from {{ ref('seed_culture_qa_questions') }}
),

-- 현행 카탈로그의 실존 테이블(스키마 = 이 타깃의 culture 스키마)
marts as (
    select table_name
    from {{ target.database }}.information_schema.tables
    where table_schema = '{{ target.schema }}'
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

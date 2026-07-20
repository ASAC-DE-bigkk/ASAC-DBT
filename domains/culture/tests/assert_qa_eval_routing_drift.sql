-- 라우팅 드리프트 신호(warn, #284): 답가능으로 큐레이션했는데 대상 마트가 카탈로그에 없음.
-- 마트 rename/drop 시 여기서 드러난다 — 빌드는 통과(warn), 질문 재큐레이션 트리거.
{{ config(severity='warn') }}

select question_id, target_mart
from {{ ref('gold_culture_qa_eval') }}
where answerable and not mart_exists

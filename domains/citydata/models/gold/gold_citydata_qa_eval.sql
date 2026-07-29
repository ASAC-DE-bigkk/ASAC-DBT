-- gold(Q&A 거버넌스): citydata 페르소나 질문 카탈로그 × 팀 전체 커버리지 라우팅. 그레인 question_id.
-- 설계: 2026-07-21-citydata-qa-eval-design.md. 두 원칙 —
--   (1) 시계열 질문만(서울 API가 지금 한 번에 답하는 실시간 스냅샷 질문은 애초 seed에서 제외),
--   (2) 답은 정의된 metric/골드로만.
-- 채택 결정 도구: 각 실수요 질문을 🟢citydata채택 / 🔵팀원커버(중복금지) / 🔴갭(로드맵) 으로 분류.
-- coverage(큐레이션 의도) vs relation_exists(information_schema 실측) 분리 —
--   라우팅 대상 골드가 rename/drop 되면 status가 🟠missing 으로 뒤집혀 드리프트가 드러난다(governed).
-- 팀원 도메인은 읽기만(information_schema) — 코드 수정 없음(gold_culture_qa_eval 선례와 동일 사상).
-- meta.external=false(내부 전용).

with q as (
    select * from {{ ref('seed_citydata_qa_questions') }}
),

-- 현행 카탈로그 실존 골드 — citydata + 팀원 5도메인(읽기 전용).
--   covered_by_relation 이 이 중 어디든 있으면 실존으로 본다.
marts as (
    select distinct table_name, table_schema
    from {{ target.database }}.information_schema.tables
    where table_schema in (
        '{{ env_var("SEOUL_CITYDATA_SCHEMA", target.schema) }}',
        '{{ env_var("WEATHER_SCHEMA", "weather") }}',
        '{{ env_var("TRANSIT_SCHEMA", "transit") }}',
        '{{ env_var("CULTURE_SCHEMA", "culture") }}',
        '{{ env_var("COMMERCE_SCHEMA", "commerce") }}',
        '{{ env_var("TRAFFIC_SCHEMA", "traffic") }}'
    )
),

joined as (
    select
        q.question_id,
        q.persona_uuid,
        q.persona_summary,
        q.home_region,
        q.persona_lens,
        q.demand_cluster,
        q.requires_timeseries,
        q.question_text,
        q.target_metric,
        q.coverage,
        q.covered_by_domain,
        q.covered_by_relation,
        q.unanswerable_reason,
        (m.table_name is not null) as relation_exists,
        m.table_schema             as resolved_schema,
        -- 채택 상태 재계산(seed coverage × 실측 존재)
        case
            when q.coverage = '🔴gap'          then '🔴gap'          -- 팀 전체 갭(로드맵) — relation 공백 정상
            when m.table_name is null          then '🟠missing'      -- 커버한다던 골드가 실존 안함(드리프트)
            when q.coverage = '🟢citydata'     then '🟢adopt'        -- citydata 채택 → D1
            when q.coverage = '🔵teammate'     then '🔵teammate'     -- 팀원 커버 → 중복 생산 금지
            else '❓unknown'
        end as coverage_status,
        -- 답변 준비 완료 = 갭 아니고 라우팅 대상 골드가 실존
        (q.coverage <> '🔴gap' and m.table_name is not null) as eval_ready
    from q
    left join marts m on m.table_name = q.covered_by_relation
)

select * from joined

-- qa_eval 불변식(#284): 그레인 유일 + 답가능→target_mart 필수 + 답불가→unanswerable_reason 필수.
with dupes as (
    select question_id, count(*) as n
    from {{ ref('gold_culture_qa_eval') }}
    group by question_id
    having count(*) > 1
),
bad as (
    select question_id
    from {{ ref('gold_culture_qa_eval') }}
    where (answerable and target_mart is null)
       or ((not answerable) and unanswerable_reason is null)
)
select question_id, 'dupe' as violation from dupes
union all
select question_id, 'invariant' as violation from bad

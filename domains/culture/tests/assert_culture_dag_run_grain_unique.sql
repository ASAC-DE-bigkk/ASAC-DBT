-- silver_culture_dag_run 그레인(dag_id × run_id) 유일성. 로더 멱등(14일 윈도우 delete+insert) 검증.
{{ config(tags=['slo']) }}
select dag_id, run_id, count(*) as n
from {{ ref('silver_culture_dag_run') }}
group by dag_id, run_id
having count(*) > 1

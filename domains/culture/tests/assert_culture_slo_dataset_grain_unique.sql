-- silver_culture_slo_dataset 그레인(run_id × dataset_name) 유일성. dbt_utils 미사용 → 단일 테스트.
{{ config(tags=['slo']) }}
select run_id, dataset_name, count(*) as n
from {{ ref('silver_culture_slo_dataset') }}
group by run_id, dataset_name
having count(*) > 1

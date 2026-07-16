# Traffic dbt AI index

이 디렉터리는 TOPIS Traffic의 `normal` 변환과 격리된 `recovery` 흐름을 소유한다.
컬럼 의미, generic test, public Gold metadata의 단일 source of truth는 각 SQL 옆 YAML이다.

## 입력과 구조

- Bronze source: [`sources.yml`](sources.yml)
- normal Silver: [`transform/silver/`](transform/silver/)
- normal Gold: [`transform/gold/`](transform/gold/)
- recovery Silver/metadata/Gold: [`recovery/`](recovery/)
- singular tests: [`../../tests/traffic/`](../../tests/traffic/)
- phase 설정과 selector: [`../../dbt_project.yml`](../../dbt_project.yml), [`../../selectors.yml`](../../selectors.yml)

## 실행 tag

| 흐름 | direct tag |
| --- | --- |
| normal Silver | `ask_seoul_traffic_transform_silver` |
| normal Gold | `ask_seoul_traffic_transform_gold` |
| source availability | `ask_seoul_traffic_transform_availability` |
| recovery Silver | `ask_seoul_traffic_recovery_silver` |
| recovery metadata | `ask_seoul_traffic_recovery_metadata` |
| recovery Gold | `ask_seoul_traffic_recovery_gold` |

tag membership은 폴더가 소유한다. DAG나 문서에서 모델 이름 목록을 별도로 복제하지 않는다.

## Public producer

- `gold_traffic_incident_current_by_admin_dong_hourly`만 Traffic의 `published_producer`다.
- SQL: [`transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.sql`](transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.sql)
- 계약: [`transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.yml`](transform/gold/gold_traffic_incident_current_by_admin_dong_hourly.yml)
- `gold_traffic_incident_summary`와 모든 Silver/recovery 모델은 도메인 내부 구현이다.

## Traffic Quality Gold ship set

승인된 Traffic Quality Gold 제품은 정확히 다음 5개다.

1. gold_traffic_incident_current_by_admin_dong_hourly
2. gold_traffic_incident_x_flow
3. gold_traffic_incident_collection_coverage_5m
4. gold_traffic_incident_expected_clearance_profile_by_admin_dong_daily
5. gold_traffic_incident_spatial_mapping_quality_daily

gold_traffic_incident_summary는 support-only relation이며 위 ship set에 포함하지 않는다.

collection coverage는 evidence_scope=materialized_snapshot_only인 request-audit 관측 제품이다. 실제 audit row가 있는 수집 5분 구간만 표현하며, landing하지 않은 schedule slot이나 Airflow missed run을 생성하거나 추론하지 않는다.

expected-clearance profile과 spatial mapping quality는 traffic_snapshot_dag_run_id로 고정된 current Silver를 occurred_at의 KST date로 재집계한다. 두 모델의 mapping_bucket은 canonical admin_dong_code 또는 __UNMAPPED__이며 unmapped row의 canonical stamp는 null이다.

## cross-domain ref 규칙

다른 group·package는 `access: public`인 producer만 명시적 package ref로 소비한다.

```sql
{{ ref('asac_seoul', 'gold_traffic_incident_current_by_admin_dong_hourly') }}
```

Traffic 내부 Silver, 호환 Gold, recovery relation을 cross-domain ref 대상으로 사용하지 않는다.
공개 의미 계약과 검증 명령은 [`../../contracts/traffic/docs/public-gold-ai-contract-v1.md`](../../contracts/traffic/docs/public-gold-ai-contract-v1.md)를 따른다.

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

## cross-domain ref 규칙

다른 group·package는 `access: public`인 producer만 명시적 package ref로 소비한다.

```sql
{{ ref('asac_seoul', 'gold_traffic_incident_current_by_admin_dong_hourly') }}
```

Traffic 내부 Silver, 호환 Gold, recovery relation을 cross-domain ref 대상으로 사용하지 않는다.
공개 의미 계약과 검증 명령은 [`../../domains/traffic/contracts/docs/public-gold-ai-contract-v1.md`](../../domains/traffic/contracts/docs/public-gold-ai-contract-v1.md)를 따른다.

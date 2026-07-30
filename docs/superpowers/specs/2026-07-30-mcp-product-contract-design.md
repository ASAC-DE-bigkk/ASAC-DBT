# Weather·Traffic MCP 제품 계약 설계

## 목적

Weather·Traffic의 기존 `public_gold` 의미 계약을 축소하지 않고, MCP/K-skill 소비자가 대표 질의와 승인된 named operation을 선택할 수 있는 정적 projection을 만든다. 이 문서는 ASAC-DBT #390의 범위이며 Dashboard와 Worker API는 변경하지 않는다.

## 현재 상태와 경계

`public_gold`에는 time roles, `Asia/Seoul` timezone, 컬럼별 `null_meaning`, quality state, coverage, `semantic_caveats`, `do_not_use_for`와 lineage가 이미 선언되어 있다. 그러나 public-Gold catalog validator는 이 선언을 검증·산출할 뿐, MCP 사용 패턴은 제공하지 않는다.

실제 `publication_id`, D1 row count, freshness, publication status는 ASAC-DAG Publisher의 런타임 사실이다. 이 계약에는 값을 적지 않고, `lineage.identifiers.publication`이 런타임 D1 catalog의 `publication_id`를 가리킨다는 정적 의미만 유지한다. Gold SQL, grain, 컬럼, `meta.serving`의 정적 게시 계약은 바꾸지 않는다.

## 선택한 구조

각 10개 서빙 모델의 `config.meta.public_gold`에 `mcp_projection`을 추가한다.

```yaml
mcp_projection:
  schema_version: mcp-product-projection/v1
  operation:
    id: weather.get_current_outlook
    approval_status: approved
    execution_mode: catalog_only
  question_examples:
    - 지금 이 장소의 가장 가까운 기상 예보는 무엇인가요?
    - 이 장소의 예보 기온과 강수 가능성은 무엇인가요?
    - 이 장소의 현재 예보 대상 시각은 언제인가요?
```

- `operation.id`는 안정적인 `weather.` 또는 `traffic.` 접두사의 named operation이다.
- `approval_status: approved`는 제품 질문과 결과 의미가 승인됐다는 뜻이다.
- `execution_mode: catalog_only`는 이 PR이 MCP tool/function 실행기를 만들지 않는다는 뜻이다. API parameter, pagination, authorization은 Worker/API 소유이므로 여기서 추정하지 않는다.
- `question_examples`는 한국어의 서로 다른 3개 질의이며 SQL·URL·동적 timestamp·secret을 담지 않는다.

기존 public catalog의 resource `public_gold` projection에 이 블록을 그대로 포함한다. 따라서 `description`이나 `description_ko`만 따로 소비하는 경로가 아닌 정적 catalog는 public_gold 전체 의미와 MCP 힌트를 함께 받는다.

## MVP operation과 질의 예시

| 도메인 | 제품 | 승인 named operation | 질문 예시 수 |
| --- | --- | --- | ---: |
| Weather | `weather_place_current_outlook` | `weather.get_current_outlook` | 3 |
| Weather | `weather_place_precipitation_window` | `weather.find_precipitation_windows` | 3 |
| Weather | `weather_place_risk_window` | `weather.find_risk_windows` | 3 |
| Weather | `weather_place_forecast_change_daily` | `weather.compare_forecast_change_daily` | 3 |
| Traffic | `traffic_incident_x_weather_current_hourly` | `traffic.get_incident_weather_context` | 3 |
| Traffic | `traffic_flow_congestion_hotspots_hourly` | `traffic.list_congestion_hotspots` | 3 |
| Traffic | `traffic_flow_link_latest` | `traffic.get_link_latest` | 3 |
| Traffic | `traffic_flow_change_latest` | `traffic.get_flow_change` | 3 |
| Traffic | `traffic_flow_link_time_profile` | `traffic.get_link_time_profile` | 3 |
| Traffic | `traffic_flow_anomaly_current` | `traffic.list_flow_anomalies` | 3 |

총 10개 operation, 30개 질문 예시다. 예시는 각 모델의 `product_question`, grain, time semantics, quality field와 `do_not_use_for`를 벗어나지 않는다. 같은 의미의 모든 자연어 표현이나 275개 개별 사용 패턴을 목록화하지 않는다.

## Validator와 산출물

public-Gold manifest validator에 다음을 추가한다.

1. `mcp_projection`이 선언된 경우 schema version, operation mapping, stable operation id, 승인 상태, execution mode, 한국어 질의 예시 3개를 검증한다.
2. operation id와 질문은 중복될 수 없고, operation의 도메인 접두사는 모델의 Weather/Traffic 소유 도메인과 일치해야 한다.
3. 유효한 값만 catalog projection에 포함한다. 검증 오류가 하나라도 있으면 기존과 같이 catalog를 만들지 않는다.
4. 모델·컬럼 메타의 `time`, `quality`, `lineage`, `semantic_caveats`, `do_not_use_for` export를 제거하거나 평탄화하지 않는다.

portfolio test는 정확히 10개 모델에서 10개의 고유 operation과 30개의 예시가 나온다는 것을 검사한다. manifest unit test는 누락, 잘못된 execution mode, 영문/중복 예시, 도메인 불일치 operation, 동적·민감 키를 거부한다.

## 오류 처리와 호환성

`mcp_projection`은 정적 선언이므로 런타임 publication id나 API endpoint를 포함하지 않는다. 이로써 dbt manifest가 실제 게시 상태를 오래된 값으로 주장하지 않는다. public-Gold consumer가 새 필드를 모르면 무시할 수 있고, 새 consumer는 schema version으로 지원 여부를 판정한다.

이 PR의 성공은 새 artifact가 rich metadata를 보존하면서 10 operation과 30 examples를 안정적으로 export하는 것이다. D1/API 전달과 실제 publication id는 ASAC-DAG #623이 담당한다.

## 검증

- contract engine의 focused unit test와 artifact byte-stability test
- Weather·Traffic public-Gold manifest validation
- DBT parse 및 변경된 serving 모델 selector의 contract test
- 실제 D1, Worker, Dashboard, prod write는 이 PR에서 실행하지 않는다.

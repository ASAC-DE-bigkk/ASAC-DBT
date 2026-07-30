# Weather·Traffic MCP 제품 계약 설계

## 목적

Weather·Traffic의 기존 rich `public_gold` 의미 계약을 축소하지 않고, MCP/K-skill이 대표 질의와 승인된 named operation을 선택할 수 있는 정적 선언을 추가한다. 이 설계는 ASAC-DBT #390의 범위이며 Dashboard와 Worker API는 바꾸지 않는다.

## 계약 경계

`public_gold`는 time role, `Asia/Seoul` timezone, 컬럼별 `null_meaning`, quality state, coverage, `semantic_caveats`, `do_not_use_for`, lineage를 계속 소유한다. 기존 rich 선언은 `description` 또는 `description_ko`로 대체하지 않는다.

10개 제품의 named operation은 `config.meta.serving.mcp_projection`에 둔다. serving metadata가 모든 D1 대상 모델에 있으므로, public-Gold 선언이 없는 모델에 불완전한 public 계약을 새로 만들지 않는다.

```yaml
mcp_projection:
  schema_version: mcp-product-projection/v1
  operation:
    id: weather.get_current_outlook
    approval_status: approved
    execution_mode: catalog_only
  question_examples:
    - 지금 장소의 현재 예보는 무엇인가요?
    - 오늘 비 가능성을 확인해 주세요.
    - 예보의 기준 시각은 언제인가요?
```

`catalog_only`는 이번 PR에서 executable MCP operation, API endpoint, pagination, authorization 계약을 만들지 않는다는 뜻이다. `publication_id` 같은 런타임 값도 dbt manifest에 넣지 않는다.

## MVP 포트폴리오

| 도메인 | 제품 수 | named operation | 질문 예시 |
| --- | ---: | ---: | ---: |
| Weather | 4 | 4 | 12 |
| Traffic | 6 | 6 | 18 |
| 합계 | 10 | 10 | 30 |

승인된 operation은 `weather.get_current_outlook`, `weather.find_precipitation_windows`, `weather.find_risk_windows`, `weather.compare_forecast_change_daily`, `traffic.get_incident_weather_context`, `traffic.list_congestion_hotspots`, `traffic.get_link_latest`, `traffic.get_flow_change`, `traffic.get_link_time_profile`, `traffic.list_flow_anomalies`다.

## 전달과 검증

ASAC-DAG #623 Publisher는 manifest의 rich `public_gold`를 D1 `_catalog.public_gold` JSON으로, `serving.mcp_projection`을 sibling `_catalog.mcp_projection` JSON으로 전달한다. `_catalog.publication_id`는 해당 Publisher가 매 실행 기록하는 런타임 값으로 유지한다.

DBT portfolio test는 10개의 고유 operation, 30개의 한국어 질문, `approved` 상태, `catalog_only` 실행 모드와 Weather/Traffic 도메인 접두어를 검증한다. 기존 public-Gold validator는 rich 의미 계약의 time, quality, lineage, caveat, 금지 용도를 계속 검증·산출한다.

실제 D1 게시, Worker API, Dashboard, prod write는 이 저장소에서 실행하지 않는다.

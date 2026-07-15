# Traffic source freshness SLO

## 적용 계약

Traffic source freshness는 사고 행 수가 아니라 Airflow 수집 run의 게시 가능 상태를 나타내는
`traffic_bronze.collection_run_manifest.event_at`만 감시한다.

| 항목 | 환경 변수 | 기본값 | 단위 |
|---|---|---:|---|
| warning | `ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_WARN_MINUTES` | 15 | minute |
| error | `ASK_SEOUL_REPORT_TRAFFIC_FRESHNESS_ERROR_MINUTES` | 30 | minute |

두 값은 dbt parse 시 정수로 해석된다. 운영 override도 `warning < error`를 지켜야 하며,
Airflow reliability watchdog에 같은 환경 변수를 주입해 한 배포 안에서 정렬한다. 환경 변수를
지정하지 않으면 기존 계약인 `15분/30분`을 유지한다.

## manifest-only 경계

- `collection_run_manifest`: freshness 적용
- `seoul_traffic_incident`: `freshness: null` 유지
- `seoul_traffic_incident_request_audit`: `freshness: null` 유지

정상적인 TOPIS zero-incident run은 incident row가 없어도 manifest와 request audit로 성공을
증명할 수 있다. 따라서 incident 행의 최신성으로 source freshness를 판단하면 정상 empty
snapshot을 stale로 오판한다. pinned snapshot correctness도 선택된 run의 정합성을 검사하는
별도 계약이며 live latest freshness로 대체하지 않는다.

## threshold 근거와 재조정 조건

2026-07-13 `dev` 기준으로 ASAC-DBT의 추적된 Traffic 코드·문서와 전체 커밋 메시지에서
freshness threshold 관련 기록을 검색했다. `15분/30분`을 도입한 변경과 zero-row/pinned
보호 변경은 확인했지만, 실제 경보 발생 횟수·false-positive 횟수·대상 run ID·지연 분포를
담은 측정 자료는 저장소에서 확인되지 않았다.

따라서 현재 상태는 **오탐이 0건이라는 뜻이 아니라 측정 자료가 없음**이다. 기본값을 다시
조정하려면 최소한 다음 증거를 수집한 뒤 별도 이슈에서 결정한다.

- 측정 기간과 전체 scheduled run 수
- warning/error 발생 run ID와 실제 게시 지연
- 정상 지연으로 판정된 false-positive 수 및 비율
- 장애 누락 여부와 새 threshold의 예상 탐지 지연

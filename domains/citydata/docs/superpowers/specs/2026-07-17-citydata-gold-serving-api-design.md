# citydata 골드 서빙 API 설계 — tier 분류·description 규격·카탈로그 (2026-07-17)

> 7/16 멘토링 회의 결정 기반: 1차 목표 = **Rapid API처럼 골드를 API 상품으로 제공** (② 대시보드 → ③ 챗봇은 이후 단계).
> 소비자는 사람이 아니라 **Agent** — 데이터 개수보다 description이 관건.
> 서빙 스토리지는 **D1 단독** — Trino 직조회는 서빙 경로에 두지 않는다(노트북 의존 인프라).
> 이 문서는 설계만 다룬다. Workers/D1 구현은 다음 단계(팀 합의 후).

## 0. 팀 현황과 계승 관계

| 팀 산출물 | 내용 | 우리가 계승하는 것 |
|---|---|---|
| commerce `docs/DB/gold/serving-design.md` | D1 서빙 설계 확정 — tier 프레임(d1_direct/d1_rollup), 전량 교체 스냅샷 원칙, Postgres 폐기 | tier 프레임, export 원칙 |
| traffic_weather `contracts/serving_gold_catalog.yml` | Agent용 서빙 후보 카탈로그 yml (dev_pending) | 취지만 계승 — 형식은 meta 방식(§4)으로 대체, 필요시 그쪽 형식을 meta에서 생성 |
| 실제 Workers API 코드 | **아직 아무도 없음** | citydata가 첫 실물 API가 될 수 있음 |

## 1. 상품성 핵심 — 과거 조회가 차별점

서울시 원본 API는 실시간 값만 제공하고 과거를 물어볼 수 없다. 우리 파이프라인은 이력을
쌓아왔으므로 **기간 지정 조회(`from`/`to`)가 우리 API의 메리트**다. 따라서:

- 이력 조회의 해상도는 **시간별·일별** 두 단계로 제공하고, 두 계열 모두 **전 기간을 D1에** 둔다.
- "지금/최근" 질문은 스냅샷 골드가, "기간·이력" 질문은 시간별/일별 골드가 답한다.
- **5분 원본(by_time)의 API 제공은 보류** — §2 참조.

## 2. 서빙 tier 분류

D1 실용 상한(≪1GB/DB, commerce 실측 기준)과 행수 추정 기반. citydata는 장소 121곳·행정동
~80동으로 축이 작아, 일별은 수년치도 D1에 들어간다 (commerce의 롤링 400일을 따르지 않는 근거).

| tier | 모델 | 추정 크기 | export |
|---|---|---|---|
| **d1_direct (스냅샷)** | place_latest · anomaly · trend · scorecard · hot_commerce (각 ~121행), ppltn_x_commerce_dong (~수백 행), forecast (~5.8k행) | 초소형 | 매 run 전량 교체 |
| **d1_direct (이력·일별, 전 기간)** | ppltn_daily · cmrcl_daily · purchasing_power_daily · ppltn_x_culture_daily | 일×121(또는 동) — 5년 ≈ 22만 행 | 일 배치 전량 교체 |
| **d1_direct (이력·시간별, 전 기간·연 단위 재검토)** | ppltn_x_weather_hourly · ppltn_x_transit_hourly · transit_x_incident_hourly | 시×~80동 ≈ 연 70만 행 | 일 배치 전량 교체 |
| **d1_rollup (신규 골드 1개)** | `gold_citydata_ppltn_hourly` — by_time을 시간별로 롤업(시간당 평균/최대 인구·혼잡도) | 시×121 ≈ 연 106만 행, 5년 ≈ 530만 행(~800MB) — 연 단위 재검토 | 일 배치 전량 교체 |
| **d1_direct (대형)** | ppltn_demographics | **실측 200,860행**(2026-07-17, Trino count) — D1 여유 | 일 배치 전량 교체 |
| **서빙 보류** | ppltn_by_time (5분 원본) | 실측 370,786행/약 10일 → 연 1,270만 행급 — D1 부적합 | export 안 함 |

**by_time 보류 사유와 대체**: 5분 원본은 D1에 못 넣고(5년 6,350만 행), Trino 직조회는 서빙
경로에서 배제됐다. 대신 ① "지금/최근"은 place_latest·scorecard·trend·anomaly(전부 by_time
파생·D1행)가, ② 기간 조회는 신규 시간별 롤업(ppltn_hourly)과 일별(ppltn_daily)이 커버한다.
5분 해상도 자체가 필요한 소비(연구용 대량 추출 등)가 실제로 나타나면 그때 제공 방식
(R2 파일 다운로드 상품, 인프라 통합 후 프록시 등)을 다시 결정한다 — **보류이지 폐기 아님**.

## 3. description 규격 (정본 = `_citydata_gold__models.yml`)

멘토 지침("테이블명 먼저, 뭘 하고, 어떤 질문을 해결하는지를 AI에게 전달되도록")을 규격화.
모든 모델 description을 4요소로 재작성한다:

```
① 테이블명 + 한 문장 정의   — "gold_citydata_place_latest — 장소별 최신 크로스 신호 스냅샷(장소당 1행)."
② 담는 내용                — 혼잡×소비×승하차×따릉이×대기질 최신값 통합.
③ 해결하는 질문 (Agent 매칭용 예시 문장 2~3개) — "지금 강남 붐벼?" / "전 장소 현재 상태를 지도에".
④ grain · 갱신주기(fast/slow) · 적재(table+replace) · 제한(⚠ 예보값·상대지수·커버리지 등)
```

- yml description이 **단일 정본** — dbt docs·`/catalog` 응답이 전부 여기서 파생.
  다른 파일에 설명을 중복 서술하지 않는다.
- **문서 교정(동작 변경 아님)**: 골드 yml description에 남은 "incremental(merge)" 등 낡은
  문구를 실제에 맞게 고친다. 실제 동작은 **골드 전 모델 table+replace** —
  `dbt_project.yml`이 `+materialized: table` + `+on_table_exists: replace`(원자 교체)로 강제.
  (골드 한정 — silver는 실제로 증분 delete+insert + dedup post-hook이며 건드리지 않는다.)

## 4. 서빙 메타 선언 — dbt `meta` 필드 (별도 카탈로그 파일 없음)

별도 contracts yml(traffic_weather 방식)은 정본이 두 개가 되어 모델 추가/삭제 시 목록
드리프트 위험이 있다(이번에 CI로 잡던 문제 유형). 대신 dbt 표준 `meta`로 **설명과 tier를
같은 파일에** 둔다:

```yaml
- name: gold_citydata_place_latest
  config:
    tags: ['fast']
    meta: {serving_tier: d1_direct}
  description: >
    gold_citydata_place_latest — 장소별 최신 크로스 신호 스냅샷(장소당 1행). ...
```

- `serving_tier` 값: `d1_direct` | `d1_rollup` | `hold`(보류) — §2 표와 1:1.
- D1 export DAG와 Workers `/catalog`는 dbt manifest(또는 yml 직접 파싱)에서
  `meta.serving_tier`가 `hold`가 아닌 모델을 서빙 목록으로 읽는다 — 목록 파일 별도 관리 없음.
- 팀 표준이 traffic_weather 형식으로 정해지면 그 yml을 meta에서 **생성**한다(손 관리 금지).

## 5. API 표면 (구현은 다음 단계)

Rapid API 모델 — 진열대 + 개별 상품:

```
GET /catalog
  → 서빙 모델 목록 JSON. 모델별 {name, description(§3), grain, tier}.
    Agent의 진입점 — description을 읽고 스스로 테이블을 고른다 (RAG/Vectorize 불사용, 회의 결정).

GET /data/{table}?<필터>
  → D1 조회. where 필터를 쿼리 파라미터로: 축 필터(area_cd, gu, admin_dong_code …)
    + 기간 필터(from/to — event_date/time_bucket 기준). 무필터 전량 응답은 스냅샷 tier만 허용.
```

- **로그**: 요청 1건 = D1 로그 테이블 1행 append (회의 결정 — 로그 수집기 없이 코드 한 줄).
  질문 로그는 이후 페르소나 재분석 원천.
- **export 원칙**: 전량 교체 스냅샷, 증분 upsert 금지 (commerce 원칙 + R2 비원자성 회고와 일관 —
  D1도 단일 writer 전량 교체가 멱등).
- 예쁜 개별 엔드포인트(`/api/congestion` 류)·인증·rate limit은 구현 단계 결정으로 이월.

## 6. 비범위 (이번에 안 하는 것)

- Workers/D1 export 코드 구현 (팀 합의·멘토 확인 후)
- `gold_citydata_ppltn_hourly` 신규 골드 SQL 구현 (설계만 — 다음 단계)
- 챗봇·페르소나·Vectorize (3단계 — 회의: 논리 검증 후 판단)
- 기존 FastAPI 대시보드(dashboard/app.py) 변경 — 2단계(대시보드) 트랙, 별도
- 타 도메인 골드의 tier 분류 (각 도메인 소유)

## 7. 산출물·다음 단계

1. 본 설계 문서 (이 파일)
2. `_citydata_gold__models.yml` — 16개 description 재작성(§3) + `meta.serving_tier` 부여(§4)
3. ~~demographics 행수 실측~~ → **완료(2026-07-17): 200,860행, d1_direct 확정**
4. (다음 단계) `gold_citydata_ppltn_hourly` 구현 / D1 export DAG / Workers 구현 /
   5분 원본 제공 방식 재논의(보류 해제 조건: 실수요 발생)

# transit 데이터 가이드 (#51)

transit dbt 프로젝트가 만드는 silver·dim·gold 모델과, 소비하는 공통 dim(asac_axes)의
데이터셋별 설명서. 분석 소비자 관점(컬럼 의미·활용·함정 중심)이며, **계약(스펙)은
[dbt_contracts.md](dbt_contracts.md)** 에, 구현 세부는 각 `.sql` 헤더·`schema.yml` 에 있다.

> **스펙 먼저 볼 것**: source·수집주기·time·space·grain·tier·보존·gold 계약은 전부
> [dbt_contracts.md](dbt_contracts.md) 에 정리돼 있다. 이 README 는 데이터셋별 해설이다.

## 구성

| 문서 | 성격 | 한 행의 의미 |
|---|---|---|
| [dbt_contracts.md](dbt_contracts.md) | **계약(스펙)** | transit 전체 source·time·space·grain·tier·보존·gold 계약 |
| [slv_transit_parking.md](slv_transit_parking.md) | silver fact (5분) | 주차장 1개의 시점 스냅샷 |
| [slv_transit_subway_arrival.md](slv_transit_subway_arrival.md) | silver fact (3분) | 열차 도착예측 1건 |
| [slv_transit_bus_position.md](slv_transit_bus_position.md) | silver fact (버스 티어링) | 버스 1대의 시점 위치 |
| [gold_transit_archive_15min.md](gold_transit_archive_15min.md) | gold 아카이브 3종 + tier dim (#286·#471) | 동×15분 / 노선×구간×30분 / 주차장×15분 — 주 단위 원본 삭제 대비 영구 집계층 |
| [gold_transit_user_facing_p1.md](gold_transit_user_facing_p1.md) | 사용자향 gold 1차 (#289) | 지금 카드(G1) / ×날씨(G6) / 따릉이 라스트마일(G9) |
| [gold_transit_user_facing_p2.md](gold_transit_user_facing_p2.md) | 사용자향 gold 2차 (#287·288·290·291·292) | 리듬(G4)·주차 프로파일/리스크(G2)·노선 쾌적도(G3)·행사 접근(G7)·수요×공급(G8)·예측(G10) |
| [gold_transit_dong_hourly.md](gold_transit_dong_hourly.md) | gold (시간, 기존 #67) | 행정동 1개 × 1시간대 교통 상태 — 15분판(dong_15min)이 아카이브 축 |
| [dim_transit_station.md](dim_transit_station.md) | dim (주간) | 지하철역 1개 |
| [dim_transit_parking.md](dim_transit_parking.md) | dim (주간) | 공영주차장 1개소 |
| [dim_admin_dong.md](dim_admin_dong.md) | dim (공통, asac_axes) | 서울 행정동 1개 |
| [dim_beop_admin_link.md](dim_beop_admin_link.md) | dim (공통, asac_axes) | 법정동↔행정동 연계 1쌍 |

> silver 실제 테이블명은 `silver_transit_*`(현행). `slv_transit_*` 문서는 같은 팩트의 해설이다.
> 버스 tier 분류는 `dim_transit_bus_route_tier`(routeType 원천 조인, #471) — 계약은 dbt_contracts §6.

## 공통 규약 (팀 공통축 #48)

- **시간축**: `event_at` = 도메인 대표 시각, **KST 벽시계**. `_at`=KST timestamp, `_date`=날짜.
  원시 event_at 조인은 금지(필터 전용). 아카이브 버킷(`bucket_at`/`hour_at`) 정렬은 크로스
  도메인 gold 에서 허용 — 원시 event_at 조인이 아니라 같은 grain 의 시각 정렬이다.
- **공간축(조인 키)**: `admin_dong_code`(행안부 10자리) + `gu_code` + `latitude`/`longitude`(WGS84).
  도메인 간 조인은 공간축으로. 커버리지 임계는 dbt_contracts §4.
- **계보**: `dag_run_id`, `ingested_at`(UTC), dim은 `load_date`/`revision_date` — 추적용.

## 읽을 때 주의

- **수집 범위/주기(현행)**: 지하철 도착 3분(경로형 ALL 수집 — 전 노선 339역·210개 동), 버스 티어링(#440·#449 —
  간선·광역 tier1 촘촘·전 노선 스냅샷 09·19시, 시간창은 dbt_contracts §2), 주차 5분(실시간
  제공 개소). 서울 전체 일반화는 여전히 금물이나, 버스는 ALL 수집으로 커버리지 대폭 확대(420개 동).
- **버스 tier**: 시간대 비교 지표(리듬·프로파일·예측)는 tier1 한정(`*_t1`), 현재 상태(dong_now)는
  전 티어 + 관측 시각 표기. 원천은 `bronze_bus_route_master`(routeType, #471).
- **아카이브 개시일**: gold 아카이브는 `transit_archive_start_at`(2026-07-21 09:00 KST) 이후만
  쌓는다 — 정책 전환 전 오염 구간(중복·무의미 tier) 차단. 그 이전 gold 는 없다.
- **arrival `event_at` 이상치**: 원천 전일 막차 잔존으로 미래 행이 있었음 — silver 상한 게이트로
  제거(#66, `event_at <= utc_to_kst(ingested_at)+스큐 10분`). 최근 24h 드랍 비율 warn 감시.
- **주차 dim 좌표 결손**: 마스터 850개소 중 유효 좌표 일부(실시간 제공 개소는 대부분 유효).

# transit silver 데이터 가이드 (#51)

transit dbt 프로젝트가 만드는 silver·dim 모델과, 소비하는 공통 dim(asac_axes)의 데이터셋별 설명서.
분석 소비자 관점의 문서다 — 컬럼 의미·활용 시나리오·함정 중심 (모델 구현 관점은 각 `.sql` 헤더 주석과 `schema.yml`).

## 구성

| 문서 | 성격 | 한 행의 의미 |
|---|---|---|
| [slv_transit_parking.md](slv_transit_parking.md) | fact (20분) | 주차장 1개의 시점 스냅샷 |
| [slv_transit_subway_arrival.md](slv_transit_subway_arrival.md) | fact (20분) | 열차 도착예측 1건 |
| [slv_transit_bus_position.md](slv_transit_bus_position.md) | fact (20분) | 버스 1대의 시점 위치 |
| [dim_transit_station.md](dim_transit_station.md) | dim (주간) | 지하철역 1개 |
| [dim_transit_parking.md](dim_transit_parking.md) | dim (주간) | 공영주차장 1개소 |
| [dim_admin_dong.md](dim_admin_dong.md) | dim (공통, asac_axes) | 서울 행정동 1개 |
| [dim_beop_admin_link.md](dim_beop_admin_link.md) | dim (공통, asac_axes) | 법정동↔행정동 연계 1쌍 |

## 공통 규약 (팀 공통축 #48)

- **시간축**: `event_at` = 도메인 대표 시각, **KST 벽시계**. `_at` 접미사는 KST timestamp, `_date`는 날짜. 시간축은 필터 전용(조인 금지).
- **공간축(조인 키)**: `admin_dong_code`(행안부 10자리) + `gu_code`(앞 5자리) + `latitude`/`longitude`(WGS84). **도메인 간 조인은 공간축으로만.**
- **계보**: `dag_run_id`, `ingested_at`(UTC), dim은 `load_date`/`revision_date` — 분석 컬럼 아님, 추적용.

## 읽을 때 주의

- **수집 범위가 좁다**: 지하철 도착=환승역 3곳(강남·잠실·사당), 버스=간선 5노선, 주차=실시간 제공 123개소. 서울 전체 일반화는 금물.
- **arrival의 `event_at` 이상치**: 원천이 전일 막차 안내를 잔존시켜 수집시각보다 미래인 행이 드물게 있음 — 시계열 분석 시 `event_at <= ingested_at 환산` 필터 권장.
- **주차 dim 좌표 결손**: 마스터 850개소 중 유효 좌표는 일부(실시간 제공 개소는 대부분 유효).

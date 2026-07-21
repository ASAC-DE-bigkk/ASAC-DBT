# slv_transit_bus_position — 버스 실시간 위치

- **한 행** = 버스 1대의 시점 위치 / **grain**: (`veh_id`, `data_tm`)
- **원천**: TOPIS `getBusPosByRtid`(전 노선 ALL, 티어링 #440·#449 — tier1 간선·광역 촘촘,
  tier2 09·19시 스냅샷, XML) → `bronze_bus_position` → SQL 파싱(regexp+unnest)
- 유일하게 **실좌표(GPS)가 있는 실시간** 데이터. 전 노선 수집으로 420개 동 커버(외곽 노선
  일부는 서울 경계 밖이라 admin_dong_code NULL — 커버리지 임계 0.85, dbt_contracts §4)

## 컬럼

| 컬럼 | 설명 |
|---|---|
| `veh_id` / `plain_no` | 차량 ID / 번호판 |
| `data_tm` → `event_at` | 위치 기준시각 (KST) |
| `bus_route_id` | 노선 ID (146=100100025 등) |
| `latitude` / `longitude` | GPS 실좌표 (WGS84) |
| `admin_dong_code` / `gu_code` | 좌표 → 경계 조인으로 계산한 행정동·구 |
| `sect_ord` | 노선 내 현재 구간 순번 |
| `next_st_id` | 다음 정류장 ID |
| `congestion` | 차내 혼잡도 코드 (0=정보없음, 3=여유, 4=보통, 5=혼잡 — TOPIS 코드) |
| `stop_flag` | **정차 중 여부** (0/1) ★신규 |
| `is_full` | **만차 여부** (0/1) ★신규 |
| `is_last_bus` | **막차 여부** (0/1) ★신규 |
| `rt_dist_km` | **노선 누적 진행거리(km)** ★신규 |
| `full_sect_dist_km` | **현재 구간 전체 길이(km)** ★신규 |

## 활용 추천

1. **동별 혼잡 히트맵**: `congestion`×`admin_dong_code`×시간대 — 지금 데이터로 바로 지도에 올라가는 대표 데모.
2. **실주행 속도** ★: 같은 `veh_id`의 `rt_dist_km` 증가분 ÷ `event_at` 간격, **`stop_flag=0`만 필터**하면 정차 배제한 순수 주행 속도 → 노선 구간별 정체 식별(`sect_ord` 단위 집계).
3. **만차율** ★: `is_full` 비율을 노선×시간대로 — 증차가 필요한 시간대 근거.
4. **막차 커버리지** ★: `is_last_bus=1`의 위치·시각 → 심야에 어느 동까지 버스가 닿는가 (지하철 막차와 교차).
5. **정차 시간 비율**: `stop_flag` 평균 = 노선이 신호/정류장에 묶여 있는 비율 — 정시성 지표.

## 주의

- 버스 수집 주기는 티어링(#440·#449): tier1 은 출퇴근 10분·그 외 시간당, tier2 는 09·19시만.
  버킷 사이 경로는 모름 — 속도는 구간 평균으로만 해석.
- **tier1(간선·광역)만 시간대 비교에 쓸 것**: tier2 는 09·19시에만 관측돼 시간대별 표본 구성이
  달라진다. 노선 tier 는 `dim_transit_bus_route_tier`(routeType 원천, #471). `congestion=0`
  (정보없음)은 혼잡 집계에서 제외.

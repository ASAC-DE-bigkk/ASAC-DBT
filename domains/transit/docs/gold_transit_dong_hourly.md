# gold_transit_dong_hourly — 동×시간대 교통 상태판

- **한 행** = 행정동 1개 × 1시간대의 버스·지하철·주차 지표 묶음 / **grain**: (`admin_dong_code`, `hour_at`)
- **원천**: silver 3종(`slv_transit_bus_position`, `slv_transit_subway_arrival`, `slv_transit_parking`)을 동·시간으로 집계
- **증분**: incremental merge (unique_key = `admin_dong_code` × `hour_at`, -3h lookback)

한 동·한 시간에 "버스가 얼마나 다녔고/막혔나, 지하철이 몇 번 도착했고 얼마나 기다렸나, 주차가 얼마나 찼나"를 한 줄로 본다. 세 소스를 **outer 결합**하므로 한 소스만 관측된 동·시간도 행이 생긴다(없는 소스 컬럼은 null).

## 컬럼

| 컬럼 | 설명 |
|---|---|
| `admin_dong_code` | 행정동 코드(행안부 10자리) — 공간축·그레인 축. 공간축 미부착(null) 행은 제외 |
| `hour_at` | 시간 버킷(KST 벽시계, `date_trunc('hour', event_at)`) — 그레인 축 |
| `bus_obs_cnt` | 버스 관측 행수(동×시간) |
| `bus_veh_cnt` | distinct 차량 수(`veh_id`) |
| `bus_congestion_avg` | 혼잡도 평균. 원천 `congestion` 중 **0(정보없음) 제외**. 실측 값역 3~5 |
| `bus_full_ratio` | 만차 비율(`is_full` 평균, 0~1) |
| `bus_stop_ratio` | 정차 비율(`stop_flag` 평균, 0~1) |
| `subway_arrival_cnt` | 지하철 도착정보 관측 행수 |
| `subway_wait_avg_s` | 접근 중 열차 평균 잔여 도착시간(초). **`barvl_dt_sec=0`(도착/진입) 제외** — 아래 주의 |
| `subway_last_train_cnt` | 막차 관측 합(`is_last_train` 합) |
| `parking_lot_cnt` | 관측 주차 개소 수(동×시간 distinct lot) |
| `parking_occupancy_avg` | 평균 점유율(개소별 평균 점유율의 평균, 개소 동등가중). **현재 상류 결손으로 null** — 아래 주의 |
| `parking_full_lot_cnt` | 만차 개소 수(개소별 시간 내 최대 점유율 ≥ 0.95). **현재 상류 결손으로 0** — 아래 주의 |

## 활용 추천

1. **동별 혼잡 시계열**: `bus_congestion_avg`·`bus_stop_ratio`를 `hour_at`로 그려 "이 동이 몇 시에 막히나". 상권·인구 도메인과 `admin_dong_code`로 조인.
2. **환승 거점 대기 프로파일**: `subway_wait_avg_s`·`subway_arrival_cnt`로 역 인근 동의 시간대별 열차 접근성(지하철 커버 동에 한함).
3. **주차 압력 히트맵**(상류 수정 후): `parking_occupancy_avg`·`parking_full_lot_cnt`로 "몇 시에 어느 동 주차가 차나".
4. **동 교통 종합판**: 세 지표군을 한 행에서 함께 봐 "차·전철·주차가 동시에 붐비는 동·시간" 도출.

## 주의

- **커버리지**: 원천은 버스 전 노선(티어링 #440·420개 동)·지하철 전 노선(경로형 ALL·339역·210개 동)·실시간 주차 개소다. 값이 있는 동·시간만 유효 표본이며, 관측 수(`*_obs_cnt`)로 얇은 셀을 거른다.
- **스냅샷 평균의 해석 한계**: silver 는 순간값 관측(버스 티어링·지하철 3분·주차 5분)이다. `hour_at` 집계는 그 시간 안에 잡힌 스냅샷들의 평균/카운트일 뿐 연속 관측이 아니다. `bus_veh_cnt`는 "그 시간에 그 동을 지난 고유 차량 수"이지 통행량이 아니고, `subway_wait_avg_s`는 도착예측 스냅샷의 평균이라 실제 승객 대기와 다르다. 관측 수(`*_obs_cnt`/`*_arrival_cnt`/`parking_lot_cnt`)를 함께 봐 표본이 얇은 셀을 걸러라.

> 이 gold(#67)는 동×시간 상태판이고, 15분판 `gold_transit_dong_15min`(#286)이 아카이브 축이다. 신규 사용자향 gold 는 [gold_transit_user_facing_p1.md](gold_transit_user_facing_p1.md)·[p2](gold_transit_user_facing_p2.md).
- **`subway_wait_avg_s`의 0 제외**: 원천 `barvl_dt_sec=0`은 "이미 도착/진입한 열차"라 대기가 아니다(실측 약 44%가 0). 포함하면 평균이 절반 이하로 왜곡돼 **제외**했다. 이 지표는 "접근 중 열차의 평균 잔여 도착시간(초)"으로 읽어야 한다.
- **주차 점유율 지표 현재 null/0 (상류 결손)**: `slv_transit_parking`·`dim_transit_parking`이 원천의 소수문자열(`'806.0'`,`'1260.0'`)을 `cast(... as integer)`로 파싱해 소수점 때문에 try-cast가 실패, `now_prk_vhcl_cnt`·`total_capacity`가 전건 null이다. 그 결과 `parking_occupancy_avg`(null)·`parking_full_lot_cnt`(0)를 지금은 계산할 수 없다. gold 로직은 정상이며 **silver 캐스트 수정(별도 이슈) 후 자동으로 채워진다**. `parking_lot_cnt`(개소 카운트)는 영향 없이 정상.
- **시간축은 정화된 silver 소비**: 미래 `event_at`은 #66 게이트로 이미 silver에서 제거됨 — gold는 추가 시간 필터 없이 소비한다.

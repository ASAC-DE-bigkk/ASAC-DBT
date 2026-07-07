# slv_transit_subway_arrival — 지하철 실시간 도착

- **한 행** = 역에 대한 열차 도착예측 1건 / **grain**: (`statn_id`, `ordkey`, `recptn_dt`)
- **원천**: `realtimeStationArrival`(환승역 3곳: 강남·잠실·사당) → `bronze_subway_arrival` + 역 마스터 dim 조인
- 노선 커버: 현재 2·4·8호선·신분당선 (역 3곳을 지나는 노선)

## 컬럼

| 컬럼 | 설명 |
|---|---|
| `statn_id` / `statn_nm` | 실시간 API 역 ID / 역명 |
| `ordkey` | 도착 순번 키 (grain — `btrain_no`는 신분당선 비정상으로 기각) |
| `recptn_dt` → `event_at` | 도착정보 생성시각 (KST) |
| `subway_id` / `route` | 노선 코드(1002 등) / 라벨("2호선" — seed 변환) |
| `train_line_nm` / `updn_line` | 방면("성수행 - 잠실새내방면") / 상하행·내외선 |
| `barvl_dt_sec` | **도착까지 남은 초** (0 = 도착/진입 상태) |
| `arvl_msg2` / `arvl_msg3` / `arvl_cd` | 도착 메시지("6분 20초 후") / 도착역명 / 상태 코드(0진입·1도착·2출발·3~5전역·99운행중) |
| `btrain_no` / `btrain_sttus` | 열차번호(참고용 — 신분당선 신뢰 불가) / 열차 종류(급행/일반) |
| `is_last_train` | **막차 여부** (0/1) ★신규 |
| `terminal_statn_nm` | **행선지(종착역)** ★신규 |
| `transfer_line_cnt` | **해당 역 환승 노선 수** ★신규 |
| `station_id`, `latitude`/`longitude`, `admin_dong_code`/`gu_code` | 역 마스터 조인 결과 (커버리지 1.00) |

## 활용 추천

1. **배차 간격**: 같은 (역, 노선, 방면)의 `event_at` 간격 → 시간대별 배차 리듬, 노선 간 비교. 간격이 벌어지는 시점 = 운행 흐트러짐 신호.
2. **대기시간 분포**: `barvl_dt_sec` 시간대별 분포 — "출근시간 강남역 2호선은 평균 몇 초 기다리나".
3. **막차 분석** ★: `is_last_train=1` 행의 `event_at` → 역·노선·방면별 실질 막차 시각. 심야 이동 수요(다른 도메인)와 대조.
4. **행선별 분리** ★: 같은 노선이라도 `terminal_statn_nm`별 배차 비율(예: 2호선 성수행 vs 내선순환).

## 주의

- **`event_at` 미래 이상치**: 원천이 전일 막차 안내를 잔존시키는 quirk로 `event_at`이 수집시각보다 미래인 행이 있었으나 **silver에서 필터됨(#66)** — `event_at <= utc_to_kst(ingested_at) + 스큐(기본 10분)` 상한으로 제거하므로 별도 필터 불필요.
- 역 3곳 표본이므로 "서울 지하철" 일반화 불가. 예측값(`barvl_dt_sec`)은 예측이지 실측 도착이 아님.

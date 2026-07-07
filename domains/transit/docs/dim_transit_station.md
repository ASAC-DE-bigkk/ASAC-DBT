# dim_transit_station — 지하철역 차원

- **한 행** = 지하철역 1개 (역×노선) / **키**: `station_id` / 784행
- **원천**: `subwayStationMaster` @weekly → `bronze_subway_station_master` 최신 스냅샷
- 물화: table (주 1회 변동 공간 조인을 미리 계산)

## 컬럼

| 컬럼 | 설명 |
|---|---|
| `station_id` | 마스터 역 ID(`BLDN_ID`) — ⚠️ 실시간 `statn_id`와 **다른 체계**, 서로 조인 불가 |
| `station_name` | 역명 원문("잠실(송파구청)") |
| `station_name_join` | **조인용 정규화 역명**(괄호 제거: "잠실") — 실시간과의 조인 키 절반 |
| `route` | 노선 라벨("2호선", "신분당선(연장)" — 괄호 유지, 조인 키 나머지 절반) |
| `latitude` / `longitude` | WGS84 좌표 |
| `admin_dong_code` / `gu_code` / `gu` / `admin_dong` | 경계 조인으로 계산한 행정동 (서울 밖 역은 null — 정상) |
| `load_date` | 스냅샷 기준일 (계보) |

## 활용 추천

1. **실시간 도착과 조인**: (`station_name_join`, `route`) — 단 route는 실시간의 `subway_id`를 seed(`seoul_subway_line_code`)로 라벨 변환 후. 직접 쓰지 말고 이미 조인된 `slv_transit_subway_arrival`을 쓰는 게 안전.
2. **역세권 분석의 앵커**: 역 좌표 기준 반경/동 단위로 상권·인구 도메인과 결합 — "역세권 동"의 정의 축.
3. **동별 역 밀도**: `admin_dong_code`별 역 수 — 교통 인프라 공급 지표.

## 주의

- 좌표는 691/784, 행정동은 400/784 (나머지 = 경기·인천 역, 서울 경계 밖이라 null이 맞음).
- 환승역은 노선 수만큼 행이 있음(잠실 = 2호선 행 + 8호선 행) — 역 단위 집계 시 `station_name_join` distinct.

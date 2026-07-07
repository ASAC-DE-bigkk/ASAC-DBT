# dim_transit_parking — 공영주차장 차원

- **한 행** = 공영주차장 1개소 / **키**: `parking_id`(`PKLT_CD`) / 850행
- **원천**: `GetParkInfo` @weekly → `bronze_park_info_master` 최신 스냅샷 (중복행은 결정적 dedup)
- 물화: table

## 컬럼

| 컬럼 | 설명 |
|---|---|
| `parking_id` / `parking_name` | 주차장 코드(실시간 `parking_id`와 **동일 체계 — 조인 키**) / 이름 |
| `addr` / `addr_gu` | 주소 / 주소 첫 토큰(구) — 경계 조인 결과와 대조 검증용 |
| `parking_kind_nm` | 유형(노외/노상 등) |
| `charge_free_nm` | 유·무료 |
| `total_capacity` | 총 주차면 수 (null 있음) |
| `wd_oper_bgng_tm` / `wd_oper_end_tm` | **평일 운영 시작/종료 (HHMM 문자열)** ★신규 |
| `we_oper_bgng_tm` / `we_oper_end_tm` | **주말 운영 시작/종료** ★신규 |
| `night_free_open_yn_nm` | **야간 무료개방 여부** ★신규 |
| `latitude` / `longitude` | 좌표 (결손 많음 — 아래 주의) |
| `admin_dong_code` / `gu_code` / `gu` / `admin_dong` | 경계 조인 행정동 |

## 활용 추천

1. **실시간 점유와 조인**: `parking_id`로 `slv_transit_parking`과 — 이미 silver에 좌표·행정동은 붙어 있으니, dim은 **요금·운영시간·유형** 속성을 더할 때 조인.
2. **운영시간 내 점유율** ★: `event_at`의 HHMM이 `wd/we_oper_bgng~end_tm` 구간 안인 행만 집계 — 폐장 시간대 0% 노이즈 제거. 요일에 따라 평일/주말 컬럼 선택.
3. **야간 주차 공급** ★: `night_free_open_yn_nm` = 무료개방 개소의 동별 분포 — 심야 막차(`is_last_bus`/`is_last_train`) 데이터와 묶으면 "심야 교통+주차" 그림.
4. **유·무료/유형별 비교**: `charge_free_nm`·`parking_kind_nm` 그룹으로 점유 패턴 차이.

## 주의

- **좌표 결손**: 850개소 중 유효 좌표 소수(행정동 커버리지 0.14) — 실시간 제공 123개소는 대부분 유효(silver 0.96). 좌표 필요한 분석은 silver 쪽 사용.
- `addr_gu` vs 경계 조인 `gu` 불일치 24건 존재(단순화 경계의 경계부 오배정, warn으로 추적 중) — 구 단위 집계 시 어느 쪽을 기준 삼을지 명시할 것.
- 운영시간은 HHMM 문자열("0900") — 숫자 비교 전 캐스트 필요, "0000"~"2400" 표기 혼재 가능.

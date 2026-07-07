# slv_transit_parking — 공영주차장 실시간 점유

- **한 행** = 주차장 1개의 20분 간격 스냅샷 / **grain**: (`parking_id`, `event_at`)
- **원천**: 서울 열린데이터 `GetParkingInfo`(실시간 123개소) → `bronze_parking`
- **증분**: incremental merge (시간당 변환 가정)

## 컬럼

| 컬럼 | 설명 |
|---|---|
| `parking_id` / `parking_name` | 주차장 코드(`PKLT_CD`, dim 조인 키) / 이름 |
| `event_at` | 원천 갱신시각(`NOW_PRK_VHCL_UPDT_TM`) KST — 대표 시각 |
| `now_prk_vhcl_cnt` | **현재 주차 대수** (점유율 분자). 미제공 개소는 null |
| `total_capacity` | 총 주차면 수(`TPKCT`, 분모). null 있음 |
| `prk_stts_nm` | 실시간 데이터 상태 설명("현재~20분이내 연계데이터 존재" 등) |
| `latitude` / `longitude` | 좌표 (dim 마스터 유래) |
| `admin_dong_code` / `gu_code` | 행정동·구 코드 (공간축, 커버리지 ~0.96) |
| `ts_source` | 원본 시각 문자열 (보존용) |

## 활용 추천

1. **점유 곡선**: 개소별 `now_prk_vhcl_cnt / total_capacity`를 `event_at` 시간대로 — "몇 시에 차기 시작해 몇 시에 만차되나". 만차 = 점유율 ≥ 0.95 근사.
2. **동/구별 주차 압력**: 동 단위 평균 점유율 히트맵 — 상권·유동인구 도메인과 조인해 "주차 공급이 병목인 동" 도출.
3. **운영시간 필터**: `dim_transit_parking`의 `wd/we_oper_bgng/end_tm`과 조인해 **운영시간 내 점유율**만 집계(폐장 시간대 노이즈 제거) — HHMM 문자열 비교.
4. **요일×시간 프로파일**: `event_at`에서 요일 추출해 평일/주말 패턴 비교 (dim의 주말 운영시간과 함께).

## 주의

- `now_prk_vhcl_cnt`/`total_capacity` null 행 존재(원천 미제공) — 점유율 계산 시 둘 다 not null + `total_capacity > 0` 필터.
- 같은 `event_at`이 여러 수집에 반복될 수 있으나 grain merge로 중복 없음.

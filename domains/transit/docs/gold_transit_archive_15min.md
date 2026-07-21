# 기반 아카이브 gold 3종 + tier dim (#286)

원본(R2 raw·Iceberg bronze)이 **주 경계(월~일 KST) 삭제**(ASAC-DAG #369)되는 구조에서,
transit 의 장기 이력은 이 아카이브 gold 가 유일하다. 사용자향 gold(9종)는 전부 여기서
파생된다. 계약(source·time·space·grain·tier·보존)은 [dbt_contracts.md](dbt_contracts.md).

**공통 계약**

- incremental merge 전용, **`full_refresh=false` 고정** — 재빌드는 지난주 이전 이력의 영구 소실.
  스키마 변경 등으로 재생성이 필요하면 기존 테이블 CTAS 백업 후 수동 진행.
- `bucket_at` = KST 벽시계 N분 버킷(`transit_time_bucket` 매크로). 시간축 계약(`_at`) 부합.
- 증분 임계 `max(bucket_at) - 3h` (silver -2h lookback + 버킷 경계 여유, #67 근거 공유).
- **주 경계 직전 마지막 변환 실패 = 영구 손실** — 운영 보강은 ASAC-DAG #443.

## gold_transit_dong_15min — 동×15분 상태판 아카이브

- **한 행** = 행정동 1개 × 15분 버킷의 버스·지하철·주차 지표 / **grain**: (`admin_dong_code`, `bucket_at`)
- `gold_transit_dong_hourly`(#67)의 15분판. 구조(3원 outer 결합) 동일, 추가 컬럼 2계열:
  - **`bus_*_t1`**: tier1(간선·광역) 한정 버스 지표. 시간대끼리 비교하는 파생(G4 리듬, G10 예측)은
    반드시 이것만 소비 — tier2 는 지정 시각(09·19시)에만 전 노선 스냅샷으로 관측돼 시간대별
    표본 구성이 달라진다(#440·#449). 전 티어 `bus_*` 는 현재 상태·커버리지(420개 동) 용도.
  - **`*_last_event_at`**: 소스별 버킷 내 최신 관측 시각. '지금' 카드(G1)의 "N분 전 관측" 표기 근거 —
    특히 tier2 만 다니는 동의 버스 값은 수 시간 전일 수 있어 이 표기가 필수다.
- 버스는 30분 주기(#440)라 15분 버킷의 절반이 비는 것이 정상(버스 축 아카이브는 route_section_30min 담당).

## gold_transit_route_section_30min — 노선×구간×30분 버스 아카이브

- **한 행** = 노선 1개 × 구간(sectOrd) 1개 × 30분 버킷 / **grain**: (`bus_route_id`, `sect_ord`, `bucket_at`)
- 30분 버킷 = 티어링 후 런 1회 스냅샷. 3분 수집 복귀 시에도 grain 유지 가능.
- **전 티어 저장 + `tier` 스탬프** — 필터는 파생 몫(G3 프로파일은 `tier=1`만).
  tier 는 빌드 시점 분류의 기록이며 과거 버킷 소급 재분류 없음.

## gold_transit_parking_lot_15min — 주차장 개소×15분 점유 아카이브

- **한 행** = 주차장 1개소 × 15분 버킷 / **grain**: (`parking_id`, `bucket_at`), 버킷당 ~3관측(5분 수집)
- `occ_avg`/`occ_min`/`occ_max` + **`occ_last`**(max_by 최신 점유율): G2 만차 리스크의
  점유 변화율은 연속 버킷 `occ_last` 의 lag 로 계산한다(버킷 평균 차보다 민감도 좋음).
- `capacity_last` 로 점유대수 복원 가능(occ_last × capacity_last).

## dim_transit_bus_route_tier — 노선 티어 (routeType 원천 조인, #471)

- tier 원천은 `bronze_bus_route_master.tier` — ASAC-DAG 가 수집 정책(`BUS_TIER1_TYPES`:
  routeType 3 간선·6 광역 = 1, 그 외 2)으로 계산해 적재한다. dim 은 그 값을 그대로 조인 —
  **tier 정의의 단일 출처는 collector 정책이며 dbt 는 재계산하지 않는다**.
- 마스터의 `max(load_date)` 스냅샷만 취한다(주간 멱등 적재라 이번 주 적재가 비어도 지난
  스냅샷으로 tier 유지). 매 빌드 전체 재계산(table).
- **관측 tier 병기**(검증용): dense 런 등장으로 역산한 `observed_tier`·`tier_mismatch` 를 함께
  둔다. 분류엔 미사용 — 원천 tier2 인데 dense 런에 반복 등장하면(=수집 정책↔reference 불일치)
  드러나는 안전망이다.
- 이력: 초기(#286)엔 관측 시간대 종류 수로 역산했으나, dense 창에 미운행한 tier1 을 놓쳐
  (실측 140 vs 원천 165) #471·#315 에서 원천 조인으로 전환했다.

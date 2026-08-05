# Transit dbt contract guide

transit 도메인 dbt PR에서 지켜야 할 **source · 수집주기 · time · space · grain · tier ·
보존 · gold** 계약을 한 곳에 정리한다. 시간/공간 공통축은 `asac_axes` package 기준(#48).

이 문서는 "지금 이 상태가 맞다"고 보여줄 수 있는 **확정 계약**만 담는다. 계획·오픈
퀘스천은 GitHub 이슈에 둔다.

## 적용 범위

- dbt project: `domains/transit` (`dbt_project.yml`, `profiles.yml`)
- 모델: `models/{dim,silver,gold}`, 테스트: `tests/`, 매크로: `macros/`
- 원천 적재: ASAC-DAG `domains/transit` (bronze), 웨어하우스 `iceberg[_dev].<TRANSIT_SCHEMA=transit>`
- 환경 분리: prod/dev 동일 스키마 `transit`, 카탈로그(`iceberg`/`iceberg_dev`)가 분리(#204)

---

## 1. Source contract

`models/sources.yml`의 `transit_bronze` — 전부 `iceberg[_dev].transit.bronze_*`.
`loaded_at_field=ingested_at`, 실시간 3종은 staleness freshness(warn 60m / error 180m, #207).

| source | table | 소비 silver | not_null 계약 |
|---|---|---|---|
| `subway_arrival` | `bronze_subway_arrival` | silver_transit_subway_arrival | `raw`, `ingested_at` |
| `parking` | `bronze_parking` | silver_transit_parking | `raw`, `ingested_at` |
| `bus_position` | `bronze_bus_position` | silver_transit_bus_position | `raw`, `ingested_at` |
| `bus_route_master` | `bronze_bus_route_master` | dim_transit_bus_route_tier | `bus_route_id`(unique), `route_type`?, `tier`(1/2) |
| `subway_station_master` | `bronze_subway_station_master` | dim_transit_station | `bldn_id`·`bldn_nm`·`route`·`load_date` (주1회, freshness null) |
| `park_info_master` | `bronze_park_info_master` | dim_transit_parking | `pklt_cd`·`pklt_nm`·`load_date` (주1회, freshness null) |

- 실시간 raw 는 페이로드 원본: 버스=XML(`<itemList>` 다수), 지하철·주차=JSON.
- `bus_arrival`·`subway_position` 은 **silver 미소비라 수집하지 않는다**(#212). 소스 미등록.
- `bus_route_master.route_type` 은 `not_null` 을 걸지 않는다 — 원천이 빈 값을 주면 source
  test 실패가 dbt build 를 정지시켜(변환 중단) 얻는 것보다 잃는 게 크다. 빈 값은 tier=2 로 흡수.

---

## 2. 수집 주기 계약 (ASAC-DAG, silver 신선도 전제)

| dataset | 주기 | 근거 |
|---|---|---|
| 지하철 도착 | 3분 | #369 |
| 주차장 | 5분 | 원천 갱신 ~5분 |
| **버스 위치** | **티어링 + 시간창** (#440·#449) | 아래 |
| 노선 마스터 | 주 1회(@weekly) | 개폐 반영 |
| silver/gold 변환 | 15분(`*/15`) | #443, 실측 build 344s |

**버스 시간창(#449)**: DAG 은 `*/10` 로 깨어나되 실제 호출은 `collect_plan()`이 정한다.
- 평일 출퇴근(07~09·17~19시) 10분, 그 외 창 내 시각은 시간당 1런
- 주말 낮(09~20시) 20분, 그 외 시간당 1런
- 공통 01~05시 제외(실측 02·03시 운행 사실상 중단), 00시(막차) 포함
- tier1(간선·광역 ~165) 매 런, tier2(그 외 ~563)는 09·19시 정시 런 = 전 노선 스냅샷
- 일 호출 평일 9,211 / 주말 8,221 (운영계정 10,000/일 이내)

> 버스 위치가 30분 주기라 15분 버킷은 절반이 빈 것이 정상 — 버스 축 아카이브는
> `gold_transit_route_section_30min`(30분 grain)이 담당한다.

---

## 3. Time contract

`_at` 접미사 = **KST 벽시계**(tz 없는 timestamp), `_date` = 날짜. 시간축은 **필터 전용**.

| 역할 | 컬럼 | 규칙 |
|---|---|---|
| source event time | `event_at` | 버스 dataTm / 지하철 recptnDt / 주차 갱신시각, KST |
| 15분 버킷 | `bucket_at` | `transit_time_bucket(event_at, 15)` — KST 벽시계 유지 |
| 30분 버킷 | `bucket_at` | `transit_time_bucket(event_at, 30)` (버스 아카이브) |
| 시간 버킷 | `hour_at` | `date_trunc('hour', event_at)` |
| 신선도 상한 | — | `event_at <= utc_to_kst(ingested_at) + skew` (#66, skew=`transit_freshness_skew_minutes`=10) |

- 미래 event_at(원천 전일 잔존 등)은 silver 에서 상한 게이트로 차단(#66). 하한 없음.
- 감시 warn: 최근 `transit_freshness_monitor_hours`(24h) 내 드랍 비율 > `transit_freshness_warn_ratio`(0.05).

---

## 4. Space contract (공통축 #48)

- **조인 키는 공간축만**: `admin_dong_code`(행안부 10자리) + `gu_code`(앞 5자리) +
  `latitude`/`longitude`(WGS84). 버스 gpsX/Y·주차/역 좌표를 런타임 point-in-polygon 으로 할당.
- 커버리지 게이트(`asac_axes.axis_coverage`) — 전 노선(ALL) 수집으로 서울 외곽 정류장이
  경계 밖 NULL 이 되는 걸 감안한 실측 임계:

| 모델 | min_ratio | 사유 |
|---|---|---|
| silver_transit_bus_position | **0.85** | ALL 수집으로 외곽 노선 정류장 경계 밖(실측 0.90). 6노선 시절 0.90 은 마진 없음 |
| silver_transit_subway_arrival | **0.45** | 경로형 ALL 로 경기·인천 역 유입(실측 0.48) |
| silver_transit_parking | 0.90 | 실시간 lot 은 대부분 유효 좌표 |

> 크로스 도메인 gold(×weather·×citydata·×culture)는 `admin_dong_code`(또는 `area_cd`·좌표)로
> 조인하되 **버킷 시각(bucket_at/hour_at) 정렬**을 함께 쓴다. 이는 원시 event_at 조인이 아니라
> 같은 grain 의 시각 정렬이다(팀 공통축 규약의 '시간축 조인 금지'는 원시 event_at 조인 대상).

---

## 5. Grain & dedup

| 모델 | grain | 증분 |
|---|---|---|
| silver_transit_bus_position | (veh_id, data_tm) | merge, -2h lookback, `row_num=1` dedup |
| silver_transit_subway_arrival | (statn_id, ordkey, recptn_dt) | merge, dedup |
| silver_transit_parking | (parking_id, event_at) | merge, dedup |

- silver 3종은 `row_number() over (partition by <grain> order by ingested_at desc) = 1` 로
  배치 내 중복·재시도 재유입을 접는다. grain unique 는 `assert_*_grain_unique` 가 감시.

---

## 6. Tier contract (버스, #471·#315)

- tier 원천은 `bronze_bus_route_master.tier` — DAG 가 수집 정책(`BUS_TIER1_TYPES`: routeType
  3 간선·6 광역 = 1, 그 외 2)으로 계산해 적재. **tier 정의의 단일 출처는 collector 정책이며
  dbt 는 재계산하지 않는다**(값 복제 시 두 곳이 어긋날 위험).
- `dim_transit_bus_route_tier` 는 마스터의 `max(load_date)` 스냅샷만 취한다(멱등 적재라 이번 주
  적재가 비어도 지난 스냅샷으로 tier 유지). 관측 tier(dense 런 등장)는 `tier_mismatch` 로 병기 —
  원천↔수집 불일치 감지용 안전망(분류엔 미사용).
- **버스 역할 분리(#440)**: 아카이브는 전 티어 저장 + tier 스탬프 / 시간대 비교 지표
  (리듬·프로파일·예측)는 `tier=1` 한정(`*_t1` 컬럼) / 현재 상태(dong_now)는 전 티어 + 관측 시각.

---

## 7. 보존 & 아카이브 개시일

- 원본(R2 raw·bronze)은 **주 경계(월~일 KST) 삭제**(#369) — 실질 보존 0~7일. 마스터는 제외.
- gold 아카이브 6종은 `full_refresh=false` 고정 — 재빌드 = 지난주 이전 이력 영구 소실.
- **아카이브 개시일** `var transit_archive_start_at`(2026-07-21 09:00 KST): 이 시각 이전은
  gold 아카이브에 넣지 않는다(정책 전환 전 오염 구간 차단). 아카이브 6종·파생의 하한.
- purge 선행 게이트(#443): `gold_transit_dong_15min.max(bucket_at) >= 이번 주 월요일 00:00 KST`
  일 때만 삭제(변환이 밀리면 skip). 아카이브가 유일 장기 저장소라 변환 성공이 보존의 전제.

---

## 8. Gold 계약 (materialization · full_refresh)

**기반 아카이브 3종** (incremental merge, `full_refresh=false`, day 파티셔닝):
`gold_transit_dong_15min`(동×15분) · `gold_transit_route_section_30min`(노선×구간×30분) ·
`gold_transit_parking_lot_15min`(주차 개소×15분).

**사용자향 9종** (선정 G1~G10 중 G5 배차·속도는 티어링으로 보류):

| ID | 모델 | grain | 재질 |
|---|---|---|---|
| G1 | gold_transit_dong_now | admin_dong_code | table(스냅샷) |
| G2 | gold_transit_parking_full_risk / _profile | parking_id / (parking_id,dow,hh) | table |
| G3 | gold_transit_bus_route_comfort | (route,sect_ord,dow,hh) tier1 | table |
| G4 | gold_transit_dong_rhythm | (dong,dow,hh) | table |
| G6 | gold_transit_x_weather_dong_hourly | (dong,hour_at) ×weather | incr, `full_refresh=false` |
| G7 | gold_transit_event_access | event_ref ×culture | table |
| G8 | gold_transit_supply_x_demand_hourly | (area_cd,hour_at) ×citydata | incr, `full_refresh=false` |
| G9 | gold_transit_lastmile_dong_hourly | (dong,hour_at) ×citydata | incr, `full_refresh=false` |

(G10 forecast_card 는 제거 — 상류 citydata ppltn_forecast 삭제 대응, ASAC-DBT#432)

**기존**: `gold_transit_dong_hourly`(#67, 동×시간, incr) — 15분판 dong_15min 이 아카이브 축.

계약 세부:
- 크로스 도메인 incr gold(G6·G8·G9)는 **소스별 독립 임계**를 쓴다 — 각 소스가 실제 채운 행의
  `max(hour_at)-3h`. 공유 임계는 느린 소스의 backfill 을 영구 배제(dev 실증).
- `is_precip`(G6)은 예보 없음을 `false` 아닌 **null 보존**. 추천 불리언(G8·G10)은 조인 미스 시
  `coalesce(..., false)`로 3-상태 제거.
- 표본 누적 계열(리듬·프로파일·예측)은 `*_base_n` 노출 — 표본 부족 판단은 소비 측 몫.

---

## 9. 집계 매크로 (단일 출처, `macros/aggregates.sql`)

같은 표현식 복붙이 모델별로 어긋나는 걸 막는다(아카이브는 `full_refresh=false`라 어긋난 이력이 고정).

| 매크로 | 규칙 |
|---|---|
| `transit_weighted_avg(val, weight)` | 관측수 가중 평균 + null 행 weight 분모 제외 |
| `transit_bus_congestion_avg(col, extra)` | 혼잡도 평균, 0='정보없음' 제외(#67) |
| `transit_parking_occ_ratio(cnt, cap)` | 점유율, 총면수 null·0 가드(#72 소수문자열 캐스트) |
| `transit_time_bucket(ts, minutes)` | N분 버킷(KST 벽시계 유지) |

# 사용자향 gold 2차 — 프로파일·카드 6종 (#287·#288·#290·#291·#292)

아카이브(#286)와 1차 3종(#289) 위에 얹는 파생 gold. 공통 성격:

- **프로파일 계열**(리듬·주차 프로파일·노선 쾌적도): 아카이브 전량 재집계 table.
  `*_base_n`(기여 버킷 수)을 노출하고 표본 부족 판단은 소비 측 임계로 — 4주 누적 시
  15분 계열 칸당 ~16, 30분 계열 ~8.
- **카드 계열**(만차 리스크·행사 접근·예측 카드): 매 변환 재생성 스냅샷 table.
  기준 시각은 벽시계가 아니라 아카이브 프런티어.
- 버스가 들어가는 시간대 비교는 전부 **tier1 한정**(#440 원칙 ②).

| 모델 | grain | 한 줄 |
|---|---|---|
| `gold_transit_dong_rhythm` (#287 G4) | 동×dow×hh | "금요일 18시가 최악" 히트맵. G1 평시 대비·G10 기준선 |
| `gold_transit_parking_profile` (#288) | lot×dow×hh | 주차장 평시 점유·만차 확률(occ_max≥0.95 버킷 비율) |
| `gold_transit_parking_full_risk` (#288 G2) | lot | 현재 점유 + 최근 1시간 추세 → "만차까지 N분" + 이 시간대 만차 확률 |
| `gold_transit_bus_route_comfort` (#288 G3) | 노선×구간×dow×hh | "8시대 이 구간 혼잡 4.2/5" (tier1 165노선 한정) |
| `gold_transit_event_access` (#290 G7) | event_ref | 최근접 역·주차장(전 행사, dim 기반) + 행사 시간대 만차 확률 |
| `gold_transit_supply_x_demand_hourly` (#291 G8) | 핫스팟×시간 | 수요(인구·혼잡·승하차) vs 주차 여유 + 압박 플래그. 동 축 공급 지표는 제외(중복) |
| `gold_transit_forecast_card` (#292 G10) | 핫스팟×미래시각 | 기대 인구 + 날씨 예보(G6 재사용) + 리듬 기준선 → "내일 이 시간" 카드(+3일) |

## 소비 시 주의

- **만차 예상 분**(`minutes_to_full_est`): lot 자신의 최신 버킷 -45분 이내 **연속 4버킷** 선형
  추세 — 결측 있는 lot 은 rate null(관측 4건이 수 시간에 걸쳐 기울기가 희석되는 것 방지).
- **행사 시간대 만차 확률**: 행사 시각 미상은 19시 근사(`is_evt_hh_imputed=true` 로 구분) +
  전 요일 평균. 프로파일은 lot 자신의 최신 관측 시각 칸으로 조인.
- **G8 범위(#291 결론)**: 핫스팟에서만 얻을 수 있는 것만 — 수요(인구·혼잡·승하차)와 압박
  판정용 최소 공급(주차 점유율). 동 축 공급 지표(관측 lot·버스 차량·지하철 도착)는
  citydata `gold_citydata_ppltn_x_transit_hourly` 또는 `gold_transit_dong_15min` 을
  `admin_dong_code` 로 조회 — 같은 동 핫스팟마다 같은 값이 반복될 뿐이라 여기 두면 중복.
  `is_parking_pressured` 는 혼잡 라벨×점유 0.8 단순 규칙(합성 지수 없음, 공식은 #291).
- **불리언 3-상태 없음**: G8 `is_parking_pressured`·G10 `transit_recommended`·`parking_busy_expected`
  는 조인 미스 시 `coalesce(..., false)` — `where not ...` 가 행을 조용히 잃지 않는다.
- **is_precip(G6)**: 예보 없는 동·시각은 `false`(비 안 옴) 아닌 **null**(정보 없음) — rain-vs-dry
  비교에서 무데이터를 맑음 표본으로 세지 않는다.
- **크로스 gold 소스별 임계(G6·G8·G9)**: 소스마다 독립 임계(그 소스가 채운 행의 max-3h) — 한
  소스가 멈춰도 다른 소스 backfill 이 영구 배제되지 않는다.
- **G10 추천**: v1 단순 규칙(주차 평시 0.8↑ or 강수 예보). 문구화는 대시보드 몫.
- 운영 초기 몇 주는 모든 프로파일 표본이 얇다 — base_n 배지 필수.

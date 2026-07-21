# culture gold 티어링 v2 — 전 도메인 gold 실측 기반 재채점

날짜: 2026-07-21 · 근거 이슈: #269 (트래킹) · 선행: `ask-seoul/culture-gold-marts-tiering.tsv` v1 (7/20)

## 왜 다시 하나

v1(7/20)은 두 가지 전제 위에서 채점했다. 7/21 카탈로그 스냅샷 갱신(77→112 테이블)으로 전 도메인 gold를 전수 실측한 결과, 둘 다 틀렸다.

1. **"commerce gold가 복구되면 결제 lift 마트가 가능하다"** — 오류. commerce gold 22개는 전부 인허가(개·폐업) 계열이고, 결제·매출 컬럼(`amt/sales/pay/card/revenue/spend`)은 도메인 전체에 한 건도 없다. #6·#9의 블로커는 "skip이라 없다"가 아니라 "그 데이터가 애초에 없다"였다.
2. **"크로스도메인 마트는 culture가 만들어야 한다"** — 불필요. 타 도메인이 이미 culture를 소비하는 크로스 마트 3개를 라이브로 운영 중이다(아래 채택 절).

또한 v1 작성(7/20 낮) 직후 저녁 스프린트에서 4행의 구축 상태가 바뀌었다(모멘텀 PR#271 머지, booking_curve #274 재정의 구축, calendar_density #272 구축, event_crowd v2).

## 결정 3 (사용자 승인, 7/21)

1. **채택 + 중복 계획 드롭** — 타 도메인 x_culture 마트와 겹치는 #11/#12/#13은 드롭하고 그들 마트를 Q&A 소비로 채택. 중복 빌드 0, 도메인 경계 존중. 캐비앗: SLA·계약은 소유 도메인 소관이며 소비는 source 경유 read-only.
2. **전면 재채점 TSV v2** — 21행 전부 갱신 + 채택 3행 편입(22~24) = 24행.
3. **dine_around 1차 공개 승격** — festival_commerce_boost 빈자리는 유일하게 진짜 해제된 dine_around로. calendar_density는 이미 external=true 기적용이라 사후 추인 → 외부 라인업은 6→7개.

## 외부 공개 라인업 v2 (7)

| 마트 | 상태 |
|---|---|
| event_schedule | 완료 (진입점 허브) |
| activity_by_dong | 완료 |
| boxoffice_daily + 모멘텀 | 완료 (PR#271) |
| booking_curve (순위 궤적 재정의) | 완료 (#274) |
| event_crowd v2 | 완료 (#282 PR#283) |
| calendar_density | 완료 (#272, 사후 추인) |
| **dine_around** | **미구축 — 유일한 신규 구축 대상** |

## 채택 3 (Q&A 소비, 타 도메인 소유)

| 마트 | 소유 | 실측 (7/21) | 대체 |
|---|---|---|---|
| `gold_weather_x_culture_event_risk_daily` | weather | 577,388행 · ~2027-05 | #12 outdoor_advisory · #13 weather_fit |
| `gold_transit_event_access` | transit | 986행 · ~2026-12 | #11 event_transit_load (접근성 각도) |
| `gold_citydata_ppltn_x_culture_daily` | citydata | 1,620행 · 당일까지 | (event_crowd 상보 — 동×일 그레인) |

## 드롭 2 + 재평가 1

- **#6 festival_commerce_boost 드롭** — 결제 데이터 부재. license_flow_daily(276만 행) 기반 재정의판은 D±n 단기 lift가 인허가 데이터 특성상 불가, 월/분기 B2B 추세로 변질 → YAGNI.
- **#9 event_impact_funnel 드롭** — 소비(결제) 축 대체 불가.
- **#10 genre_geo_match β 후속 유지, 근거 승격** — 원안 소스가 실존 확인됨(citydata `ppltn_demographics` + `purchasing_power_daily`, admin_dong 조인축).

## dine_around 설계 방향 (구현은 별도 사이클)

- 소스: `gold_culture_activity_by_dong`(426동 스카폴드) × commerce `gold_license_dong_category_matrix`(식품 카테고리 active 230,717건 · 220동, `admin_dong_code` 보유).
- 조인축: #48 합의 행안부 canonical `admin_dong_code`. commerce는 자기 스키마 밖 접근 금지 원칙에 따라 source 경유 read-only.
- 그레인·컬럼·contract는 feature 이슈에서 확정.

## 산출물

- [x] `ask-seoul/culture-gold-marts-tiering.tsv` v2 (24행)
- [x] 본 설계 문서
- [x] #269 정정 코멘트 (commerce 전제 오류 실측 + 라인업 v2)
- [x] dine_around feature 이슈 → #308

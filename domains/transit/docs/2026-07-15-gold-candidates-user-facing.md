# Transit 사용자향 Gold — 선정 10종

- 상태: **선정 확정** (2026-07-20) — 구현 준비 단계
- 이력: 2026-07-15 후보 10선 초안 → 07-16 rev.2 수집주기·보존정책 반영 → 07-16 rev.3 크로스 후보 18종 확장 → **07-20 rev.4 사용자 선정 10종 확정**
- 기준 도메인: transit. 기존 gold `gold_transit_dong_hourly`(#67, 동×시간 교통 상태판)의 축(동코드×시간, 버스·지하철·주차 결합)을 유지·확장한다.
- 데이터 근거: `iceberg_dev` 실측(2026-07-15) + DAG 설정 실측(2026-07-16)

---

## 0. 전제 — 수집 주기·보존 정책과 설계 원칙

| 항목 | 값 | 출처 |
|---|---|---|
| 버스 위치 수집 | **티어링(#440, 2026-07-20 반영)** — tier1(간선·광역) 30분, tier2(그 외) 하루 3회(07·13·19시 KST). 일 10,000콜 예산 제약. 노선 5→728로 확대(실측 관측 650+노선·420개 동), 주기는 3분→30분으로 하향 | `transit_bus_bronze.py`, 이슈 #440 |
| 지하철 도착 수집 | **3분** (`*/3`) | `transit_subway_bronze.py` |
| 주차장 수집 | **5분** (`*/5`) | `transit_parking_bronze.py` |
| silver/gold 변환 | 1시간 (`@hourly`) | `transit_transform.py` |
| 원본 보존 | **주 경계 삭제** — 이번 주(월 00:00 KST~)만 유지, 다음 주 시작 시 지난주 R2 raw + Iceberg bronze 삭제. 실질 보존 0~7일 가변 | `seoul_transit/maintenance.py` (#369) |

**원칙 1 — gold가 유일한 장기 저장소다.** bronze가 주 경계로 사라지므로 gold를 silver에서
재빌드(full-refresh)하면 지난주 이전이 영구 소실된다. 모든 gold는 증분(merge) 전용 +
full-refresh 가드 필수. 집계 grain이라 영구 보존 비용은 무시할 수준 — **gold = 아카이브 레이어**.

**원칙 2 — '평시 프로파일' 계열은 아카이브 gold에서 파생한다.** 여러 주 평균이 필요한 지표는
silver로 만들 수 없다(월요일 아침엔 지난 9시간치뿐). 기반 gold를 먼저 쌓고 그 위에서 파생.
운영 초기는 표본이 얇고 주가 지날수록 좋아진다.

**원칙 3 — 소스별 주기에 맞는 grain.** 지하철(3분)·주차(5분)는 **15분 grain**(주차 5분 관측으로
점유 변화율 산출). 버스는 티어링(#440) 이후 30분 주기라 **30분(또는 시간) grain** — 15분 버킷은
절반 이상이 빈다. 사용자 '지금' 신선도를 위한 변환 주기 단축(예: 15분)은 별도 운영 작업.

### 데이터 제약 (실측)

1. **지하철 실시간은 6역·4개 동** — 지하철 실시간 지표는 커버리지 한계 명시.
   `dim_transit_station`(전 노선 700+역)으로 '최근접 역' 용도는 전 지역 가능.
2. ~~주차 점유율 cast 버그~~ — **해소 확인(2026-07-20)**: silver가 double 경유 매크로
   (`transit_int_from_numeric_str`, #72)로 수정돼 실측 전건 non-null. 단
   `gold_transit_dong_hourly`의 관련 주석(96~100행)은 낡은 정보 — gold 작업 시 주석 정리.
3. 크로스 조인 상대 도메인(citydata·weather 등)의 보존 정책은 별도 — 과거분 유지 여부 도메인별 확인.
4. citydata에 핫스팟(120곳) 기준 크로스 gold 기존재(`gold_citydata_ppltn_x_transit_hourly` 등) —
   G8(수요×공급)은 착수 전 중복 정리 필요.
5. **버스 티어링(#440) 영향 (2026-07-20 조사)**:
   - G5(배차·속도)는 30분 스냅샷으로 성립 불가 — 재검토 대상(§2 표기). `bronze_bus_arrival`(도착정보)은
     스키마만 있고 0행이라 대체 원천도 현재 없음.
   - tier2 노선은 07·13·19시에만 관측 → **시간대별 관측 노선 구성이 달라져** 카운트류 지표
     (bus_obs_cnt 등)는 수집 정책 아티팩트를 반영하고, 평균류(congestion_avg)도 구성 편향 발생.
   - **버스 역할 분리 원칙 (2026-07-20 확정)**:
     ① 아카이브(기반 gold)는 **전 티어 저장 + tier 구분 컬럼** — 원본 주 단위 삭제 구조에서
        필터는 파생 단계 몫, 저장은 무조건 전부.
     ② 시간대 비교 지표(리듬·프로파일·예측의 버스 성분)는 **tier1 한정 필터** — 구성 편향 회피.
     ③ 현재 상태·커버리지(G1 등)는 **전 티어 + 관측 시각(freshness) 표기** — 시간대 비교가
        아니므로 왜곡 없음, 420개 동 커버리지 유지.
   - 반대급부: 노선 5→650+, 동 커버리지 94→420(전 25개 구) — 동 grain gold의 공간 커버리지는 대폭 개선.
   - citydata `silver_citydata_transit_ppltn` mode='bus'(핫스팟 121곳, 5분 주기, 승하차 5/10/30분·누적,
     주간 시간대 약 80% 채움)를 **버스 수요 축 보강**으로 활용 가능 — 단 위치 기반 공급/혼잡 지표의
     대체는 아니며(승하차 인구 성격), 핫스팟 동 한정. ⚠ dev 실측상 citydata 수집이 2026-07-17 이후
     중단 상태 — 운영 확인 필요.

---

## 1. 기반 아카이브 gold 3종 (선행 인프라)

사용자향 gold 전체의 하부 구조. 매시 변환에서 안정적으로 merge되면 주 경계에서 bronze가
사라져도 사용자향 지표는 전부 재계산 가능하다. **주 경계 전 마지막 변환 실패 = 영구 손실**
→ 변환 DAG 실패 알림·주말 실행 보장이 운영 요건.

| 테이블 | grain | 역할 |
|---|---|---|
| `gold_transit_dong_15min` | 동 × 15분 | 기존 dong_hourly의 15분판, 영구 아카이브의 축. hourly는 여기서 roll-up(기존 테이블 하위 호환 유지 or 뷰 전환) |
| `gold_transit_route_section_30min` | 노선 × 구간(sect_ord) × **30분** | 버스 혼잡의 구간 단위 아카이브 (G3 원천). 티어링(#440)에 맞춰 15분→30분 grain, tier 구분 컬럼 포함 |
| `gold_transit_parking_lot_15min` | parking_id × 15분 | 개소 단위 점유율·변화율 아카이브 (G2 원천) |

---

## 2. 선정 gold 10종

| ID | 테이블(안) | grain | 결합 도메인 | 주요 선행 |
|---|---|---|---|---|
| G1 | `gold_transit_dong_now` | 동 × 최신 15분 | — | 기반 dong_15min |
| G2 | `gold_transit_parking_full_risk` | parking_id × 15분 | — | parking_lot_15min 누적 |
| G3 | `gold_transit_bus_route_comfort` | 노선×구간×요일×시간대 | — | route_section_30min 누적 (tier1 한정) |
| G4 | `gold_transit_dong_rhythm` | 동 × 요일 × 시간 | — | dong_15min 누적 |
| G5 | ~~`gold_transit_bus_headway_speed`~~ | — | — | **보류** (티어링 #440 — 3분 복귀 또는 도착정보 수집 시 재개) |
| G6 | `gold_transit_x_weather_dong_hourly` | 동 × 시간 | weather | dong_15min |
| G7 | `gold_transit_event_access` | event_ref | culture | dim_station, G2/G4 프로파일 |
| G8 | `gold_transit_supply_x_demand_hourly` | 핫스팟 × 시간 | citydata(인구) | citydata 중복 정리 합의 |
| G9 | `gold_transit_lastmile_dong_hourly` | 동 × 시간 | citydata(따릉이) | dong_15min |
| G10 | `gold_transit_forecast_card` | 핫스팟(동) × 미래 시각 | citydata(인구예보) + weather(예보) | G4 리듬 누적 |

### G1. `gold_transit_dong_now` — "지금 우리 동네 교통" 실시간 스코어카드 (후보 1)
- 기반 15분 gold의 최신 버킷을 사용자 등급으로 변환 — 버스 혼잡 상/중/하, 주차 여유 %, 지하철 평균 대기 분
- 화면: "성수동: 버스 혼잡 '높음'(40분 전 관측), 주차 여유 12%, 2호선 평균 대기 3분"
- 지하철·주차는 신선도 15분 이내, 버스는 전 티어 사용 + **소스별 관측 시각 표기 필수**
  (tier1 최대 30분, tier2 최대 수 시간 — 제약 5 원칙 ③). 변환 주기 단축(운영 작업) 전제

### G2. `gold_transit_parking_full_risk` — 주차장별 "지금 가면 자리 있나 + 만차 임박" (후보 2)
- 현재 점유율 + 5분 관측 기반 점유 변화율로 '만차까지 예상 N분' + 요일×시간 만차 확률(아카이브 누적)
- 화면: "현재 88%, 채워지는 속도로 30분 내 만차 예상 — 평일 14시 만차 확률 85%"
- 프로파일 부분은 누적 몇 주 필요

### G3. `gold_transit_bus_route_comfort` — 노선×구간별 "몇 시에 타면 앉아 가나" (후보 3)
- `gold_transit_route_section_30min` 누적분에서 congestion(3/4/5)·is_full 요일×시간대 프로파일
- 화면: "272번 성수→건대 구간, 8시대 혼잡 4.2/5"
- **tier1(간선·광역 165노선) 한정** — 제약 5 원칙 ②. tier2는 시간대 프로파일 불가(하루 3회 관측)

### G4. `gold_transit_dong_rhythm` — 동별 요일×시간 교통 히트맵 (후보 4)
- `gold_transit_dong_15min` 누적분을 요일 축으로 접은 평시 프로파일
- 화면: "우리 동네는 금요일 18시가 일주일 중 최악"
- G1의 '평시 대비'·G10의 기준선으로 재사용. 초기 몇 주 '표본 부족' 배지 필요

### G5. `gold_transit_bus_headway_speed` — 노선별 배차간격·운행속도 (후보 5) ⚠ 성립 불가 — 재검토
- (원안) 3분 GPS trace의 차량별 구간 통과 시각에서 배차간격·구간 속도 추정
- **티어링(#440)으로 30분 스냅샷이 되면서 배차(주요 노선 5~10분 간격)·속도 추정 불가**(제약 5).
  대체 원천 후보였던 `bronze_bus_arrival`(도착정보)도 0행. **보류 확정(2026-07-20 사용자 결정)** —
  3분 복귀(트래픽 증량 승인, #369 잔여) 또는 도착정보 수집 개시 시 재개

### G6. `gold_transit_x_weather_dong_hourly` — 날씨 조건부 교통 상태 (후보 6, × weather)
- 아카이브 gold + 같은 동·시각 기온(TMP)·강수확률(POP)·강수량(PCP).
  과거분으로 "비 올 때 주차 +N%p" 패턴, 예보분으로 "내일 15시 비 → 혼잡 상향"
- 화면: "오늘 15시 비 예보 — 이 동네 주차 혼잡 평소보다 심할 예정"
- weather gold는 동×시각 grain으로 조인키 완비. '비 오는 날' 표본 누적 위해 조기 착수 이득

### G7. `gold_transit_event_access` — 행사장 가는 길 안내판 (후보 8, × culture)
- 행사 좌표 기준 최근접 지하철역(dim_station 전 노선)·주차장 top3 + 행사 시간대 해당 동 주차·버스 프로파일
- 화면: "이 공연장: 7호선 어린이대공원역 도보 5분, 공연시간대 주차 만차 확률 90% → 대중교통 권장"
- 접근성 부분(dim 기반)은 보존 정책 무관 — 즉시 전 행사 제공 가능. 문화 일정 ~2027 확보

### G8. `gold_transit_supply_x_demand_hourly` — 수요 대비 공급 '교통 압박 지수' (후보 9, × citydata)
- 실시간 인구(min/max)·지하철 5분 승하차 수요 대비 버스 관측·주차 여유 공급 비율
- 화면: "성수카페거리: 인구 '붐빔' + 주차 여유 5% → 지금 차 가져가면 안 됨"
- ⚠ citydata `ppltn_x_transit_hourly`(핫스팟 기준)와 조합 유사 — 착수 전 중복 정리 합의(제약 4)

### G9. `gold_transit_lastmile_dong_hourly` — 지하철 주변 따릉이 (후보 10, × citydata)
- 지하철역 보유 동의 따릉이 잔여 대수(sbike)·주차 여유를 나란히. 실시간 결합 위주라 보존 영향 적음
- 화면: "건대입구역 인근 따릉이 34대 여유 — 내려서 따릉이 타세요"
- 지하철 실시간(6역) 겹치는 동은 대기시간까지

### G10. `gold_transit_forecast_card` — "내일 이 시간 교통" 예측 카드 (후보 11, × citydata × weather)
- `gold_citydata_ppltn_forecast`(주중/주말×시간 기대 인구) + weather +3일 예보 + G4 평시 리듬 결합
  → 미래 시간대의 예상 교통 상태
- 화면: "내일(토) 15시 강남역 일대: 인구 '붐빔' 예상 + 비 예보 → 주차 비추천, 지하철 이용"
- 유일한 순수 '미래' 제품. G4 누적이 선행이라 후반 배치

---

## 3. 빌드 순서 (의존 관계)

```
Phase 1  기반 아카이브 3종 + full-refresh 가드  ── dong_15min · route_section_30min · parking_lot_15min
         (+ 운영: 변환 주기 단축, 실패 알림·주말 실행 보장)
Phase 2  G1 dong_now, G6 ×weather, G9 lastmile   ── 기반 gold 직접 파생, 누적 불필요 → 즉시 가치
Phase 3  G4 rhythm                               ── 아카이브 누적 시작(얇은 표본으로 개시 가능)
         (G5 headway_speed 는 보류 — 3분 복귀 또는 도착정보 수집 시 이 페이즈로 복귀)
Phase 4  G2 parking_full_risk, G3 route_comfort  ── 누적 프로파일 성숙 후
Phase 5  G7 event_access, G8 supply_x_demand, G10 forecast_card
         ── G7: G2/G4 프로파일 활용, G8: citydata 중복 정리 선행, G10: G4 누적 선행
```

- 누적이 필요한 지표(G2~G4, G10)는 **모델 자체는 조기 배포**하고 표본 수(`base_n` 류 컬럼)를
  노출해 소비 측이 신뢰도를 판단하게 한다.

## 4. 제외 후보 기록

rev.3의 18종 중 미선정: 7(×traffic 돌발 영향), 12(경기일 작전판), 13(따릉이 적합도 확장),
14(명소 나들이), 15(상권 주차), 16(생활시설 접근성), 17(기상×돌발 리스크), 18(핫플 접근).
필요 시 후속 라운드에서 재검토 — 상세 설계 메모는 이 문서 git 이력(rev.3) 참조.

# 사용자향 gold 1차 — dong_now · ×weather · lastmile (#289)

기반 아카이브(#286)에서 직접 파생되는 즉시 가치 3종(G1·G6·G9).
선정 경위·설계 원칙은 [2026-07-15-gold-candidates-user-facing.md](2026-07-15-gold-candidates-user-facing.md),
아카이브 계약은 [gold_transit_archive_15min.md](gold_transit_archive_15min.md).

## gold_transit_dong_now — "지금 우리 동네 교통" (G1)

- **한 행** = 행정동 1개의 최신 교통 상태 / **grain**: `admin_dong_code` / **재질**: 매 변환 재생성 table
- 소스별로 "최근 24h 내 마지막 관측 버킷"을 **따로** 뽑아 결합 — 주차는 5분 전, 버스는
  40분 전(tier2 동은 수 시간 전)이 최신일 수 있어서다.
- 사용자 등급: `bus_congestion_grade`(여유/보통/혼잡), `parking_avail_pct`(여유 %),
  `subway_wait_min`(대기 분).
- **`*_last_event_at` 를 반드시 함께 노출**할 것 — "N분 전 관측" 없이 값만 보여주면
  tier2 동에서 사용자를 속이게 된다. 경과분은 조회 시점 기준으로 소비 측이 계산.

## gold_transit_x_weather_dong_hourly — 날씨 조건부 교통 (G6, × weather)

- **한 행** = 행정동×1시간의 교통 실측 + 그 시각 예보 / **grain**: (`admin_dong_code`, `hour_at`)
- **과거 행**: 교통(버스 tier1 한정 — 시간대 비교 취지) + 당시 최신 발표 예보 → "비 올 때 주차 +N%p" 패턴
- **미래 행**: 예보만(교통 컬럼 null) → "내일 15시 비 예보" 전망 카드. 매 런 최신 발표로 갱신됨
- 날씨 피벗: TMP·POP·PCP·SKY·PTY, `max_by(…, issued_at)`(citydata 선례). PCP '강수없음'=null.
- 과거 예보-교통 쌍이 여기 동결되므로 weather 원천 보존 정책과 무관 — `full_refresh=false`.

## gold_transit_lastmile_dong_hourly — 지하철 주변 따릉이 (G9, × citydata)

- **한 행** = 지하철역 보유 동×1시간 / **grain**: (`admin_dong_code`, `hour_at`), 역 동(~400) 한정
- 따릉이 잔여(`sbike_bike_last_sum`)·주차 여유·지하철 대기(실시간 6역 동만)를 나란히
- **커버리지 주의**: 따릉이는 citydata 핫스팟 121곳 주변 대여소만 — `sbike_*` null 은
  "정보 없음"이지 "대여소 없음"이 아니다. citydata 수집 중단 구간(실측 2026-07-17~)은 행이 비는 게 정상
- citydata 보존 별도 → 여기 merge 된 행이 따릉이 이력의 자체 아카이브(`full_refresh=false`)

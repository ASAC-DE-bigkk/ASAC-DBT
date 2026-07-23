# citydata QA — 질문 · 답변 · 소스 테이블

> 질문 수요=네이버 실검, 커버리지=팀 골드 실측(2026-07-21, dev). 🟢채택 / 🔵팀원커버 / 🔴갭

| # | 질문 | 답변 | 소스 테이블 |
|---|---|---|---|
| CQ001 | 이번 주말 서울에서 몇 시가 제일 한산해요? 조용히 걷고 싶어요. | 주말여부×시간 기대 혼잡 예보 | gold_citydata_ppltn_forecast |
| CQ002 | 경복궁 쪽은 무슨 요일 몇 시가 덜 붐벼요? | 요일×시간 평균 혼잡 패턴 | gold_citydata_ppltn_by_time |
| CQ003 | 손주들 데리고 주말에 나가는데 어느 시간대가 덜 붐벼요? | 주말여부×시간 기대 혼잡 예보 | gold_citydata_ppltn_forecast |
| CQ004 | 우리 정릉동 상권이 요즘 뜨고 있어요, 지고 있어요? | 붐빔 변화율·hot_index | gold_citydata_hot_commerce |
| CQ005 | 명절 연휴에 서울 시내가 평소보다 붐빌까요? | 주말여부×시간 기대 혼잡 예보 | gold_citydata_ppltn_forecast |
| CQ006 | 동대문구는 무슨 요일·시간이 한가한 편이에요? | 요일×시간 평균 혼잡 패턴 | gold_citydata_ppltn_by_time |
| CQ007 | 서울에서 요즘 뜨는 상권 순위 알려줘요. 장사 자리 보게. | ✔ 건대입구역 ▲5.3%·수유역 ▲12.1% (hot_index 순) | gold_citydata_hot_commerce |
| CQ008 | 서울 관광지 평일엔 보통 몇 시가 제일 한산해요? | 시간대별 평균 인구 | gold_citydata_ppltn_hourly |
| CQ009 | 특정 장소 요일·시간대별 평균 혼잡 패턴 데이터 있어요? | 요일×시간 평균 혼잡 패턴 | gold_citydata_ppltn_by_time |
| CQ010 | 비 오는 날엔 상도동 근처가 평소보다 덜 붐비나요? | ✔ 비 와도 안 줄어듦 — 오히려 살짝↑ (11,770 vs 11,552) | gold_citydata_ppltn_x_weather_hourly |
| CQ011 | 지금 서울에서 평소보다 갑자기 붐비는 데 있어요? | 평소 대비 z-score 이상 여부 | gold_citydata_ppltn_anomaly |
| CQ012 | 성수동 소비가 최근 며칠새 얼마나 늘었어요? | ✔ 서울숲·성수카페거리 "유지"(정체) 상태 | gold_citydata_cmrcl_daily |
| CQ013 | 고궁은 무슨 요일이 제일 한산해요? | 요일×시간 평균 혼잡 패턴 | gold_citydata_ppltn_by_time |
| CQ014 | 주말에 서울에서 제일 한산한 시간대가 언제예요? | 주말여부×시간 기대 혼잡 예보 | gold_citydata_ppltn_forecast |
| CQ015 | 서울대공원 요일·시간별 붐빔 예측 있어요? 동선 짜게. | 주말여부×시간 기대 혼잡 예보 | gold_citydata_ppltn_forecast |
| CQ016 | 그 유적지는 무슨 요일 몇 시가 덜 붐벼요? | 요일×시간 평균 혼잡 패턴 | gold_citydata_ppltn_by_time |
| CQ017 | 한강공원은 보통 몇 시가 제일 한적해요? 강아지 데리고 가게. | ✔ 새벽 0~4시가 가장 한적 | gold_citydata_ppltn_hourly |
| CQ018 | 서울 명소들 무슨 요일이 사람이 제일 적어요? | 요일×시간 평균 혼잡 패턴 | gold_citydata_ppltn_by_time |
| CQ019 | 경복궁은 무슨 요일에 관광객이 제일 많이 몰려요? | ✔ 수·목요일 최다 (광화문·덕수궁 평균최대 5.4만) | gold_citydata_ppltn_daily |
| CQ020 | 강남에 20대는 주로 무슨 요일 몇 시에 많이 모여요? | ✔ 토요일 21시 피크 (강남역 20대 35%) | gold_citydata_ppltn_demographics |
| CQ021 | 이번 주말 서울 날씨 어때요? 비 와요? | 팀원 골드가 답함(중복 생산 금지) | gold_weather_place_daily_outlook (weather) |
| CQ022 | 서울 도심 주차장은 무슨 요일·시간에 만차예요? | 팀원 골드가 답함(중복 생산 금지) | gold_transit_parking_profile (transit) |
| CQ023 | 어느 동네가 무슨 시간대에 교통이 제일 막혀요? | 팀원 골드가 답함(중복 생산 금지) | gold_transit_dong_rhythm (transit) |
| CQ024 | 서울에서 소바·일식집 많은 동네가 어디예요? | 팀원 골드가 답함(중복 생산 금지) | gold_license_dong_category_matrix (commerce) |
| CQ025 | 성수동에서 요즘 사람들이 제일 많이 찾는 맛집 어디예요? | ✘ 팀 전체 미보유: 맛집 인기/추천 데이터 팀 전체 미보유 — 상권 밀집도까지만. 신규 소스 | — |
| CQ026 | 서울에서 국밥 맛집으로 유명한 데 어디예요? | ✘ 팀 전체 미보유: 개별 점포 인기/평판 미수집 — 신규 소스 필요 | — |
| CQ027 | 지금 그 유명 맛집 대기줄 긴가요? | ✘ 팀 전체 미보유: 실시간 웨이팅 팀 전체 미수집 — 서울 API에도 없음(신규 소스) | — |
| CQ028 | 압구정에서 요즘 인기 많은 한정식집 어디예요? | ✘ 팀 전체 미보유: 개별 식당 인기/예약 미수집 — 밀집도까지만 | — |
| CQ029 | 성수동에서 요즘 사람 몰리는 맛집 웨이팅 짧은 데 있어요? | ✘ 팀 전체 미보유: 개별 맛집·웨이팅 미수집(신규 소스) | — |
| CQ030 | 오늘 서울 미세먼지 어때요? 사진 찍으러 나가게. | ✘ 팀 전체 미보유: 대기질(미세먼지) 팀 전체 미수집 — weather는 KMA 기온·강수· | — |

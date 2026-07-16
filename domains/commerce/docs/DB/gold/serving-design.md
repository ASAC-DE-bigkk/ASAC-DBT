# gold 서빙 설계 — 지표 의도·용도 (commerce)

> 서울 열린데이터 인허가(LOCALDATA) 상권 ELT. medallion raw→bronze(Iceberg)→silver(entity/history/detail)→**gold(집계 전용)**→Serve=**D1(SQLite, 예정)**.
> 본 문서는 구현 지시가 아니라 **설계 의도** 문서다. "gold 지표로 화면에서 무엇을 보여줄 것으로 기대했고, 어떤 용도로 보길 원했는가"를 서빙 관점에서 정리한다. 22개 gold 테이블을 6개 화면 테마에 매핑하고 D1/Iceberg 서빙 tier를 확정한다.

---

## 0. 요약 — gold→D1 서빙 아키텍처 한 눈에

**서빙 정책 핵심(PROJECT.md §4):** gold 는 bronze/silver 와 동일 Iceberg 카탈로그. Serve = Cloudflare D1(SQLite) 선별 export. Postgres 폐기 확정. D1 특성(DB당 용량 상한 실용 ≪1GB · 단일 writer · 시퀀스 없음 · 엣지 읽기 최적화 · 동적타이핑) → **소형 조회형 파생만 전량 교체 스냅샷 export**, 수백만 행 원장은 **D1 금지·Iceberg(Trino) 직조회**.

### 서빙 tier 분류표

| tier | 정의 | 테이블(행수) | 근거 |
|---|---|---|---|
| **iceberg_api** | Trino(Iceberg) 직조회. D1 원장 금지 | flow_daily(2,918,695) | 일×지역3축 카디널리티 폭발 + 임의기간·다축 필터 → 사전집계·평탄화 불가. event_date 문자열 range 로 파티션 프루닝 |
| **d1_rollup** | 원 grain 은 D1 금지, **화면 축으로 사전 롤업한 소형 파생만** D1 export. 세부 드릴다운은 Iceberg 폴백 | flow_monthly(1,338,656→롤업 181,430) · flow_yearly(446,330→21,558) · churn_yearly(59,536) · geo_grid(16,353) · stock_age_band(12,822) · uptae_mix(29,683) | 원장은 대용량이나 화면은 굵은 grain(gu/major/category, age_band, top-N uptaenm)만 사용 → 롤업 후 ≪1GB. 비율 지표는 합산 후 재산출 |
| **d1_direct** | 이미 조합 grain 으로 평탄화된 소형 → **D1 직접 전량 교체 스냅샷** | dong_summary(417) · cohort_survival(7,502) · lifespan(2,867) · status_duration(596) · status_transition(108) · seasonality(2,912) · gu_specialization(283) · dong_category_matrix(3,488) · area_profile(859) · multi_site(140) · change_activity(152) · address_succession(99) · phone_succession(91) · data_quality(152) · env_facility_operation(51) | <8K행·수 KB~수백 KB. 조인 불필요, 엣지에서 풀스캔 무해. 자연키(dataset·gu_code·uptaenm 등) 기반 스냅샷 재생성으로 멱등 |

**집계:** iceberg_api 1개 · d1_rollup 6개 · d1_direct 15개 = **22개(누락 0)**.

**전역 원칙:** ① 모든 D1 export = 전량 교체 스냅샷(증분 upsert 금지). ② 결정키(dataset/opnsfteamcode/mgtno, gu_code, uptaenm) 로 재생성 멱등. ③ export 시 타입 정규화(좌표 double · 코드 varchar · decimal 보유율 double). ④ latest_collected_at 을 화면 '데이터 기준일'로 노출.

---

## 1. 상권 흐름 대시보드 (market-flow)

**화면 목적** — 개·폐업 이벤트를 시간축(일/월/연)·계절축(월중 1~12)·동태축(순증/교체율/신생비)으로 탐색. "언제·어디서·무슨 업종이 뜨고 지나"를 기간·업종3단·지역3축 필터로 읽는다.
**주 사용자** — 상권분석가·자치구 정책담당, 창업지원기관·소상공인센터, 입지·프랜차이즈 컨설턴트, 데이터 PM.

**답하는 핵심 질문**
- 최근 월별 개·폐업 모멘텀은? 어느 업종·자치구가 순증/순감인가?
- 장기(연) 추세는 성장/쇠퇴? 업종·자치구별로 어떻게 갈리나?
- 개·폐업이 특정 달(계절)에 몰리나?
- 시장이 순증형인가 교체(churn)형인가 — 신생비·교체율은?
- 특정 기간 개·폐업 스파이크(정책·팬데믹)가 일 단위 어디서?
- 같은 업종을 일/월/연 다른 해상도로 봐도 추세가 일관적인가?

**지표 테이블 표**

| 테이블 | 무슨 지표 | 어떤 용도로 보려 했나 | grain | tier |
|---|---|---|---|---|
| flow_daily | cnt(일별 개·폐업), 기간합계, opened vs closed | 임의기간 스파이크 탐지·세밀 드릴다운(연→월→일의 최말단) | event_date × event_type × dataset × gu/dong/legal | iceberg_api |
| flow_monthly | cnt(월별), net=opened−closed, 이동평균(FE) | **화면 기본 해상도** 절대 시계열·최근 모멘텀·자치구 비교 | ym × event_type × dataset × gu/dong/legal | d1_rollup |
| flow_yearly | cnt(연별), net, 연평균성장(FE) | 수십 년 장기 구조적 상승/하락 국면 | y × event_type × dataset × gu/dong/legal | d1_rollup |
| seasonality | cnt(월중), 월별 점유율(FE) | 연 무관 계절 패턴 — 창업/폐업 타이밍 규칙성 | event_type × month(01~12) × major/category/dataset | d1_direct |
| churn_yearly | opened·closed·net_change·stock_start·churn_rate·birth_rate | 순증형 vs 교체형 진단(신생상권/포화상권) | y × major/category/dataset × gu_code | d1_rollup |

**연계·주의**
- **완결기간 계약**: daily/monthly/yearly 는 당일·당월·당해 제외 완결분만 append(재실행 0건 멱등). 화면은 최신 미완결 구간 미표시 또는 **회색 '미완결'** 처리.
- **해상도 정합**: 동일 필터에서 yearly cnt = Σmonthly = Σdaily. 드릴다운은 연→월→일로 같은 축을 좁혀 호출.
- **롤업 계약**: monthly 는 (ym, event_type, major, category, gu_code)로 롤업(181,430행), yearly 는 (y,…,gu_code)로 롤업(21,558행) → D1 스냅샷. dong/legal/dataset 세부는 `/monthly/detail`(Iceberg) 폴백.
- **윈도우 상이**: seasonality=최근 10년 완결연도, churn=최근 20년(2006~2025). 나란히 비교 시 기준연도 차이 주석.
- **근사 배지**: churn 의 stock_start(교체율·신생비 분모)는 연 단위 문자열 연산 기반 '근사 영업스톡'. 롤업 시 opened/closed/stock_start 합산 후 rate 재산출. stock_start=0 → rate NULL.
- **재빌드 윈도우**: gold 는 정기 --full-refresh 로 재빌드되며 그 짧은 구간엔 일시 조회 불가 → 위젯 '데이터 준비중' 스켈레톤(완료 후 자동 정상화).
- **UNK 버킷**: 결측 gu/dong/legal 은 'UNK' 집계 → 지도·지역필터에서 별도 처리. 날짜 문자열 ISO(사전순=날짜순)라 range 는 문자열 비교로 안전. 커버리지 1900~2025 원천 그대로 → 기본범위 최근 20~30년, 극단연도(1900)는 이상치로 접어둠.

---

## 2. 업종 생존·수명·상태 분석 (survival)

**화면 목적** — "이 업종으로 창업하면 얼마나 버티나, 폐업·휴업 리스크는?"를 정량화하는 창업 리스크 평가 화면. 코호트 생존곡선(우측검열 보정)·폐업 수명 분포·상태 지속기간·전이방향을 결합.
**주 사용자** — 예비 창업자·소상공인, 자치구 인허가·정책 담당, 상권 분석가·기획자, 프랜차이즈·부동산 입지팀.

**답하는 핵심 질문**
- 이 업종에 창업하면 k년 후 생존확률은? (코호트 생존곡선)
- 폐업 업소는 보통 몇 년(p50/p90) 버텼나? 1년 내 조기폐업 비율은?
- 10년 이상 버티다 폐업한 규모는? 자치구별 수명·조기폐업률 차이는?
- 휴업은 얼마나 지속되고, 재개(02→01)하나 폐업(02→03)하나?
- 각 상태(영업/휴업/폐업/취소)는 평균 얼마 지속되고 진행 중 세그먼트는?
- 개업 활발했던 코호트일수록 생존율이 낮은가(경쟁 밀집)?

**지표 테이블 표**

| 테이블 | 무슨 지표 | 어떤 용도로 보려 했나 | grain | tier |
|---|---|---|---|---|
| cohort_survival | survival_rate·survivors·cohort_n·years_elapsed | **편향 없는 정본** 생존곡선 — 업종 간 k년 생존율 직접 비교 | major×category×cohort_y×years_elapsed(0~30) | d1_direct |
| lifespan | p50/p90/avg_days·early_close_ratio·closed_within_1y·survived_10y_then_closed·n_closed | 폐업 완결분 수명 분포·조기폐업률의 지역 비교(입지 판단) | major×category×dataset×gu_code | d1_direct |
| status_duration | p50/p90/avg_days·n_segments·max_days·is_ongoing | 상태(영업/휴업/폐업/취소)가 얼마나 유지되나·진행중 규모 | dataset×status_code×is_ongoing | d1_direct |
| status_transition | transitions·from_group→to_group | 상태 변화 방향·빈도(02→01 재개 vs 02→03 폐업) 리스크 경로 | major×category×dataset×from×to | d1_direct |

**연계·주의**
- **grain·모수 상이(등치 금지)**: cohort_survival=시간축 생존곡선(연 단위 근사·검열 보정), lifespan=폐업 완결분만의 수명 분포, status_duration=상태별 지속기간. 숫자를 직접 등치시키지 말 것.
- **생존 편향**: lifespan 은 '폐업 완결분'만 모수(현재 영업 중 장수 업소 미포함) → avg/p50 가 실제 기대수명보다 짧게 편향. **'폐업분 기준' 라벨 필수**. cohort_survival 이 편향 없는 정본.
- **씨앗 지표**: status_transition·status_duration 은 이력(history) 축적 중. 휴업(02)은 원천 3,718행(폐업 03=1.56M 대비 0.24%) → 02 관련 셀은 표본 부족. **'이력 축적 중·표본 부족' 배지 + 최소 n 임계(transitions/n_segments<30 회색)**.
- **근사 주의**: cohort_survival 연 단위 근사(폐업연−개업연>k), status_duration p50/p90 은 approx_percentile → 툴팁 명시.
- **코드체계**: status 코드는 dataset별 라벨 이질을 2자리(01영업·02휴업·03폐업·04취소/말소·05제외/전출·06기타)로 정규화 — dtl 세부 상태와 다름.
- **서빙**: 4개 모두 소형(108~7,502행) → 전량 D1 직접 export, 조인 없이 엣지 즉답. 과거 코호트도 매일 생존자 변동 → 스냅샷 전량 교체.

---

## 3. 지역 프로파일·지도 (geo-place)

**화면 목적** — 행정동·자치구·좌표격자 단위로 "이 동네엔 뭐가 많고, 뭐가 새로 생기고, 어디가 밀집 핫스팟이고, 이 구는 어떤 업종에 특화됐나"를 탐색하는 입지 프로파일링 도구. **'구성' 지표는 영업(01) 스톡 기준, 총계 지표만 폐업 포함**이라는 이중 축을 명확히 구분.
**주 사용자** — 창업·입지 검토자, 지자체 상권/인허가 담당, 상권 분석가.

**답하는 핵심 질문**
- 이 행정동엔 어떤 업종(중분류)이 많은가? 영업/폐업 구성은?
- 최근 1년 새로 생긴 업종은(동네 활력 신호)?
- 지도 밀도 핫스팟·신규 개업 격자는 어디인가?
- 이 구는 서울 평균 대비 어떤 업종에 특화(LQ>1)? 특정 업종은 어느 구에?
- 이 동네/구는 신생 상권(1년 미만↑)인가 노포 상권(20년+↑)인가?
- 지오코딩 커버리지 낮은 지역은 어디라 밀도 과소평가 위험이 있나?

**지표 테이블 표**

| 테이블 | 무슨 지표 | 어떤 용도로 보려 했나 | grain | tier |
|---|---|---|---|---|
| dong_summary | business_count(폐업포함 누적)·open/closed_count·dataset_count·geocoded_count | 동네 첫인상 요약·동 간 비교·코로플레스 기준 레이어·지도 커버리지 배지 | admin_dong_code 1행 | d1_direct |
| dong_category_matrix | active_cnt(01)·total_cnt·opened_last_365d | 동네 업종 구성·최근 1년 신규 개업 업종(활력) | admin_dong × major × category | d1_direct |
| geo_grid | active_cnt·opened_last_365d_active | 행정동보다 세밀한 실공간 밀도 히트맵·핫스팟 | grid_lat×grid_lng(0.005°) × major × category | d1_rollup |
| gu_specialization | active_cnt·share_in_gu·lq | 구 특화 벤치마크(LQ>1=서울평균보다 밀집) | gu_code × major × category | d1_direct |
| stock_age_band | active_cnt(밴드별)·신생/노포 비중(FE) | 생존자 스톡의 연령 구성 — 신생 vs 노포 상권 성숙도 진단 | major×category×dataset×gu×age_band(6밴드) | d1_rollup |

**연계·주의**
- **지표 정합성(혼용 금지)**: dong_summary.business_count=폐업 포함 누적 원장, matrix/geo_grid/gu_specialization/stock_age_band 의 active_cnt=영업(01) 스톡. 동 총계 카드는 business_count, 업종 구성 도넛/매트릭스는 active_cnt.
- **롤업 계약**: geo_grid — 개요 레이어=grid×major 롤업(줌아웃), 드릴 레이어=grid×major×category(단일 category subset). 지도 팬/줌 저지연 위해 iceberg 대신 D1 스냅샷. stock_age_band — dataset 축 드롭한 major×category×gu×age_band 롤업만 D1, dataset 정밀조회는 Iceberg 폴백.
- **커버리지 한계 3종(화면 필수 표기)**: ① 지오코딩 — geo_grid·geocoded_count 는 latitude not null(약 84%) → 미지오코딩 누락. dong_summary 에 geocoded_count/business_count '지도 커버리지' 배지 + '좌표 보유 업소만' 각주. ② 개업일 — opened_last_365d·age_band 는 apvpermymd 유효 ISO만 → '개업일 보유분 기준' 각주. ③ UNK 버킷 — matrix 는 결측 dong/gu 를 'UNK' 보존 → 지도/리스트에서 필터로 감추되 합계 각주 표기(API `include_unk=false`).
- **시점**: matrix/geo_grid/stock_age_band 의 최근 1년·업력은 KST 스냅샷 매일 재계산, latest_collected_at 을 '데이터 기준일'로 노출.

---

## 4. 업소 특성·규모·업태 프로파일 (biz-profile)

**화면 목적** — 특정 dataset·자치구를 골랐을 때 "그 업종 가게가 실제로 어떻게 생겼나"를 규모(면적)·업태 구성(uptaenm)·체인화(다지점)·정보변경 활발도로 프로파일링. dataset 선택 하나로 4개 패널 동시 갱신.
**주 사용자** — 창업·입점 전략, 인허가·상권 정책 분석가, 프랜차이즈/체인 분석가, 화면 개발자.

**답하는 핵심 질문**
- 이 업종 가게는 보통 몇 ㎡? 소형(<33㎡)·대형(≥330㎡) 비중은(자치구 차이)?
- 업종 안 실제 업태 구성은? 최근 1년 신규를 주도하는 업태는?
- 얼마나 체인화됐나 — 동일전화 다지점 비율·최대 지점 수?
- 정보(상호·주소)를 얼마나 자주 바꾸나 — 개명·이전 잦은 업종은?
- 규모·업태·체인화·변경활발도를 종합한 업종 프로파일 유형은?

**지표 테이블 표**

| 테이블 | 무슨 지표 | 어떤 용도로 보려 했나 | grain | tier |
|---|---|---|---|---|
| area_profile | n_with_area·avg/p50/p90_m2·lt_33m2·ge_330m2 | 표준 점포 크기·소형/대형 구성·자치구 크기 차이 | major×category×dataset×gu_code | d1_direct |
| uptae_mix | active_cnt·total_cnt·opened_last_365d | 최말단 업태(uptaenm) 믹스·최근 성장 주도 업태 | major×category×dataset×uptaenm×gu_code | d1_rollup |
| multi_site | sites_with_phone·multi_site_locations·multi_site_ratio·multi_site_operators·max_sites_per_operator | 체인화 침투율(동일전화 다지점) 추정 | major×category×dataset | d1_direct |
| change_activity | businesses·avg/max_versions·rename_ratio·relocation_ratio | 리브랜딩·이전 패턴(정보변경 활발도) | major×category×dataset | d1_direct |

**연계·주의**
- **공통 축**: 4개 모두 major/category/dataset 공통 → dataset 선택 하나로 규모·업태·체인화·변경활발도 4패널 동시 갱신.
- **커버리지·근사·씨앗 표기 필수**: ① area 면적 유효율 ~78%·detail 보유 40개 dataset 한정 → 미보유 업종은 '면적 데이터 없음', n_with_area 를 표본 신뢰 배지. ② uptae uptaenm 7,644종·현재 버전 영업 기준, **lodging 은 스키마 드리프트로 제외** → 각주 필수. ③ multi_site 전화 보유율 44%·번호공유≠법인동일·20+지점 컷 → '추정' 경고 상시. ④ change_activity 이력 축적 초기 씨앗(실측 avg_versions 최대 1.1, ratio 대부분 <0.005) → **절대치보다 업종 간 상대순위**로 해석, '누적 중' 경고.
- **롤업 계약**: uptae_mix 원장 grain(29,683=dataset×uptaenm×gu)은 D1 금지 → (a) gu 제거 dataset×uptaenm top-N 소형 파생만 D1, (b) 자치구 드릴다운(전 grain)은 iceberg_api. 7,644종 방대 → top-N 페이징+검색.
- **서빙**: area(859)·multi_site(140)·change_activity(152) 소형 → D1 직접 스냅샷. 자연키(dataset+gu_code / dataset+uptaenm) 재생성 멱등.

---

## 5. 자리 승계·연쇄창업 (succession)

**화면 목적** — "폐업하면 그 자리/그 사업자는 다음에 무엇을 하나"를 관계(전이) 렌즈로. 두 축 구조 분리 — ① 자리 승계=같은 도로명주소 폐업 후 0~365일 최근접 후속 개업 1건, ② 연쇄창업=같은 전화번호로 폐업 후 ≤3년·주소 상이 재개업. 둘 다 (closed→opened) 전이 매트릭스. **두 지표 모두 '근사'임을 화면 전면 명시가 설계 핵심**.
**주 사용자** — 상권 정책·인허가 분석가(공실 회전·업종 대체), 창업/프랜차이즈 입지 전략가, 데이터 기획자.

**답하는 핵심 질문**
- 폐업한 음식점 자리엔 다시 음식점? 다른 업종?(업종 고착성)
- 승계 활발한 업종 조합은 — 대각선(같은 업종) vs 비대각선(전환)?
- 자리가 비면 얼마나 빨리 채워지나(avg/p50 gap, 90일 내 승계율)?
- 같은 사업자(전화)는 폐업 후 업종을 유지하나 갈아타나?
- 연쇄창업은 얼마나 빨리(1년 내) 일어나나?
- 자리 승계(주소)와 사업자 승계(전화) 패턴은 다른가?

**지표 테이블 표**

| 테이블 | 무슨 지표 | 어떤 용도로 보려 했나 | grain | tier |
|---|---|---|---|---|
| address_succession | successions·avg/p50_gap_days·within_90d·대각선비율(FE) | 자리(주소) 업종 고착성·승계 속도(공실 회전) | (closed_major/category→opened_major/category) | d1_direct |
| phone_succession | successions·avg/p50_gap_days·within_1y·업종유지율(FE) | 사업자(전화) 업종 전환·재도전 속도(생애주기) | 동일 전이 grain | d1_direct |

**연계·주의**
- **합산·병합 금지**: 동일 전이 grain 이나 매칭 축·시맨틱 상이. address=같은 주소·최근접 1건·window 365일·within_90d·gap≥0(동일일 허용). phone=같은 전화·주소 상이 배제·window 3년(1095일)·within_1y·gap>0. phone 은 address 와 겹치지 않도록 동일 주소 구조적 배제(상보).
- **근사 경고(상단 배지·툴팁 필수)**: ① 주소=건물 단위·호수 미구분 → M×N 팬아웃을 '최근접 1건'으로 제어한 근사. ② 전화=원천 커버리지 약 44%·번호 승계/재배정 노이즈 → 공용번호(20+지점) 컷 후에도 근사.
- **분모 없음**: 매칭 성사 건만 집계 → '총 폐업 수' 분모 없이 절대 승계건수를 절대율로 오독 금지. **상대 비교·매트릭스 형태로만** 제시.
- **위젯 제약**: gap 분포는 원장이 아닌 사전집계(avg/p50/within_*) 스칼라만 → 히스토그램 대신 요약통계·매트릭스·chord/sankey.
- **서빙**: 둘 다 <100행(99·91) → d1_direct 확정. 원장(silver_license_entity 매칭 중간산물 수백만)은 D1 금지지만 gold 는 조합 grain 평탄화 완료. 타입 정규화(gap double·코드 varchar).

---

## 6. 데이터 품질·환경 특수축 (governance)

**화면 목적** — 내부 거버넌스. 각 API(dataset)의 필드별 결측(전화/좌표/행정동/폐업일/주소/상호)을 진단해 서빙·분석 신뢰도를 판단하고 수집 개선 우선순위를 정한다. 동시에 LOCALDATA 에 '영업시간·영업요일' 부재 한계를 고지하고, 유일 실측 가능한 환경 배출시설(대기/수질)의 가동일수·가동시간을 특수 축으로 제공.
**주 사용자** — 데이터 엔지니어/거버넌스, 분석가(지표 신뢰도), 수집 파이프라인 운영자, 환경 도메인 분석가.

**답하는 핵심 질문**
- 어느 API가 좌표/전화/행정동 매핑 결측이 가장 심한가?
- 폐업일(dcbymd) 보유율은? lifespan/succession 을 신뢰할 수 있나?
- geo_grid·succession 등을 뒷받침하는 원천 커버리지가 충분한가?
- 대분류/중분류별 신뢰도 프로파일은?
- 환경 배출시설의 자치구별 연간 가동일수·가동시간 분포는?
- 일반 업종 영업시간을 왜 못 주는가(원천 부재)를 어떻게 고지하나?

**지표 테이블 표**

| 테이블 | 무슨 지표 | 어떤 용도로 보려 했나 | grain | tier |
|---|---|---|---|---|
| data_quality | total/active_rows·phone/geo/admin_dong/address/name_coverage·close_date_coverage_of_closed | API별 서빙·분석 신뢰도 판단·수집 개선 우선순위 | major × category × dataset (152행) | d1_direct |
| env_facility_operation | facility_rows·with_operating_days/hours·avg/p50_operating_days/hours | 영업시간 요구의 실측 대응 — 환경 배출시설 가동 시간축 | dataset × gu_code (51행, 상태01) | d1_direct |

**연계·주의**
- **신뢰도 씨앗지표 연동**: data_quality 의 close_date_coverage_of_closed·geo_coverage·phone_coverage 는 타 화면 파생지표의 신뢰 근거(lifespan/cohort_survival←폐업일, geo_grid←좌표, address/phone_succession←전화 44%). **해당 화면에 커버리지 경고 배지 연동**. 폐업행 0인 dataset 은 close_date NULL='해당없음'.
- **환경 커버리지 한계**: env_facility_operation 은 영업시간 요구의 실측 대응이나 한계 큼 — **수질 배출시설은 가동일수/가동시간 보유율 거의 0(with_operating_days≈0, avg=0.0), 대기만 유효** → '원천 부재/결측' 경고 고정 노출, with_*/facility_rows 커버리지 비율 병기.
- **일반 업종 영업시간 불가**: LOCALDATA 원천에 필드 자체 부재(payload 전수검색 0건) → **화면 상단 명시적 고지**.
- **근사 라벨**: p50/approx_percentile 값은 근사 → '근사' 라벨.
- **서빙**: 둘 다 초소형(152·51행) → D1 직접, 매일 전량 재계산. export 시 decimal 보유율→double, gu_code→varchar 정규화.

---

## 7. 22 테이블 전수 매핑표 (테이블 → 화면 → tier)

| # | gold 테이블 | 행수 | 화면 테마 | serving tier |
|---|---|---|---|---|
| 1 | gold_license_flow_daily | 2,918,695 | market-flow | iceberg_api |
| 2 | gold_license_flow_monthly | 1,338,656 (→181,430) | market-flow | d1_rollup |
| 3 | gold_license_flow_yearly | 446,330 (→21,558) | market-flow | d1_rollup |
| 4 | gold_license_seasonality | 2,912 | market-flow | d1_direct |
| 5 | gold_license_churn_yearly | 59,536 | market-flow | d1_rollup |
| 6 | gold_license_cohort_survival | 7,502 | survival | d1_direct |
| 7 | gold_license_lifespan | 2,867 | survival | d1_direct |
| 8 | gold_license_status_duration | 596 | survival | d1_direct |
| 9 | gold_license_status_transition | 108 | survival | d1_direct |
| 10 | gold_license_dong_summary | 417 | geo-place | d1_direct |
| 11 | gold_license_dong_category_matrix | 3,488 | geo-place | d1_direct |
| 12 | gold_license_geo_grid | 16,353 | geo-place | d1_rollup |
| 13 | gold_license_gu_specialization | 283 | geo-place | d1_direct |
| 14 | gold_license_stock_age_band | 12,822 | geo-place | d1_rollup |
| 15 | gold_detail_area_profile | 859 | biz-profile | d1_direct |
| 16 | gold_detail_uptae_mix | 29,683 | biz-profile | d1_rollup |
| 17 | gold_license_multi_site | 140 | biz-profile | d1_direct |
| 18 | gold_license_change_activity | 152 | biz-profile | d1_direct |
| 19 | gold_license_address_succession | 99 | succession | d1_direct |
| 20 | gold_license_phone_succession | 91 | succession | d1_direct |
| 21 | gold_license_data_quality | 152 | governance | d1_direct |
| 22 | gold_env_facility_operation | 51 | governance | d1_direct |

**tier 합계**: iceberg_api 1 · d1_rollup 6 · d1_direct 15 = **22 (누락 0)**.

---

## 8. 서빙 한계·후속

**① 씨앗 지표 성숙 대기 (이력 축적 초기)**
- status_transition·status_duration — 휴업(02) 원천 3,718행(폐업 대비 0.24%)으로 02 관련 셀 표본 부족. transitions/n_segments<30 회색 처리, '이력 축적 중' 배지. 시계열 누적으로 신뢰 상승.
- change_activity — 실측 avg_versions 최대 1.1, rename/relocation ratio 대부분 <0.005. 절대치 비교 무의미 → **업종 간 상대순위**로만 해석 안내.

**② 근사 지표 해석 주의**
- churn stock_start(교체율·신생비 분모) = 연 단위 문자열 연산 근사 영업스톡 → '근사' 배지, stock_start=0 rate NULL.
- address/phone_succession = 매칭 성사 건만(분모 없음), 주소 건물단위·전화 44% 커버리지 → 절대율 오독 금지, 상대·매트릭스만.
- cohort_survival(연 근사·검열 보정) · lifespan(폐업분 생존편향) · p50/p90(approx_percentile) → 각 라벨·툴팁 명시.

**③ 재빌드 윈도우·부분 제외 gold**
- 재빌드(--full-refresh) 진행 중 짧은 구간엔 해당 gold 가 일시 조회 불가('Metadata not found') → 위젯 '데이터 준비중' 스켈레톤(완료 후 자동 정상화). API 는 build_status 로 503 building.
- uptae_mix lodging — 스키마 드리프트로 union 제외 → 화면 각주.

**④ 커버리지 한계 상시 노출**
- 지오코딩 ~84% (geo_grid/geocoded_count) · 면적 ~78% (area) · 전화 44% (multi_site/phone_succession) · 개업일 결측(opened_last_365d/age_band) · 수질 배출시설 가동필드 ≈0 · 일반 업종 영업시간 원천 부재(payload 0건).
- data_quality 를 타 화면 신뢰도 배지의 단일 소스로 연동.

**⑤ D1 export 미구현 (Serve=D1 '예정')**
- 현재 gold 는 Iceberg 카탈로그에만 존재. D1 스냅샷 export 파이프라인(전량 교체·자연키 재생성·타입 정규화) 미구축.
- d1_rollup 6종의 **사전 롤업 파생 모델**(flow monthly/yearly 화면축, churn dataset 접기+rate 재산출, geo_grid grid×major, stock_age_band dataset 드롭, uptae top-N) 미빌드 → 빌드 후 D1 대상 확정.
- iceberg_api(flow_daily) 및 각 d1_rollup 의 detail 폴백 엔드포인트는 Trino 직조회 백엔드 필요.

**⑥ 뷰/파생 축 미승계 및 정합 계약**
- flow 3모델 완결기간 계약(당일/당월/당해 제외, append 멱등, 지연도착은 --full-refresh 스윕) → 화면 미완결 구간 회색 처리 UI 계약 필요.
- 해상도 정합(yearly=Σmonthly=Σdaily) 및 major enum 실측 4개(culture/environment/health/industry, health=8 dataset) 검증 필요.
- UNK 버킷(결측 지역코드) 표준 처리 규약을 지도·리스트·합계 각주에 일관 적용.
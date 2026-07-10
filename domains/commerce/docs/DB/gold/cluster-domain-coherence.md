# gold detail 클러스터 — 도메인 정합성 검증 (공식 문서 대조)

> **목적**: 비공통 필드 병합(Jaccard union-find)이 "컬럼만 닮은 **무관 도메인**"을 한 detail 테이블로
> 섞지 않았는지, **공식 API 식별자(LOCALDATA 업종코드)와 소관 법령**을 기준으로 사후 검증한다.
> 병합 **알고리즘·경계**는 [../../silver-noncommon-catalogs.md](../../silver-noncommon-catalogs.md),
> 객체 명세는 [tables.md](tables.md), 기계용 카탈로그는 [../../gold-catalog.csv](../../gold-catalog.csv).

## 1. 왜 이 검증이 필요한가

`build_catalog` 의 클러스터링은 **비공통 필드셋의 Jaccard 유사도**만 본다(`catalog_rules.py`). 원리상
필드가 **우연히** 겹친 서로 무관한 업종이 하나의 detail 로 병합될 위험이 있다(예: 의료+체육이 좌표·주소
필드만 닮아 묶이는 경우). 따라서 산출된 **8개 cluster 를 공식 문서 기준으로 도메인 정합성 사후 검증**한다.

- 병합 대상은 **비공통(꼬리) 필드**뿐이다. 공통 컬럼은 전 152종이 `commerce_business_entity` 하나를
  공유하므로 이 검증과 무관하다.
- **single 70종은 1:1**(병합 없음)이라 도메인 혼입이 원천적으로 불가 → §6.

## 2. 검증 기준 (재사용 표준)

클러스터가 **도메인 정합적**이라고 판정하려면 멤버 전원이 다음 중 하나를 만족해야 한다.

- **(a) 단일 소관 법령** — 멤버의 LOCALDATA 업종 prefix 가 동일한 법령군에 속함(가장 엄격).
- **(b) 단일 산업 테마** — 서로 다른 법령이지만 하나의 **인정된 산업 테마**(콘텐츠 제작·배급 / 관광 /
  현장 이용 오락 venue)로 수렴하고, 그 테마가 **연관 도메인**임.

그리고 **cluster 이름**(`NAME_BY_MEMBER`)이 그 법령/테마를 지시해야 한다.

**경보(오병합) 조건**: 멤버가 서로 **무관한** 법령/산업(예: 의료+체육, 식품+환경)에 걸치면
필드-유사도 **오병합**으로 보고 재검토·분할한다.

**근거 데이터**: `commerce_dim_dataset`(`category`·`sub_category`·`service_name`·`oa_id`) +
`commerce_catalog.members`. **공식 출처**: 서울 열린데이터광장 `https://data.seoul.go.kr/dataList/<oa_id>/S/1/datasetView.do`,
원천 LOCALDATA `https://www.localdata.go.kr`(업종코드 = `service_name` = `LOCALDATA_<코드>`).

## 3. 판정 요약

| detail 테이블 (cluster) | 종수 | 공식 근거(소관 법령 / 업종군) | 기준 | 판정 |
|---|---:|---|:--:|:--:|
| `commerce_food_sanitation_business_detail` | 21 | **식품위생법** (`LOCALDATA_072***`) | (a) | ✅ |
| `commerce_sports_facility_detail` | 11 | **체육시설의 설치·이용에 관한 법률** (`103***·104***`) | (a) | ✅ |
| `commerce_public_sanitation_service_detail` | 4 | **공중위생관리법** (`051***·062001·114401`) | (a) | ✅ |
| `commerce_amusement_park_detail` | 3 | **관광진흥법** 유원시설업 (`030708-712`) | (a) | ✅ |
| `commerce_medical_institution_detail` | 3 | **의료법** 의료기관 (`010***`) | (a) | ✅ |
| `commerce_media_content_business_detail` | 16 | **문화콘텐츠 제작·배급**(영화비디오법·음악산업법·게임산업법·공연법·출판문화산업법·대중문화예술산업법) | (b) | ✅ |
| `commerce_game_entertainment_venue_detail` | 9 | **현장 이용 오락 venue**(게임산업법 제공업·영화비디오법 감상/제공·음악산업법 노래연습장) | (b) | ✅ |
| `commerce_tourism_business_detail` | 15 | **관광진흥법** 관광사업·관광편의시설 | (b) | ✅ |

**결과: 8/8 통과 · 오병합 0건.** 5개는 단일 법령(기준 a), 3개는 단일 산업 테마(기준 b). "전혀 무관한"
도메인이 섞인 사례는 없다. 오히려 필드-유사도 병합이 레지스트리의 거친 `category` 라벨보다 도메인을
**더 정확히** 잡은 경우가 있다(§5).

## 4. 클러스터별 상세 (멤버 × 공식 코드 × 소관 법령)

### 4.1 `commerce_food_sanitation_business_detail` — 식품위생법 (21종)

전원 `LOCALDATA_072***` = 식품위생법 영업(제조가공·판매·접객·급식·물류).

| dataset | 공식 명칭 | LOCALDATA | 비고 |
|---|---|---|---|
| general_restaurant | 일반음식점 | 072404 | |
| rest_restaurant | 휴게음식점 | 072405 | |
| bakery | 제과점영업 | 072218 | |
| instant_sale_mfg | 즉석판매제조가공업 | 072219 | |
| food_mfg | 식품제조가공업 | 072211 | |
| food_additive_mfg | 식품첨가물제조업 | 072212 | |
| container_pkg_mfg | 용기·포장지제조업 | 072215 | |
| food_subdivision | 식품소분업 | 072208 | |
| food_sale_etc | 식품판매업(기타) | 072213 | |
| edible_ice_sale | 식용얼음판매업 | 072221 | |
| food_vending | 식품자동판매기업 | 072210 | |
| hfood_dist_sale | 건강기능식품유통전문판매업 | 072202 | |
| hfood_general_sale | 건강기능식품일반판매업 | 072203 | |
| group_meal_food_sale | 집단급식소식품판매업 | 072201 | |
| contract_meal_service | 위탁급식영업 | 072101 | |
| group_meal_facility | 집단급식소 | 072102 | |
| food_cold_storage | 식품냉동냉장업 | 072207 | 물류 |
| food_transport | 식품운반업 | 072209 | 물류 |
| entertainment_bar | 유흥주점영업 | 072302 | 접객 |
| singing_bar | 단란주점영업 | 072301 | 접객 |
| distribution_sale | 유통전문판매업 | 072217 | §5① 레지스트리 `category=industry` 이나 코드상 식품 |

### 4.2 `commerce_sports_facility_detail` — 체육시설법 (11종)

전원 `103***·104***` = 체육시설의 설치·이용에 관한 법률.

| dataset | 공식 명칭 | LOCALDATA |
|---|---|---|
| golf_course | 골프장 | 103102 |
| golf_range | 골프연습장업 | 103101 |
| billiard_hall | 당구장업 | 103201 |
| swimming_pool | 수영장업 | 103501 |
| ice_rink | 빙상장업 | 103401 |
| sled_park | 썰매장업 | 103901 |
| yacht_marina | 요트장업 | 104001 |
| martial_arts_gym | 체육도장업 | 104101 |
| fitness_center | 체력단련장업 | 104201 |
| dance_hall | 무도장업 | 103301 |
| dance_academy | 무도학원업 | 103302 |

### 4.3 `commerce_public_sanitation_service_detail` — 공중위생관리법 (4종)

| dataset | 공식 명칭 | LOCALDATA |
|---|---|---|
| beauty_shop | 미용업 | 051801 |
| barber_shop | 이용업 | 051901 |
| bathhouse | 목욕장업 | 114401 |
| laundry | 세탁업 | 062001 |

### 4.4 `commerce_amusement_park_detail` — 관광진흥법 유원시설업 (3종)

| dataset | 공식 명칭 | LOCALDATA |
|---|---|---|
| full_amusement_park | 종합유원시설업 | 030712 |
| general_amusement_park | 일반유원시설업 | 030709 |
| amusement_etc | 유원시설업(기타) | 030708 |

### 4.5 `commerce_medical_institution_detail` — 의료법 의료기관 (3종)

| dataset | 공식 명칭 | LOCALDATA |
|---|---|---|
| clinic | 의원 | 010102 |
| affiliated_medical | 부속의료기관 | 010103 |
| medical_corporation | 의료법인 | 010108 |

### 4.6 `commerce_media_content_business_detail` — 문화콘텐츠 제작·배급 (16종, 기준 b)

서로 다른 법령이나 전원 **콘텐츠 제작·배급·유통**(B2B 공급망)이라는 단일 산업 테마.

| dataset | 공식 명칭 | LOCALDATA | 소관 |
|---|---|---|---|
| cinema | 영화상영관 | 031302 | 영화비디오법 |
| film_screening | 영화상영업 | 031303 | 영화비디오법 |
| film_distribution | 영화배급업 | 031301 | 영화비디오법 |
| film_import | 영화수입업 | 031304 | 영화비디오법 |
| film_production | 영화제작업 | 031305 | 영화비디오법 |
| video_distribution | 비디오물배급업 | 031002 | 영화비디오법 |
| video_production | 비디오물제작업 | 031005 | 영화비디오법 |
| game_distribution | 게임물배급업 | 030501 | 게임산업법 |
| game_production | 게임물제작업 | 030502 | 게임산업법 |
| music_video_distribution | 음반·음악영상물배급업 | 031402 | 음악산업법 |
| music_video_production | 음반·음악영상물제작업 | 031403 | 음악산업법 |
| online_music_service | 온라인음악서비스제공업 | 031401 | 음악산업법 |
| performance_hall | 공연장 | 030601 | 공연법 |
| pop_culture_agency | 대중문화예술기획업 | 030802 | 대중문화예술산업발전법 |
| printing_shop | 인쇄사 | 041601 | 인쇄문화산업진흥법 |
| publisher | 출판사 | 041701 | 출판문화산업진흥법 |

### 4.7 `commerce_game_entertainment_venue_detail` — 현장 이용 오락 venue (9종, 기준 b)

**§4.6 과의 경계**: 제작·배급(media_content)이 아니라 **고객이 현장에서 이용**하는 제공/감상 업소.
필드셋이 이 B2C 운영 특성을 반영해 갈렸다(같은 `031***` 비디오군도 제작/배급 vs 감상/제공으로 분리 — §5②).

| dataset | 공식 명칭 | LOCALDATA | 소관 |
|---|---|---|---|
| general_game_arcade | 일반게임제공업 | 030506 | 게임산업법 |
| youth_game_arcade | 청소년게임제공업 | 030507 | 게임산업법 |
| internet_game_cafe | 인터넷컴퓨터게임시설제공업 | 030505 | 게임산업법 |
| combined_game_arcade | 복합유통게임제공업 | 030504 | 게임산업법 |
| combined_video_service | 복합영상물제공업 | 030503 | 영화비디오법 |
| video_viewing_room | 비디오물감상실업 | 031001 | 영화비디오법 |
| video_small_theater | 비디오물소극장업 | 031003 | 영화비디오법 |
| video_viewing_service | 비디오물시청제공업 | 031004 | 영화비디오법 |
| karaoke_room | 노래연습장업 | 030901 | 음악산업법 |

### 4.8 `commerce_tourism_business_detail` — 관광진흥법 관광사업·관광편의시설 (15종, 기준 b)

| dataset | 공식 명칭 | LOCALDATA | 비고 |
|---|---|---|---|
| domestic_travel_agency | 국내여행업 | 031201 | |
| overseas_travel_agency | 국외여행업 | 031202 | |
| general_travel_agency | 일반여행업 | 031203 | |
| convention_facility | 국제회의시설업 | 030704 | |
| convention_planning | 국제회의기획업 | 030801 | |
| city_tour_bus | 시내순환관광업 | 030706 | |
| tour_cruise | 관광유람선업 | 030703 | |
| resort_complex | 종합휴양업 | 030713 | |
| auto_campground | 자동차야영장업 | 031105 | |
| general_campground | 일반야영장업 | 031107 | |
| tourist_performance_hall | 관광공연장업 | 030602 | |
| tourist_cabaret | 관광극장유흥업 | 030603 | |
| tour_restaurant | 관광식당 | 072401 | §5② 관광편의시설(식품 코드) |
| tour_entertainment_bar | 관광유흥음식점업 | 072402 | §5② 관광편의시설(식품 코드) |
| foreigner_entertainment_bar | 외국인전용유흥음식점업 | 072403 | §5② 관광편의시설(식품 코드) |

## 5. 특기 사항 — 병합이 레지스트리 라벨보다 정확했던 지점

**① `distribution_sale`(유통전문판매업)** — 레지스트리 `category=industry` 로 라벨돼 있으나, 공식 코드
`LOCALDATA_072217` 은 **식품위생법 072군**(식품 유통전문판매업)이다. 필드-유사도 병합이 이를 food
클러스터로 정확히 귀속시켜 **거친 라벨의 오분류를 사실상 교정**했다.

**② 관광 지정 음식점 3종**(`tour_restaurant` 072401 · `tour_entertainment_bar` 072402 ·
`foreigner_entertainment_bar` 072403) — 코드상 `072`(식품) 이지만 실체는 **관광진흥법 관광편의시설
지정업소**. 병합은 이들을 food 가 아니라 **tourism** 으로 묶었는데, 이는 필드셋(관광 지정 관련 항목)이
관광군과 더 가깝기 때문이며 도메인상 타당하다(식품/관광 **경계 업종**).

**③ 같은 업종 prefix 의 목적별 정확한 분리** — `031***`(비디오물)이 코드상 한 군인데도
**제작·배급**(031002·031005)은 media_content, **감상·제공**(031001·031003·031004)은
game_entertainment_venue 로 갈렸다. 병합이 코드만 따르지 않고 **실질 영업(공급 vs 현장 이용)** 을
필드셋으로 구분했음을 보여준다.

## 6. single 70종 (병합 없음)

single 은 각 API 가 **자기 테이블 1개**(`commerce_<short>_detail`)로 1:1 대응하므로 도메인 혼입이
원천적으로 없다(pharmacy·hospital·optical_shop·lodging·v2 환경 13종 등). 즉 도메인 정합성 검증 대상은
**병합이 일어난 cluster 8개**에 한정된다.

## 7. 결론 & 재검증 방법

- **결론**: 8개 cluster 모두 단일 소관 법령(5) 또는 단일 산업 테마(3) 안에서만 병합 — **컬럼만 닮은
  무관 도메인 오병합 0건**. 위치 매핑/시간축 등 공통 필드는 supertype(`commerce_business_entity`)이
  전담하므로 detail 병합과 무관하다.
- **개별 식별성 보존**: 병합돼도 각 API 는 `dataset` 컬럼 필터 또는 `commerce_v_api_<short>`
  뷰(152×2)로 개별 조회 가능 — [views.md](views.md).
- **드리프트 재검증(신규 API 추가 시)**: `build_catalog` 가 카탈로그 버전을 올리면(신규 API/필드) **이 문서의
  §3~§4 를 갱신**하고 §2 기준으로 신규 멤버의 소관 법령 정합성을 재판정한다. 현행 매핑 재현 쿼리:

```sql
-- cluster 멤버 × 도메인 메타(정합성 재검증용)
select d.detail_table, d.category, d.sub_category, d.dataset, d.name_ko, d.service_name
from serving.public.commerce_dim_dataset d
where d.detail_table in (select object from serving.public.commerce_catalog where kind='detail_cluster')
order by d.detail_table, d.category, d.dataset;
```

관련 문서: [tables.md](tables.md) · [views.md](views.md) · [../README.md](../README.md) ·
병합 알고리즘 [../../silver-noncommon-catalogs.md](../../silver-noncommon-catalogs.md).

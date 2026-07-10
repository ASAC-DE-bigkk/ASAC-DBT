# KCISA 서울 행사 silver/gold 편입 — 전량 + 3축 dedup (#85)

- 이슈: [ASAC-DBT#85](https://github.com/ASAC-DE-bigkk/ASAC-DBT/issues/85) / 브랜치: `feat/85-culture-kcisa-silver-gold`
- bronze: `bronze_kcisa_seoul_event` (ASAC-DAG#196 · PR ASAC-DAG#225, area2 sido=서울 스냅샷)

## 배경 · 목적

서울시 문화행사 API는 자발등록 체계라 **국립기관(국립현대미술관·국립중앙박물관 등) 최신 전시가 구멍**이다.
KCISA "한눈에보는문화정보" bronze(2026-07-10 실측: distinct seq **523건**, 국립기관 전시 24건)를
silver/gold로 편입해 이 구멍을 메운다. **이슈 문면은 "전시"였으나 전량 편입으로 확장**(사용자 결정) —
분포가 공연 379 / 전시 104 / 교육·체험 22 / 행사·축제 ~10 로 공연이 다수라, dedup을 제대로 걸면
전시 구멍 보강 + 교육·체험 등 타 축에 없는 커버리지까지 얻는다.

## 그레인 · 스코프

- **silver 그레인**: `seq` (KCISA 자연키) — 스냅샷 dedup 후 1행. 전 serviceName 편입.
- **dedup 후 예상**: 523 − ~135(3축 교차) ≈ **~390행 신규**.
- 기존 축 모델(performance·event·exhibition·sejong·festival)은 **수정하지 않음** —
  기존 축이 정본, KCISA는 보강. 중복 시 KCISA 행을 버린다.

## 아키텍처

```
bronze_kcisa_seoul_event
  │ ① seq 스냅샷 dedup — partition by seq order by culture_dedup_order()
  │ ② 3축 anti-join dedup — silver_culture_performance / _event / _exhibition
  │ ③ 좌표 내장(gpsX=경도, gpsY=위도) → culture_dong_map + gu_codes(sigungu)
  ▼
silver_culture_kcisa_event
  ▼
gold_culture_location_daily — union 1건 추가 (serviceName→activity_type 매핑)
```

| 파일 | 작업 |
|---|---|
| `models/sources.yml` | `bronze_kcisa_seoul_event` 등록 (record_json·load_date·ingest_ts, daily freshness 기본) |
| `models/silver/silver_culture_kcisa_event.sql` | **신규** — 파싱→스냅샷 dedup→3축 anti-join→행정동 |
| `models/gold/gold_culture_location_daily.sql` | union에 kcisa 1건 추가 |
| `models/schema.yml` | silver 계약 (unique·not_null·axis_coverage·bbox) |
| `tests/assert_kcisa_no_cross_duplicate.sql` | **신규** singular — 3축 잔존 중복 0 |

## 컬럼 매핑 (silver)

| KCISA 필드 | silver 컬럼 | 처리 |
|---|---|---|
| `seq` | `event_id` | 그레인 키. not_null·unique |
| `title` | `title` | trim·nullif |
| `place` | `venue_name` | dedup 키에서 제외(소스 간 표기 상이), 컬럼 보존 |
| `serviceName` | `service_name` | gold activity_type 매핑 원천 |
| `realmName` | `category` | 보존 |
| `sigungu` | `gu` | gu_codes crosswalk로 gu_code |
| `startDate`/`endDate` | `event_start_date`/`event_end_date` | `try(date_parse(…,'%Y%m%d'))` → date |
| `gpsX`/`gpsY` | `longitude`/`latitude` | `asac_axes.seoul_lonlat('gpsx_raw','gpsy_raw')` (X=경도·Y=위도) |
| — | `event_at` | `cast(event_start_date as timestamp(6))` |
| — | lineage 6종 | `culture_lineage('kcisa')` |

## dedup 규칙 (핵심 설계)

**정규화 제목 + 기간 겹침** (승인안 b):

- 정규화: `lower(regexp_replace(title, '\s|\[.*?\]|\(.*?\)', ''))` — 공백·대괄호·소괄호 제거 + 소문자.
- 매칭: 정규화 제목 일치 **AND** (기간 교차 **OR** 한쪽 기간 null).
  기간 교차 = `k.start <= x.end AND k.end >= x.start`.
- 대상 3축: `silver_culture_performance`(performance_name) ·
  `silver_culture_event`(event_title) · `silver_culture_exhibition`(title).
- 매칭된 KCISA 행은 **제거**(anti-join). 실측 catch: perf 97 · event ~30 · sema 10.
- 기간 조건이 살리는 것: 같은 제목·다른 시기 **재공연** 5건(perf 102→97) — 다른 이벤트가 맞음.
- 장소를 키에서 뺀 이유: "아트포레스트 1관" vs KOPIS 시설명처럼 소스 간 표기가 달라
  미탐 → gold 이중집계가 더 큰 해악.

## gold 편입

`raw_activities` union에 추가:

```sql
select gu_code, gu, 'kcisa:' || event_id,
       case service_name
           when '전시' then 'exhibition'
           when '공연' then 'performance'
           when '행사/축제' then 'festival'
           else 'event'   -- 교육/체험 등
       end,
       event_start_date, event_end_date
from silver_culture_kcisa_event
```

- **id 프리픽스 `kcisa:`** — KCISA `seq`와 sema `exhibition_id`가 둘 다 숫자형이라
  같은 activity_type('exhibition') 안에서 `count(distinct activity_id)` 충돌 가능 → 프리픽스로 격리.
- dedup이 silver에서 끝났으므로 기존 type 컬럼(exhibitions_count 등)에 합산해도 이중집계 없음.
  "exhibitions_count = 모든 전시" 의미 유지(사용자 결정), 출처는 silver lineage로 추적.

## 계약 · 테스트

- `event_id`: not_null + unique (그레인) / `title`·`load_date`·`ingested_at`: not_null
- `longitude`/`latitude`: `asac_axes.in_seoul_bbox`
- `gu_code`: `asac_axes.axis_coverage` — 빌드 후 실측 −5%p로 확정 (기존 패턴, severity warn)
- `assert_kcisa_no_cross_duplicate` (singular): dedup 규칙과 동일 조건으로 3축 재검사 → 잔존 0행
- 기존 grain 테스트 선례(`assert_*_grain_unique`)는 schema unique로 갈음 (seq 단일 컬럼이라 singular 불요)

## 완료 조건 (AC, 이슈 대응)

- dbt parse/compile/test 통과 (컨테이너 dev 타깃, `--no-partial-parse`)
- dedup 후 3축(performance 포함) 교차 중복 0 실측
- **국립기관 전시 신규 반영 실측** — 국립현대미술관·국립중앙박물관 등이 silver에 존재
- gold: kcisa 편입 전/후 activities_count 델타 확인 (자기 스키마(culture) 밖 미기록)

## 리스크 · 한계

- **제목 정규화의 한계**: 부제 표기 차이("뮤지컬 캣츠" vs "캣츠")는 미탐 — 잔존 이중집계 가능.
  실측 임계(assert 0행은 "규칙 기준 0")로 관리, 퍼지 확장은 필요 시 후속.
- **스냅샷 소스**: KCISA는 현재 활성분만 제공 — 종료 행사는 다음 스냅샷에서 사라지나
  silver는 스냅샷 dedup(최신 관측 유지)이라 한번 들어온 seq는 유지됨.
- 서비스명 '공연'+realmName '전시' 7건은 serviceName 기준으로 performance 매핑(단순 규칙 우선).

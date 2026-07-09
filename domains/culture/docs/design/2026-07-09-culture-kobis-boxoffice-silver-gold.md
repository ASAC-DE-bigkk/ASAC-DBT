# culture KOBIS 영화 박스오피스 silver/gold 설계 (#86)

**이슈**: [ASAC-DBT#86](https://github.com/ASAC-DE-bigkk/ASAC-DBT/issues/86)
**작성일**: 2026-07-09 · **브랜치**: `feat/86-culture-kobis-silver-gold` (dev 기준)
**범위**: silver `silver_culture_movie_boxoffice`(일×순위) + gold `gold_culture_movie_boxoffice_daily`(서울 쏠림) + 계약/테스트.
**선행(완료)**: bronze는 ASAC-DAG#197(PR#228)로 적재 — `bronze_kobis_boxoffice_nation` / `_seoul`.

## 목표

KOBIS 일별 박스오피스(전국 top10 + 서울 한정 top10)를 메달리온 silver/gold로 편입해
**"서울 쏠림"** 신호 — 서울/전국 관객 비중 — 을 만든다. 서울 한정 랭킹은 상영지역 필터
(`wideAreaCd=0105001`)로 수집된 실제 서울 소비이지, 전국 집계의 프록시가 아니다.

## ⚠️ 네이밍 — 기존 KOPIS boxoffice와 충돌 회피

dev에는 이미 `silver_culture_boxoffice` / `gold_culture_boxoffice_daily`가 있으나 이는
**KOPIS 예매상황판**(공연 예매 top50 랭킹, `bronze_kopis_boxoffice`)이다 — 영화 관객수와
다른 축. 혼동을 막기 위해 KOBIS 영화 모델은 **`movie_boxoffice`** 이름을 쓴다
(`silver_culture_movie_boxoffice`, `gold_culture_movie_boxoffice_daily`).
기존 KOPIS 모델·gold·테스트는 **손대지 않는다**(머지된 자산 미변경).

## 소스 사실 (bronze 계약, dev 라이브 확인 2026-07-09)

- bronze 컬럼: `dataset, source, endpoint, record_seq, record_json, raw_object_key,
  page_no, load_date, ingest_ts, run_id, collected_at` — `culture_lineage()`가 요구하는
  계보 컬럼(`run_id, raw_object_key, collected_at, ingest_ts, load_date`) 전부 존재.
- 각 행 = 그날 top10 중 영화 1건. `record_json` 18필드(`rank, movieCd, movieNm, openDt,
  salesAmt, salesShare, salesAcc, audiCnt, audiAcc, scrnCnt, showCnt` 등). `openDt`는 `YYYY-MM-DD`.
- **`targetDt`(실제 관객일)는 record_json에 없다** — 로더 계약(ASAC-DAG#197):
  `targetDt = date(load_date) − 1일`. → silver는 `boxoffice_date = cast(load_date as date)
  - interval '1' day`로 복원(dev 확인: load_date 2026-07-09 → 2026-07-08).
- 서울 top10 ≠ 전국 top10(서로 다른 영화 집합). 두 랭킹은 독립 처리.

## silver — `silver_culture_movie_boxoffice`

**그레인**: `region × boxoffice_date × rank`. 공간축 시도(서울시)까지라 dong/gu 축 면제.

- **union**: `bronze_kobis_boxoffice_nation`(`region='nation'`) ∪ `_seoul`(`region='seoul'`),
  각 분기에 `{{ culture_lineage('kobis') }}` — `silver_culture_reservation` union 패턴.
- **cast**: `rank`→int, `movie_cd`(movieCd)·`movie_nm`(movieNm) 문자열(trim, ''→NULL),
  `open_date`(openDt)→date(`try(cast(... as date))`), `audience_count`(audiCnt)·
  `audience_acc`(audiAcc)·`sales_amount`(salesAmt)→bigint, `sales_share`(salesShare)→double,
  `screen_count`(scrnCnt)·`show_count`(showCnt)→int.
- **boxoffice_date**: `cast(load_date as date) - interval '1' day`.
- **dedup**: `row_number() over (partition by region, boxoffice_date, rank order by
  {{ culture_dedup_order() }})` = rn 1 — 파티션 키를 테스트 그레인과 일치.
- **event_at**: `cast(boxoffice_date as timestamp(6))` (#48 `_at`=event time 관례).
- **계보 컬럼**: `source_system, dag_run_id, raw_object_key, collected_at, ingested_at, load_date` 그대로 방출.

## gold — `gold_culture_movie_boxoffice_daily`

**그레인**: `boxoffice_date` (날짜 1행). silver에서 region별 집계.

| 컬럼 | 정의 |
|---|---|
| `boxoffice_date` | 그레인 |
| `nation_top_audience` | `sum(audience_count)` where region='nation' |
| `seoul_top_audience` | `sum(audience_count)` where region='seoul' |
| `seoul_audience_share` | `round(1.0*seoul_top_audience / nullif(nation_top_audience,0), 3)` — **서울 쏠림 신호** |
| `nation_top_movie` | region='nation' ∧ rank=1 영화명 (해석 보조) |
| `seoul_top_movie` | region='seoul' ∧ rank=1 영화명 (해석 보조) |

**지표 근거(집계 비율)**: 서울·전국 top10은 서로 다른 영화 집합이라 "관객 비중"은 top10
관객 합의 비율로 정의 — 매일 계산 가능(빈 날/NULL 없음)해 시계열 축으로 안정적이고, top10만
있는 소스의 정직한 "서울 소비 온도". 같은 영화(movieCd 매칭)의 서울⊂전국 정합성은 지표가
아니라 **불변식 테스트**로 검증(아래).

**공간 경계**: 시도(서울시)까지라 자치구 조인 불가 → `gold_culture_location_daily` 미편입,
일 단위 "서울 영화소비" 축 전용.

## 계약·테스트

**schema.yml** (신규 2 모델 엔트리 추가):
- `silver_culture_movie_boxoffice`: `region` accepted_values `['nation','seoul']`,
  `movie_cd` not_null, `rank` not_null.
- `gold_culture_movie_boxoffice_daily`: `boxoffice_date` not_null·unique,
  `seoul_audience_share` not_null.

**singular tests** (`domains/culture/tests/`):
- `assert_movie_boxoffice_grain_unique.sql`: silver `region × boxoffice_date × rank` 중복 0.
- `assert_movie_boxoffice_seoul_subset.sql`: 같은 `boxoffice_date`·`movie_cd`가 양 region에
  있을 때 서울 `audience_count` ≤ 전국 `audience_count` (위반 시 >0행) — **AC "서울⊂전국" 실측**.

## 재료·범위

- 전 모델 `+materialized: table` (프로젝트 기본, 일 ~20행). `sources.yml`에 KOBIS bronze 2건 신규 등록.
- culture 스키마 밖 미수정. 기존 KOPIS boxoffice 모델 미변경.

## 완료 조건 (이슈 AC 대응)

- [ ] dbt parse/compile 통과
- [ ] dbt test 통과 (grain unique + subset 불변식)
- [ ] 자기 도메인(culture) 스키마 밖 미기재
- [ ] 서울/전국 비중 파생 실측 — dev에서 `gold_culture_movie_boxoffice_daily` 조회,
      `seoul_audience_share ∈ (0,1)` 및 subset 테스트 통과 확인

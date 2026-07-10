# dbt/domains/culture — 서울 문화활동 silver/gold

**타 도메인에서 조인하러 온 분을 위한 문서입니다.** 서울의 문화활동(공연·행사·축제·전시·공공예약·영화 박스오피스·야구 일정)을 "언제(시간축) × 어디(공간축)" 그레인으로 제공합니다. 위치: dev = `iceberg_dev.culture` / prod = `iceberg.culture` (silver·gold·bronze 전부 같은 스키마).

> 컬럼 계약·테스트: [models/schema.yml](models/schema.yml) · bronze 원천 정의: [models/sources.yml](models/sources.yml) · 설계 배경: [docs/design/](docs/design/) · 수집 파이프라인 내부(ASAC-DAG): `dags/domains/culture/`

## 조인 계약 — 이것만 알면 됩니다 (#48 공통축)

### 시간축: `event_at` (KST, timestamp(6))

- 모든 `_at` 컬럼은 **KST**, 접미사는 `_at`(timestamp)/`_date`(date)만 사용.
- 시간축은 별도 dim 테이블이 아니라 **where 필터**로 씁니다: `where event_at >= timestamp '2026-07-01 00:00:00'`.
- ⚠️ **기간 fact 주의**(공연·행사·전시 등): `event_at` 단독 필터 = **시작일 기준**입니다. "D일에 진행 중인 행사"는 `event_start_date <= D and D <= event_end_date`로 물으세요.
- 스냅샷 fact(예약·박스오피스)는 `load_date`/`snapshot_date`(그날의 상태)가 시간키입니다.

### 공간축: `admin_dong_code` / `gu_code` (행안부 코드)

- `admin_dong_code` — 행안부 행정동 **10자리** canonical 코드 (조인축).
- `gu_code` — 자치구 5자리 (= admin_dong_code 앞 5자리), `gu` — 자치구 한글 라벨.
- 좌표 보유 행은 `longitude`/`latitude`(WGS84, 서울 bbox 검증 통과분만) 동봉.
- 코드 정본은 asac_axes 패키지의 `dim_admin_dong`(행안부 행정동 마스터 bronze `common.bronze_admin_dong_master` 기반, 서울 426동)입니다. culture silver 전체가 이 dim에 canonical 정렬돼 있어(PR #107 · 스키마 위치 합의 [ASAC-DAG#154](https://github.com/ASAC-DE-bigkk/ASAC-DAG/issues/154)) `admin_dong_code` 조인 시 타 도메인과 같은 정본 코드를 씁니다.

### 조인 예시

```sql
-- 내 도메인 지표를 구×일 문화활동 밀도와 붙이기
select m.*, c.activities_count, c.performances_count
from <my_schema>.my_daily_metric m
left join culture.gold_culture_location_daily c
  on c.gu_code = m.gu_code
 and c.event_date = m.metric_date;

-- 행정동×일 grain 조인 — 426동 전체가 행으로 존재해(0건 동 포함) left join 시 null 걱정 없음
select d.*, c.activities_count
from <my_schema>.my_dong_metric d
left join culture.gold_culture_activity_by_dong c
  on c.admin_dong_code = d.admin_dong_code
 and c.event_date = d.metric_date;

-- "오늘 진행 중인 문화행사"를 silver에서 직접 (기간 겹침 질의)
select gu, admin_dong, title, event_start_date, event_end_date
from culture.silver_culture_event
where event_start_date <= current_date and current_date <= event_end_date;
```

## 바로 쓰는 진입점 (gold)

대부분의 크로스 도메인 조인은 gold로 충분합니다:

| 테이블 | 그레인 | 행수* | 답하는 질문 |
|---|---|---|---|
| `gold_culture_location_daily` | gu_code × event_date | 67,593 | 구별·일별 문화활동 수 (`activities_count` + 종별: performances/events/festivals/exhibitions/sejong) |
| `gold_culture_reservation_daily` | gu_code × snapshot_date | 250 | 구별 공공예약 가용률(`availability_rate` = 접수중/전체) |
| `gold_culture_boxoffice_daily` | snapshot_date × rank_no | 500 | 예매 상위 50 공연이 언제·어디서 |
| `gold_culture_movie_boxoffice_daily` | boxoffice_date (날짜 1행) | 2 | 영화 관객 서울 쏠림(`seoul_audience_share`) — 시도 그레인이라 자치구 축 없음 |
| `gold_culture_sports_schedule` | 경기 1행 | 67 | 서울 야구(잠실·고척) 홈경기 일정 |
| `gold_culture_activity_by_dong` | admin_dong_code × event_date | 177,216 | **행정동**별·일별 활동 — 426동 전체 scaffold(0건 동도 행 존재, `activities_count=0`), 날짜 창 [오늘−90, 오늘+365] |

\* 행수는 2026-07-10 dev 실측. 스냅샷·기간 전개 특성상 매일 증가합니다.

## silver 카탈로그 — 12개

행사/기간 fact (7): "무엇이 언제 어디서 열리나"

| 테이블 | 그레인(유니크 키) | 행수* | 내용 · 원천 |
|---|---|---|---|
| `silver_culture_event` | `event_key` (md5 제목\|시작일\|장소) | 19,456 | 서울 문화행사 — 열린데이터광장. 최대 볼륨 축 |
| `silver_culture_performance` | `performance_id` | 1,560 | KOPIS 공연 — 시설 정밀 조인(mt10id) |
| `silver_culture_festival` | `festival_id` | 219 | KOPIS 축제 |
| `silver_culture_exhibition` | `exhibition_id` | 870 | 시립미술관 전시 — 좌표는 분관만(그 외 구 레벨) |
| `silver_culture_sejong` | `sejong_id` | 16,872 | 세종문화회관 공연/전시 — 단일 시설(좌표 상수) |
| `silver_culture_kcisa_event` | `event_id` | 394 | KCISA 문화정보 — 국립기관(국현·중박 등) 전시 구멍 보강. 위 3축과 교차중복 dedup 완료 |
| `silver_culture_sports_event` | (game_date, stadium, game_time) | 67 | KBO 서울 홈경기 7월~9월초 — seed 원천(월간 수동 갱신) |

스냅샷 fact (3): "그날의 상태"

| 테이블 | 그레인 | 행수* | 내용 |
|---|---|---|---|
| `silver_culture_reservation` | (service_id, load_date) | 14,847 | 공공서비스예약 문화+체육 — 상태(`접수중` 등)·자치구 |
| `silver_culture_boxoffice` | (load_date, rank_no) | 500 | KOPIS 예매상황판 top50 — **공간축 면제**(area=시도뿐) |
| `silver_culture_movie_boxoffice` | (region, boxoffice_date, rank) | 40 | KOBIS 일별 박스오피스 — `region` = 'nation'/'seoul'. `boxoffice_date` = 수집일−1 |

dim (2): 시설 마스터

| 테이블 | 그레인 | 행수* | 내용 |
|---|---|---|---|
| `silver_culture_facility` | `facility_id` | 1,686 | KOPIS 공연시설 — **좌표 100%**, `seat_scale`(좌석수, 미상=null) |
| `silver_culture_space` | `space_key` | 1,071 | 서울 문화공간 — 미술관·도서관 등 (원천 좌표 축 스왑 보정 완료) |

## 주의점 — 정직 구간

1. **구 오배정 상한 ~10%**: `gu`(원본 라벨)와 좌표 유래 구가 다른 행이 최대 10.17% (단순화 폴리곤 경계 + 라벨 의미차 포함, 상시 계측 중). **자치구 분석은 `gu`/`gu_code`(라벨 우선) 기준을 신뢰**하고, `admin_dong` 레벨은 근사로 취급하세요.
2. **좌표 없는 행**: `admin_dong`/`admin_dong_code` = null, 구 레벨(`gu_code`)까지만 유효. 행 자체는 유지됩니다(fail-open).
3. **null = 미측정**: 이상치·미상 값은 추정하지 않고 null입니다 (서울 bbox 밖 좌표, seat_scale 0 등). null 제외 집계는 소비자 몫.
4. **sports는 문화활동 집계 미편입**: `gold_culture_location_daily`에 야구는 없습니다(축 분리). 필요하면 `gold_culture_sports_schedule`을 직접 union.
5. **초기 구축기 각주(7/1~7/6)**: 7/1 event는 7/2 수집분 역산(proxy), 7/4 예약 상태는 저녁 상태 — 상세는 [docs/design/](docs/design/)의 재설계 문서 참조. 7/7 이후는 각주 없음.
6. **행수 스케일 주의**: `silver_culture_event`와 `sejong`은 기간 fact라 과거~미래 수년치 포함. 최근 창으로 where 필터 권장.
7. **`quality_status` 활용**(#111): 각 공간축 silver·`gold_culture_sports_schedule`에 `dong_precise`(좌표로 행정동 정밀)/`gu_only`(구 레벨 근사, admin_dong null)/`unmatched` 표식. **동 레벨 분석은 `where quality_status = 'dong_precise'`** 권장. gold는 `dong_precise_count`(location_daily·reservation_daily)로 롤업.
8. **`gold_culture_activity_by_dong`는 `dong_precise`만**: admin_dong_code 그레인이라 좌표 없는 활동(`gu_only`)은 누락됩니다. 구 레벨 전체는 `gold_culture_location_daily`(+`dong_precise_count`)를 보세요.

## 신선도 — 언제 데이터가 갱신되나

- 수집(bronze): 매일 **03:00 KST** → 변환(silver/gold): Asset 트리거 자동, 대개 **03:30~04:00 반영**.
- 즉 아침에 보는 데이터 = 전일까지 확정분 + 당일 새벽 스냅샷.
- `movie_boxoffice`는 전일 관객(`boxoffice_date` = 수집일−1), `facility`는 주간 전수 리프레시(그 외 요일은 변화분만).
- 원천 신선도는 `dbt source freshness`(collected_at 기준 30h warn/48h error)로 감시 중.

## 더 깊이

- 축 표준 합의: [ASAC-DBT#48](https://github.com/ASAC-DE-bigkk/ASAC-DBT/issues/48) — 시간/공간축 규약 원문
- 모델별 설계·트레이드오프: [docs/design/](docs/design/) (silver 재설계, KCISA 편입, 공간축 canonical 전환 등)
- 수집 내부(계약·재시도·볼륨 감시): ASAC-DAG `dags/domains/culture/docs/`
- bronze를 직접 읽어야 한다면: [models/sources.yml](models/sources.yml) — 15개 테이블, `record_json`(원본 JSON) + lineage. 단 dedup 전이므로 silver 경유 권장.

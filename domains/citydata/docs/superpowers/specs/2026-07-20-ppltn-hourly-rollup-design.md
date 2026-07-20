# gold_citydata_ppltn_hourly — 시간별 인구 롤업 설계 (2026-07-20)

> 서빙에서 비어있던 **시간 단위 이력** 해상도를 채운다. 현재: 현재(스냅샷) ✅ · 일별 ✅ · **시간별 ❌** · 5분(by_time, 서빙 보류).
> 정본 흐름: specs/2026-07-17-citydata-gold-serving-api-design.md §2 의 "시간별 롤업(예정)" 구현.

## 1. 문제

`/data/gold_citydata_ppltn_daily?from&to` 는 "지난주 일별 추이"까지만 답한다.
"지난주를 **시간별로**"("어제 오후 몇 시에 제일 붐볐나")는 못 준다 — 일별은 하루 1점,
by_time(5분)은 대용량이라 D1 서빙 보류. 그 사이 시간 해상도가 공백.

## 2. 모델 — daily 규격의 시간 버전

- **그레인**: `(time_bucket = date_trunc('hour', event_at) [KST], area_cd)` → 시간당 121행
- **소스**: `silver_citydata_ppltn` (daily 와 동일 소스, 시간 단위 GROUP BY). 이름은 dim_seoul_area 조인.
- **컬럼** (daily 와 1:1, 축만 시간):

| 컬럼 | 의미 |
|---|---|
| time_bucket, area_cd | 그레인 |
| area_nm·area_category·sido·gu·admin_dong·gu_code·admin_dong_code·longitude·latitude | 장소 메타(dim 조인) |
| avg_population / max_population / min_population | 그 시간 평균·최대·최소 붐빔 |
| peak_at | 그 시간 피크 5분 시각 |
| peak_congestion_level | 피크 시각 혼잡도 |
| busy_ratio_percent | 붐빔/약간붐빔 슬라이스 비율(%) |
| measurement_count | 그 시간 집계 슬라이스 수 (완결성, 최대 12) |

- **적재(Trino/골드)**: `table+replace` — citydata 골드 전체 불변식(dbt_project.yml) 그대로. slow 티어.
- **계약**: `contract: enforced` + `data_type` 전 컬럼 + `unique_grain(time_bucket, area_cd)` 테스트.
- **tag**: `slow` (일 집계류 — 5분마다 재빌드 불필요, daily 와 같은 그룹).

## 3. D1 서빙 — append(시간 버킷 upsert)

전량 교체하면 1년치(106만 행)를 매 export 재기록 → D1 쓰기 한도(10만/일) 초과.
**hourly 만 append 모드**로 분리한다 (스냅샷 7종·일별 5종은 기존 전량 교체 유지):

- export DAG 에 **HOURLY_APPEND_TABLES** 3번째 경로 추가
- 매시 run: **최근 2시간(late-arrival 여유)** time_bucket 을 D1 에서 DELETE 후 그 구간만 INSERT
  → 시간당 ~242행 쓰기 (한도 여유 큼). 최초 1회는 전체 백필.
- `CREATE TABLE IF NOT EXISTS`(DROP 안 함) — 누적 보존.
- `_catalog` 행은 다른 테이블처럼 upsert.

**규모**: 시간당 121행 · 1년 106만 행 ≈ 100MB (D1 무료 500MB 내).

## 4. 연결·서빙

- `serving_tier: d1_direct`, export 목록(HOURLY_APPEND_TABLES)에 등록 → 대시보드 `served_url` 자동 표시(Dashboard PR#7 로직).
- 조회: `GET /data/gold_citydata_ppltn_hourly?area_cd=POI014&from=2026-07-13&to=2026-07-20`
  → 홍대 시간별 168행. **"지난 일주일 시간별" 완성**.

## 5. 비범위

- by_time(5분) 서빙 — 여전히 보류(hold).
- hourly 크로스 3종·demographics D1 적재 — 별도 확장.
- append 최적화의 일반화(타 도메인) — 공통 서빙 패턴 논의 시.

## 6. 산출물

1. 본 설계 문서
2. `models/gold/gold_citydata_ppltn_hourly.sql`
3. `_citydata_gold__models.yml` 엔트리(description·contract·data_type·test·serving_tier meta)
4. `citydata_serving_export.py` HOURLY_APPEND_TABLES 경로

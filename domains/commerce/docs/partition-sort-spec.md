# 정렬·파티션 스펙 결정 기준 (commerce)

> 근거 실측: ASAC-DBT #262 (silver 조인 OOM 실측·3층 전략) · 작업 이슈: #264.
> 3층 전략에서 이 문서는 **②응답 비용** 층을 담당한다 — ①요청 절단(WHERE·워터마크)이 메모리를
> 지키고, ②는 그 요청의 **스캔 비용**을 줄인다. RDB 대응: 파일 통계(min/max)=BRIN,
> `sorted_by`=CLUSTER(물리 정렬), `partitioning`=선언적 파티셔닝.

## 축 선정 원칙 (사용자 확정 2026-07-19)

- **금지 — 수집 아티팩트 축**: `collected_at` / `observed_date` / `load_date`.
  첫 전량 수집(예: 2026-06-30 일반음식점 534,680건)이 **한 단위에 뭉쳐** 프루닝이 무효가 된다.
- **사용 — 원천 데이터 축**: 거의 모든 행에 확정 존재하고 처리 단위를 실질 구분하는 값만.
  - `updatedt_ts` (LOCALDATA UPDATEDT 파싱) — **실측 null 0 / 2,902,377행**
  - `lastmodts_ts` (LASTMODTS) — 실측 null 0 (updatedt 결측 시 폴백 정렬키)
  - `event_date`/`ym`/`y` (인허가일 APVPERMYMD·폐업일 DCBYMD 파생 = 원천 사건일, 1900~2026 분포)
  - 원천 식별자: `dataset`, `opnsfteamcode`, `mgtno`

## 현행 적용 상태 (sorted_by — #264)

| 모델 | sorted_by | 의도 | 활성화 |
|---|---|---|---|
| gold_license_flow_daily | `event_date` | iceberg_api 범위질의(기간 필터 필수) 파일 프루닝 | --full-refresh 시 전체 재정렬 |
| gold_license_flow_monthly | `ym` | /monthly/detail 폴백 범위질의 | 〃 |
| gold_license_flow_yearly | `y` | 연 범위질의 | 〃 |
| silver_license_history | `dataset, opnsfteamcode, mgtno, updatedt_ts` | prior_tail 키 조회·dataset 단위 운영·암묵 버저닝 축 | 신규 append 즉시 / 기존 파일은 다음 --full-refresh |
| silver_license_current | `dataset, opnsfteamcode, mgtno` | delete+insert 키 매칭·dataset 필터 | 〃 |
| silver_license_entity | `dataset, admin_dong_code` | dataset 필터(#262 M3 실측) + 행정동 집계 지역성 | table 재생성 시 자동(매 run) |

- incremental 모델의 `properties` 는 **테이블 생성 시점에만** 반영된다. 기존 dev/prod 테이블에는
  `ALTER TABLE <t> SET PROPERTIES sorted_by = ARRAY[...]` 로 선반영 가능(신규 쓰기부터 정렬).
  기존 파일까지 재정렬하려면 --full-refresh(또는 유지보수 `optimize` — 정렬 스펙 준수 재작성).

## 파티셔닝 승격 기준 (현재: 전 모델 보류)

파티셔닝은 다음 **3개를 모두** 만족할 때만 추가한다:

1. **규모**: 테이블 ≥ 수천만 행 또는 ≥ 수 GB (참고: #262 실측 — weather silver 48M행이 승격 후보 예시).
2. **소비자**: 해당 축 범위 술어로 조회하는 실소비자(서빙 API·증분 스캔)가 존재.
3. **파티션 밀도**: 예상 파티션당 평균 ≥ 64MB 유지 가능 (과파티셔닝 방지).

현 commerce 최대 테이블(history·flow_daily 각 ~2.9M행)은 1번 미달 — **sorted_by 만으로 파일 min/max
프루닝이 충분**하고, 파티셔닝 시 오히려 초소형 파일 수백 개(예: flow_daily 를 year() 분할 시 119개
연 파티션 × 수백 KB)로 스캔·메타데이터 비용이 증가한다.

> 예외 금지 축: 승격하더라도 수집 아티팩트 축으로는 파티셔닝하지 않는다(위 원칙).

## 확인 방법 (DBeaver `127.0.0.1:30586` 에서 실행 가능)

```sql
-- 1) 스펙 반영 확인 (≒ RDB \d+)
SHOW CREATE TABLE iceberg_dev.commerce.gold_license_flow_daily;
-- → WITH ( ... sorted_by = ARRAY['event_date ASC NULLS FIRST'] ) 보이면 성공

-- 2) 파일별 min/max 조임 확인 (≒ BRIN 유효성)
SELECT file_path, record_count, lower_bounds, upper_bounds
FROM iceberg_dev.commerce."gold_license_flow_daily$files" LIMIT 5;

-- 3) 효과 실측 — 범위질의 실행 후 실제 스캔량 (≒ EXPLAIN ANALYZE 실측부)
SELECT query_id, physical_input_bytes, physical_input_rows
FROM system.runtime.queries ORDER BY created DESC LIMIT 5;
```

## 실측 결과 (2026-07-19 dev, #264 적용 직후 — 기대치 교정)

- **스펙 반영**: 6/6 테이블 `SHOW CREATE TABLE` 에 sorted_by 확인.
- **행수 보존**: entity 2,895,122 완전 일치 · flow 3종 +854/+18/+1 (full-refresh 소급 흡수 — 정상).
- **스캔 바이트 -48%**: flow_daily 2024년 범위질의의 event_date 컬럼 읽기 5,581,726B → 2,893,142B.
  정렬로 RLE 인코딩 효율이 올라간 효과(정렬의 즉시 이득은 압축).
- **파일 프루닝은 즉시 발현되지 않음(중요)**: full-refresh 직후 6개 파일이 **각각 전 기간
  (1900~2026)을 커버** — `sorted_by` 는 writer **스트림 내부** 정렬이라, 병렬 writer 에 해시 분배된
  풀 리빌드 산출 파일은 서로 범위가 겹친다. 프루닝 발현 경로:
  1. **일별 증분 append** — 신규 완결일만 담아 파일별 event_date 범위가 자연히 좁음 → 최근 구간
     질의부터 프루닝 발현(시간 경과에 따라 개선).
  2. 유지보수 `optimize` — 정렬 스펙을 준수해 재작성(파일 배치에 따라 개선).
  - full-refresh 스윕 **직후**가 프루닝 최악 케이스라는 점을 운영 시 인지할 것.

## 변경 이력

- 2026-07-19 #264: sorted_by 6종 코드화 + 본 기준 신설 + 적용 실측 기록 (배경 실측: #262).

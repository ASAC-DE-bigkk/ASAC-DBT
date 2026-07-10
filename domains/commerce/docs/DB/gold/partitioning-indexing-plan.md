# gold 파티셔닝·인덱싱 계획 (검토용 — 미적용)

> **상태: 제안 문서.** 아직 어떤 인덱스도 생성/변경하지 않았다. 사용자 검토 후 지침에 따라 적용한다.

## 0. 현재 상태 (실측)

- gold DB(serving-postgres) 전체 크기: **5.1GB**. 최대 테이블: `commerce_business_entity_history`
  1.86GB(2,897,296행) · `commerce_business_entity` 1.78GB(2,891,729행) ·
  `commerce_food_sanitation_business_detail` 546MB(1,122,868행) · `commerce_mail_order_sale_detail`
  513MB(933,625행). 나머지 81개 테이블은 개별 100MB 미만.
- **인덱스 실태(전수 조사)**: **gold 85개 테이블 전부 PK 1개뿐 — 보조 인덱스 0개.** `dataset`,
  `admin_dong_code`(entity 측, dim 은 PK 있음), `gu_code`, `status_code`, `updatedt`, `collected_at`
  모두 인덱스 없음.
- `commerce_business_entity.updatedt` 범위: 2025-12-15 ~ 2026-07-08(약 7개월), NULL 0%.
- `commerce_business_entity_history.collected_at` 분포: 2026-06 = 1,341,987행 / 2026-07(월 중) =
  1,552,767행 — **월 100만+ 행 증가 추세**(append-only, 무한 누적).

## 1. 실측 근거 — 인덱스 부재의 실제 영향 (EXPLAIN)

### 1.1 API 뷰 조회 (`commerce_v_api_general_restaurant`, `LIMIT 100`)

```
Limit (actual time=1113.5..1187.7ms rows=100)
  Buffers: shared hit=1078 read=219914, temp read=1063 written=64476   -- 디스크 I/O 21만 버퍼(~1.7GB)
  -> Nested Loop Left Join × 3단(region/status/detail)
       -> Parallel Hash Join
            -> Parallel Seq Scan on commerce_food_sanitation_business_detail  -- 112만행 풀스캔
```

**LIMIT 100짜리 단순 조회가 1.1초, 1.7GB I/O.** `general_restaurant` 는
`commerce_food_sanitation_business_detail`(cluster, 21개 API 병합)의 일부인데, 그 테이블에 `dataset`
인덱스가 없어 **매번 112만행 전체를 병렬 스캔**한다. **152개 API view 중 cluster 소속(82개 API,
8개 cluster) 전부**가 이 문제에 해당한다(single 70개는 테이블 자체가 1 API 전용이라 영향 적음).

### 1.2 이력 시간창 조회 (`collected_at > now() - 7일`)

```
Finalize Aggregate (actual time=321.4..326.6ms)
  -> Parallel Seq Scan on commerce_business_entity_history
       Filter: (collected_at > now() - '7 days')
       Rows Removed by Filter: 447,549   -- 전체 read=152,010 버퍼(~1.2GB), 정작 쓰는 건 18%뿐
```

290만행 중 **18%만 필요한데 100% 스캔**. `commerce_load_gold`(매일 06:00 증분), watchdog, 향후
"최근 N일 변경분" 류 리포트/조회가 전부 이 패턴에 해당.

## 2. 인덱싱 우선순위 (즉시 적용 검토 — 저비용·고효과)

| 우선순위 | 대상 | 인덱스 | 근거 | 예상 효과 |
|---:|---|---|---|---|
| **1** | detail **cluster 8개**(food_sanitation_business·media_content_business·tourism_business·sports_facility·game_entertainment_venue·public_sanitation_service·medical_institution·amusement_park) | `CREATE INDEX ON <table>(dataset)` | §1.1 — cluster 는 여러 API 가 한 테이블에 섞여 있어 `dataset` 이 유일한 스코프 필터. API view 82종이 이 필터에 의존 | 112만행 풀스캔 → dataset 필터 인덱스 스캔(수백~수천행) |
| **2** | `commerce_business_entity` | `CREATE INDEX ON commerce_business_entity(dataset)` | 도메인/API view(320개) 전부가 entity 를 `dataset` 으로 필터 | 289만행 풀스캔 회피 |
| **3** | `commerce_business_entity_history` | `CREATE INDEX ON commerce_business_entity_history(collected_at)` (또는 BRIN — §2.1 참고) | §1.2 — 시간창 조회·증분 리포트·watchdog | 290만행 → 대상 구간만 |
| **4** | `commerce_business_entity_history` | `CREATE INDEX ON commerce_business_entity_history(dataset)` | API 이력 view(152개)가 `dataset` 필터 | 좌동(entity 와 동일 이유) |
| **5** | `commerce_business_entity` | `CREATE INDEX ON commerce_business_entity(admin_dong_code)` | `commerce_dim_region` 조인 키(320 view 전부가 LEFT JOIN) — region 쪽은 PK 있으나 entity 쪽 조인 컬럼은 미인덱스 | Nested Loop 효율화(§1.1 조인 필터 단계) |
| **6** | `commerce_business_entity` | `CREATE INDEX ON commerce_business_entity(fmt, status_code, detail_status_code)` | `commerce_dim_business_status` 조인 키(복합) | 좌동 |
| **7** | `commerce_business_entity`, `_history` | `CREATE INDEX ON <table>(gu_code)` | 메모리 기록: "위치데이터는 시군구·행정동 코드로 타 도메인과 매핑 예정" — 교차 도메인 조인 대비 | 향후 크로스도메인 조인 대비(현재 내부 조회에서 직접 사용 확인은 안 됨 — **선반영 여부는 사용자 판단**) |
| — | single 70개 detail | (불필요) | 테이블 자체가 1 API 전용이라 `dataset` 값이 상수 — 필터해도 이득 없음 | — |

### 2.1 `collected_at` — BRIN vs BTREE

`commerce_business_entity_history` 는 **append-only**(값이 삽입 시각 순으로 물리 적재)이므로
`collected_at` 은 **BRIN 인덱스**가 BTREE 대비 유리할 가능성이 높다(용량 대폭 작음, append-only
데이터에 최적). 단, BRIN 은 "물리적 삽입 순서 ≈ 논리적 정렬 순서"를 전제하므로 **실제 적재 순서를
확인 후 결정**(현재 로더는 silver 버전 순 append 이므로 전제 충족 가능성 높음 — 확정은 실측 필요).

```sql
-- 후보 A: BTREE(범용, range+정렬 모두 지원, 용량 큼)
CREATE INDEX ON commerce_business_entity_history USING btree (collected_at);
-- 후보 B: BRIN(append-only 전제, 용량 1/100 수준, range 조회에 특화)
CREATE INDEX ON commerce_business_entity_history USING brin (collected_at);
```

## 3. 파티셔닝 — 지금 할지 말지 판단

### 3.1 결론: **지금은 이르다.** 트리거 조건을 넘으면 재검토.

| 판단 근거 | 값 |
|---|---|
| 전체 gold DB 크기 | 5.1GB(파티셔닝 없이 관리 가능한 규모 — 통상 수십GB부터 실효) |
| 최대 테이블(entity_history) | 1.86GB / 290만행 — 단일 인덱스로 충분히 다룰 수 있는 규모 |
| 데이터 보유 기간 | 약 7개월(2025-12~2026-07) — 파티션 프루닝 이득이 나오려면 보통 파티션 여러 개(≥수개월~수년)가 쌓여야 함 |
| 쿼리 패턴 | 대부분 `dataset` 필터(§2) — **시간 범위가 아니라 API 종류가 주 필터**이므로, 시간 파티셔닝보다 §2 인덱싱이 우선 |

**인덱싱이 선행되고 나면 파티셔닝의 한계효용이 더 낮아진다** — 인덱스만으로 §1 의 두 문제(dataset
필터·시간창 필터)가 상당 부분 해소되기 때문. 파티셔닝은 "인덱스로도 해결 안 되는 규모"에서 쓰는 다음
단계 도구로 남겨둔다.

### 3.2 향후 트리거 조건 (아래 중 하나라도 충족 시 재검토 착수)

- `commerce_business_entity_history` 가 **12개월 이상**(현재 7개월) 누적되어 오래된 구간을 아카이브/
  드롭할 필요가 생길 때 → **RANGE PARTITION BY collected_at (월 단위)**.
- gold DB 전체가 **20GB 이상**으로 커질 때(현재 5.1GB, 월 100만+ 행 증가세 기준 약 1년 내외 도달 가능).
- 특정 cluster detail(현재 최대 546MB)이 **2GB 이상**으로 커질 때 → 해당 테이블만 개별 파티셔닝 검토
  (전체 일괄 파티셔닝 아님 — 필요한 테이블만).
- Trino 조회(`serving.public.*`)에서 시간범위 조건의 응답 지연이 사용자 체감 수준으로 나타날 때.

### 3.3 대상 우선순위(트리거 충족 시)

1. `commerce_business_entity_history`(append-only, 무한 성장, `collected_at` RANGE — 가장 자연스러움)
2. 대형 cluster detail(현재 1순위: `food_sanitation_business` 546MB) — 역시 `collected_at` RANGE
3. `commerce_business_entity`(현재 상태 테이블, mutable) — **파티셔닝 부적합 후순위**. RANGE 파티션은
   append-only 성격에 맞는데, entity 는 UPDATE 위주(최신 포인터 갱신)라 파티션 키 값이 바뀌는 행이
   생겨 관리가 번거로움 → entity 는 **인덱싱만**으로 대응하고 파티셔닝 대상에서 제외 권장.

## 4. 적용 순서 제안 (권장 — 확정 아님, 지침 대기)

1. **§2 우선순위 1~4**(cluster 8개 + entity/history 의 `dataset`, history 의 `collected_at`) —
   즉시 적용해도 리스크 없음(순수 추가 인덱스, 쓰기 경로 영향은 INSERT 시 인덱스 갱신 비용뿐이며
   `commerce_load_gold` 는 일 1회 배치라 영향 미미).
2. **§2 우선순위 5~6**(region/status 조인 키) — 뷰 조회 체감 지연이 확인되면 추가.
3. **§2 우선순위 7**(`gu_code`) — 실제 크로스도메인 조인 요구가 구체화되면 추가(현재는 선제 반영 여부
   판단 필요).
4. **파티셔닝**은 §3.2 트리거 전까지 보류.

## 5. 재현 쿼리

```sql
-- 인덱스 현황 전수 확인
select tablename, count(*) from pg_indexes where schemaname='public' and tablename like 'commerce_%' group by tablename order by count desc;

-- 특정 뷰의 실행계획(적용 전/후 비교용)
explain (analyze, buffers) select * from commerce_v_api_general_restaurant limit 100;

-- 테이블/인덱스 물리크기
select relname, pg_size_pretty(pg_total_relation_size(relid)) from pg_catalog.pg_statio_user_tables where relname like 'commerce_%' order by pg_total_relation_size(relid) desc;
```

## 6. 다음 단계

1. 사용자 검토 → §2 표의 어느 우선순위까지, 어떤 인덱스 타입(BTREE/BRIN)으로 적용할지 지침.
2. (선택) region/status 조인 실측(EXPLAIN) 추가 확인 — 지침 있을 시 착수.
3. 승인된 범위만 구현(브랜치·이슈·PR — CLAUDE.md §워크플로 준수). 인덱스는 `gold/loader.py` DDL
   ensure 단계에 `CREATE INDEX IF NOT EXISTS`로 편입해 멱등성을 유지한다.

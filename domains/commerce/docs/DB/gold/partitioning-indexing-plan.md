# gold 파티셔닝·인덱싱 계획 (2026-07-10 인덱싱 적용됨)

> **상태: 인덱싱 적용 완료 · 파티셔닝 보류.** §2 우선순위를 view SQL 실제 predicate 로 재검증해
> **6개 인덱스**(entity/history × dataset·admin_dong_code·(status_code,detail_status_code))를
> 적용했다(`ddl.create_index_sql()`). 원안의 "cluster detail 8개 dataset 인덱스"는 구현 중 재검토해
> **제외**했다 — view JOIN/WHERE 를 다시 읽어보니 API view 는 `dataset` 필터를 entity/history 측에만
> 걸고 detail 은 항상 (entity_seq, collected_at, content_hash) PK 로만 조인돼 detail 쪽 dataset
> 인덱스는 실제로 안 쓰인다(과반영 회피). 라이브 검증(§9): pharmacy(선택도 0.76%) 조회 1187ms→**18ms**
> (Bitmap Index Scan 확인). §3 파티셔닝은 트리거 조건 미충족으로 여전히 보류.

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

## 2. 인덱싱 — 적용 결과 (2026-07-10, `ddl.create_index_sql()`)

**구현 중 원안을 수정**했다 — view SQL 을 다시 정밀 확인한 결과, API view 의 `dataset` 필터는
`e.dataset`/`h.dataset`(entity/history 측)에만 걸리고, detail 은 항상 detail 자신의 PK
`(entity_seq, collected_at, content_hash)` 로만 조인된다(entity/history 에서 넘어온 값으로 조회).
즉 **detail 테이블의 `dataset` 컬럼은 어느 view 도 직접 predicate 로 쓰지 않는다** — 원안 우선순위
1(cluster 8개 dataset 인덱스)은 **적용하지 않음**(과반영 회피, 실제 view SQL 근거 없음).

| 대상 | 인덱스 | 근거(view SQL) | 상태 |
|---|---|---|---|
| `commerce_business_entity`, `_history` | `(dataset)` | API view `where e/h.dataset = '<short>'` | ✅ 적용 |
| `commerce_business_entity`, `_history` | `(admin_dong_code)` | `_DIM_JOIN` → `commerce_dim_region` | ✅ 적용 |
| `commerce_business_entity`, `_history` | `(status_code, detail_status_code)` | `_DIM_JOIN` → `commerce_dim_business_status`(`fmt` 은 dim 측 PK 라 entity 측엔 불필요 — 원안 표기 `fmt,status_code,detail_status_code` 를 실제 조인식 기준으로 수정) | ✅ 적용 |
| ~~detail cluster 8개 `(dataset)`~~ | — | view 가 detail.dataset 을 predicate 로 안 씀(위 설명) | ❌ 미적용(원안 폐기) |
| `commerce_business_entity_history(collected_at)` | BRIN/BTREE | §1.2 시간창 조회(watchdog·리포트) — **view 조인이 아니라 별도 ad-hoc 쿼리 패턴** | 보류(§2.1, 이번 스코프 밖) |
| `commerce_business_entity*(gu_code)` | — | 현재 어떤 view/쿼리도 직접 predicate 로 안 씀 | 보류(§2.1) |
| single 70개 detail | (불필요) | 테이블 자체가 1 API 전용 | — |

### 2.1 보류 항목(이번 스코프 밖 — "뷰 구성 요소"에 한정된 지침이라 미적용)

- **`collected_at`**(BRIN vs BTREE): §1.2 의 "최근 7일" 류 조회는 view 정의가 아니라 리포트/watchdog
  ad-hoc 쿼리 패턴이라 이번 적용 범위(뷰 구성 요소) 밖. 필요해지면 BRIN(append-only 전제, 용량
  1/100)과 BTREE 중 실측 후 선택.
- **`gu_code`**: 메모리 기록의 "타 도메인 크로스조인 대비"는 현재 어떤 view/쿼리도 아직 참조하지
  않아 이번 지침(뷰 구성 요소) 범위 밖. 크로스도메인 조인이 실제로 구현될 때 추가.

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

## 4. 적용 이력

- 2026-07-10: §2 의 6개 인덱스 적용(gold 초기화 + 전면 재적재와 함께 라이브 반영). `entity_id`
  (text 해시) → `entity_seq`(bigint) 전환도 같은 작업에서 병행(근거: [normalization-plan.md](normalization-plan.md)
  entity_seq 절) — 인덱스 자체의 크기·조인 비용도 함께 줄었다.
- **파티셔닝**은 §3.2 트리거 미충족으로 계속 보류.

## 5. 재현 쿼리

```sql
-- 인덱스 현황 전수 확인
select tablename, count(*) from pg_indexes where schemaname='public' and tablename like 'commerce_%' group by tablename order by count desc;

-- 특정 뷰의 실행계획(적용 전/후 비교용)
explain (analyze, buffers) select * from commerce_v_api_general_restaurant limit 100;

-- 테이블/인덱스 물리크기
select relname, pg_size_pretty(pg_total_relation_size(relid)) from pg_catalog.pg_statio_user_tables where relname like 'commerce_%' order by pg_total_relation_size(relid) desc;
```

## 6. 라이브 검증 결과 (2026-07-10, gold 전면 재적재 후)

| 항목 | 결과 |
|---|---|
| 인덱스 생성 | 6개 전부 확인(`commerce_business_entity`/`_history` × dataset·admin_dong_code·status) |
| **선택도 낮은 API**(`commerce_v_api_pharmacy`, entity 대비 0.76%) | `Bitmap Index Scan on commerce_business_entity_dataset_idx` 사용 — **1187ms → 18ms** |
| **선택도 높은 API**(`commerce_v_api_general_restaurant`, 18.5%) | 여전히 Parallel Seq Scan — **정상**(Postgres 플래너가 이 선택도에서는 seq scan 이 실제로 더 빠르다고 정확히 판단. 인덱스가 안 쓰인 게 아니라 안 쓰는 게 맞는 케이스) |
| entity_seq 전환 | `commerce_entity_key` 2,891,707건, entity/entity_key 1:1 정합 확인 |
| 전체 재적재 | 83 objects·8,681,958 rows·1,728s(build_catalog 25s + load_gold 1700s + code_values 1.3s) |

**결론**: 6개 인덱스는 152개 API view 중 **선택도 낮은 대다수**(general_restaurant·mail_order_sale·
instant_sale_mfg 등 소수 대형 API 제외)에서 실측으로 확인된 큰 개선을 제공한다. 대형 API 는 인덱스
유무와 무관하게 seq scan 이 이론적으로도 맞는 케이스라 추가 조치 불필요.

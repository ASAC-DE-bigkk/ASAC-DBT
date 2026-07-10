# gold 정규화 계획 (검토용 — 미적용)

> **상태: 제안 문서.** 아래 내용은 실측 데이터 기반 분석과 설계 옵션이며, **아직 어떤 테이블도 변경하지
> 않았다.** 사용자 검토 후 어느 항목에 어떤 옵션을 적용할지 지침을 받으면 그때 구현한다.

## 0. 문제의식 (사용자 제기)

gold 는 이미 **85개 테이블**(entity+이력 2, dim 3, detail 78[cluster 8+single 70], marker/catalog 2)로
구성돼 있다. 여기서 "정규화"를 저카디널리티 컬럼마다 기계적으로 자식 테이블을 뽑아내는 방식으로 하면,
**컬럼 수만큼 테이블이 폭증**한다(방금 §2 실측에서 후보만 182건 나왔다 — 그대로 다 뽑으면 85→267개).
→ 이 문서의 목표는 **"뽑을 수 있는 것"과 "뽑을 가치가 있는 것"을 데이터로 분리**하고, 뽑더라도
**테이블 수를 최소화하는 설계**를 제시하는 것이다.

## 1. 방법론

1. `pg_stats`(이미 ANALYZE 완료 — 스캔 없이 즉시 조회)로 **85개 테이블 전체·1,031개 컬럼**의
   `n_distinct`/`null_frac`을 일괄 수집.
2. detail 78개 payload 컬럼만 대상(공통 supertype/dim 은 이미 정규화됨 — §6).
3. **필드명 접미사 휴리스틱**으로 1차 분류: `_ymd/_dt`(날짜) · `_yn`(플래그) · `_cnt/_area/_scp/_tons/
   _no/_flr/_hrm/_lay`(수량·식별번호) → **자동 제외**(정규화 대상 아님, 애초에 범주형이 아님).
   `_nm/_gbn/_gbnnm/_se/_senm/_cd` → **정규화 후보**로 1차 통과.
4. **distinct ≤300 ∧ (distinct/non-null행) <5% ∧ non-null행 ≥500** 만 후보 유지 → 182건.
5. 상위 후보는 **실제 값 표본**을 조회해 진짜 통제어휘인지 확인(추측 금지 — 사용자 지침 준수).

## 2. 핵심 발견 — 실측 검증

### 2.1 표본 검증 결과 (실제 값 조회)

| 컬럼 | 테이블 | distinct | 실제 값(표본) | 판정 |
|---|---|---:|---|---|
| `uptaenm`(업태명) | food_sanitation_business | 75 | 한식·중국식·일식·분식·호프/통닭·편의점 … | ✅ 진짜 통제어휘 |
| `sntuptaenm`(세부업태명) | food_sanitation_business | 85 | 좌동 + 키즈카페·푸드트럭·산후조리원 … | ✅ 진짜 통제어휘 |
| `silmetnm`(판매방법명) | mail_order_sale | 28 | (통신판매 방법 구분) | ✅ 통제어휘 |
| `bzstat_se_nm` | building_sanitation | 2 | 건물위생관리업 / 건물위생관리업 기타 | ✅ 통제어휘(소규모) |
| `ctgry_nm`(배출시설 종별) | air_pollution_facility | 3 | 4종 / 5종 / (blank) | ✅ 통제어휘(소규모) |
| **`uptaenm`(mail_order_sale)** | mail_order_sale | **977** | 자유기술(판매품목 자기서술) | ❌ **동일 필드명, 다른 의미** — 준자유텍스트, 제외 |
| `homepage`/`jtupsomainedf`/`cndpermntwhy` | food/public_sanitation | 2~21 | 전부 공백(결측) | ❌ 결측 위주 — 범주 아님 |
| `isream`/`monam`/`pasgbreth` | food/game_venue | 2~27 | `0`/`1`/공백 | ❌ Boolean 플래그 — 별도 코드테이블 불필요 |
| `lindjobgbnnm`/`bupnm` 등 | livestock_sale/sports_facility | **1** | 테이블 전체 상수 1값 | ❌ 정보량 0 — 정규화 무의미 |

**중요 결론**: **동일 필드명이 API마다 다른 의미/자유도를 가진다**(`uptaenm`이 food 에서는 75종 통제
분류지만 mail_order_sale 에서는 977종 준자유텍스트). → **필드명 기준 글로벌 매핑 금지**, 반드시
**(테이블, 컬럼) 단위로 값을 확인한 것만** 후보로 채택한다(아래 §3 은 표본 검증을 거치지 않은 나머지
항목을 "review"로 명시해 **적용 전 재검증 필요**를 표시했다).

### 2.2 왜 detail cluster(8개)가 최우선인가

`commerce_food_sanitation_business_detail`은 이미 **21개 API 를 병합**한 테이블이다. 그 안의
`uptaenm`(75종)/`sntuptaenm`(85종) 하나씩만 정규화해도 **112만 행의 반복이 컬럼 2개로 해소**된다 —
cluster 는 이미 "병합"돼 있어서 **테이블 1개당 정규화 효과가 single 테이블보다 훨씬 크다.**
같은 이유로 `mail_order_sale`(93만행, single 이지만 최대 규모)의 `silmetnm`(28종)도 우선순위가 높다.

## 3. 분류 결과 (실측값·savings 순, 상위 60건)

`savings` = non-null행수 − distinct값수 (정규화 시 제거되는 반복 텍스트 수, 우선순위 근거).

| 순위 | 테이블 | 컬럼 | distinct | 행수 | savings | 판정 |
|---:|---|---|---:|---:|---:|---|
| 1 | food_sanitation_business | `bdngownsenm` | 3 | 1,122,868 | 1,122,865 | **Tier A**(표본검증 필요*) |
| 2 | food_sanitation_business | `wtrsplyfacilsenm` | 5 | 1,122,868 | 1,122,863 | **Tier A**(표본검증 필요*) |
| 3 | food_sanitation_business | `lvsenm` | 8 | 1,122,868 | 1,122,860 | **Tier A**(표본검증 필요*) |
| 4 | food_sanitation_business | `trdpjubnsenm` | 8 | 1,122,868 | 1,122,860 | **Tier A**(표본검증 필요*) |
| 5 | food_sanitation_business | `sntuptaenm` | 85 | 1,122,868 | 1,122,783 | ✅ **Tier A(검증완료)** |
| 6 | food_sanitation_business | `uptaenm` | 75 | 1,006,913 | 1,006,838 | ✅ **Tier A(검증완료)** |
| 7 | mail_order_sale | `silmetnm` | 28 | 933,625 | 933,597 | ✅ **Tier A(검증완료)** |
| 8 | media_content_business | `culwrkrsenm`/`nearenvnm`/`culphyedcobnm`/`regnsenm`/`bdngsrvnm` | 5~23 | 141,361 | ~14.1만 ea | **Tier A**(표본검증 필요*) |
| 9 | public_sanitation_service | `bdngownsenm`/`uptaenm`/`sntuptaenm` | 3~28 | 134,178 | ~13.4만 ea | **Tier A**(표본검증 필요*) |
| 10 | tobacco_retail | `mwsrnm` | 4 | 95,281 | 95,277 | **Tier A**(표본검증 필요*) |
| 11 | game_entertainment_venue | `culwrkrsenm`~`bfgameocptectcobnm` | 2~40 | 51,410 | ~5만 ea | **Tier A**(표본검증 필요*) |
| — | livestock_sale | `lindjobgbnnm` | **1** | 41,933 | 41,932 | **Tier B**(상수 — 정규화 무의미) |
| — | homepage/jtupsomainedf/cndpermntwhy | — | 2~21 | 다수 | 다수 | **Tier C**(결측/플래그 — 제외) |
| — | pharmtrdar/storetrdar/engstntrnmaddr | — | 199~271 | 만 단위 | 만 단위 | **Tier D**(면적/주소 텍스트 추정 — 개별 확인 필요) |

`*표본검증 필요` = §2.1 방식으로 아직 실제 값을 열람하지 않은 항목(자동 분류만 거침). **mail_order_sale
의 `uptaenm` 사례**(같은 접미사·낮아 보이는 배율이라도 실제론 준자유텍스트)가 있으므로, **Tier A(표본검증
필요) 항목은 적용 전 반드시 값 표본을 확인**해야 한다 — 이 문서는 그 확인을 시행하지 않은 상태다(전수
확인은 사용자 지침 이후 착수 여부 결정).

전체 182건(candidate 109 + review 73) 원자료는 재현 가능(§5 재현 쿼리)하며 지면상 상위만 표기했다.

## 4. 설계 옵션 — 테이블 폭증 방지

### Option 1 — 공유 코드 테이블 1개 (권장, MVP-first)

```sql
create table commerce_code_value (
  domain text,        -- 'food_business_type' | 'food_business_subtype' | 'mail_order_sale_method' | ...
  value  text,         -- 원본 한글 값(자연키) — 서러게이트 코드 발급 안 함(불필요한 ID 남발 방지)
  n_occurrences bigint, -- 참고용 — 실측 당시 등장 행수(문서화 목적, 갱신은 카탈로그 재실측 시)
  primary key (domain, value)
);
```

- **detail 테이블은 변경하지 않는다** — 기존 text 컬럼 그대로 둔다. `commerce_code_value` 는
  **정본 값 목록(governance/드롭다운/BI 참조용) 문서화 테이블**로 신설.
- Tier A(검증완료 + 향후 검증될 항목) 값을 `domain` 으로 묶어 **테이블 1개에 전부 수용** — 후보가
  10개든 100개든 **신규 테이블은 항상 1개**(폭증 원천 차단).
- 리스크·비용 최소: 스키마 마이그레이션·백필·FK 없음. `commerce_catalog` 처럼 카탈로그 재실측 시 갱신.

### Option 2 — 진짜 3NF 전환(컬럼→FK, 후행 검토)

- detail 테이블의 해당 컬럼을 `<col>_code` 로 바꾸고 `commerce_code_value(domain, value)` 를 FK 참조.
- 스토리지 절감·참조무결성 확보. 단, **detail 78개 중 대상 컬럼만 스키마 변경 + 백필 필요**(비용 큼).
- **적용 시점 판단 기준**: gold DB 전체 크기가 현재 **5.1GB**(§ partitioning-indexing-plan.md 참고)에서
  유의미하게 커지거나(예: 20GB+), 해당 컬럼이 조회 WHERE/GROUP BY 에 실제로 자주 쓰이기 시작할 때만
  검토. **지금은 근거 부족**(TOAST 압축으로 반복 짧은 문자열의 실질 저장비용은 이미 낮음).

**권장**: 지금은 **Option 1만** 적용(신규 테이블 +1, 위험 0)하고, Option 2 는 트리거 조건 충족 시
개별 컬럼 단위로만 재검토.

## 5. 재현 쿼리 (재검증·확장용)

```sql
-- 컬럼별 카디널리티(스캔 없음, ANALYZE 결과 활용)
select s.tablename, s.attname, s.n_distinct, s.null_frac, t.n_live_tup
from pg_stats s
join pg_stat_user_tables t on t.relname = s.tablename
where s.schemaname='public' and s.tablename like 'commerce_%_detail'
order by s.tablename, s.attname;

-- 특정 컬럼 표본값 확인(적용 전 필수 — §2.1 mail_order_sale.uptaenm 반례 참고)
select distinct <col> from <table> where <col> is not null limit 200;
```

## 6. 이미 정규화된 부분 (참고 — 이번 분석 범위 밖)

`status_code`/`detail_status_code`→`commerce_dim_business_status`, `gu_code`/`admin_dong_code`→
`commerce_dim_region`, `dataset`(및 major/category/sub_category)→`commerce_dim_dataset` 은
**이미 gold 설계 시점에 정규화 완료**(참고: [tables.md](tables.md)). 이번 분석은 그 **바깥의 detail
payload(비공통 78테이블)** 만 다룬다.

## 7. 다음 단계

1. 사용자 검토 → 어떤 Tier A 항목에 Option 1/2 중 무엇을 적용할지 지침.
2. (선택) 표본검증 미완료 Tier A 항목 전수 확인 스크립트 실행 — 지침 있을 시 착수.
3. 승인된 범위만 구현(브랜치·이슈·PR — CLAUDE.md §워크플로 준수).

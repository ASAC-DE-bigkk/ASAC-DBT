# commerce gold → 도메인 공통 Serving Contract(#478) 필드 매핑

> **목적**: commerce 의 자체 서빙 tier 스킴([serving-design.md](serving-design.md): `iceberg_api`/`d1_rollup`/
> `d1_direct`)을 ASAC-DAG **#478 도메인 공통 Serving Contract v1**(`meta.serving.*`)로 수렴할 때,
> **각 gold 모델의 필드값이 무엇이 되고 어떻게 세팅되는지**를 미리 확정해 두는 준비 문서.
> 계약 규격 정본은 ASAC-DAG [`docs/contracts/serving-contract-v1.md`](https://github.com/ASAC-DE-bigkk/ASAC-DAG/blob/dev/docs/contracts/serving-contract-v1.md),
> 추적 경로는 dags 번들 [`docs/serving-contract-chain.md`](https://github.com/ASAC-DE-bigkk/ASAC-DAG/blob/dev/domains/commerce/docs/serving-contract-chain.md).

## 적용 상태 (2026-07-27)

- **15 d1_direct 모델에 `config.meta.serving.*` 를 선언 완료**했다([`_commerce_gold__models.yml`](../../../models/gold/_commerce_gold__models.yml)).
  복합키 근거로 자체 generic test [`macros/unique_combination_of_columns.sql`](../../../macros/unique_combination_of_columns.sql)
  (dbt_utils 무의존)를 추가하고 각 복합키 모델에 모델레벨 test 로 걸었다. PK 컬럼 `not_null` 근거도 보강했다.
- **계약(validator) 규칙을 로컬에서 재현 검증 → 15 모델 0 findings(PASS).** grain 은 각 모델 SQL 의
  `GROUP BY` 로 확정했으므로 `unique_combination` 은 구조적으로 통과한다. 단 **ASAC-DBT `serving_contract/`
  가 현 서브모듈에 없어 실 validator·dbt 실행은 로컬 불가** — 최종 검증은 다음 PR CI(`serving-contract-gate`)
  와 팀 `dbt test` 다. not_null 보강 컬럼은 모두 taxonomy 파생 또는 `'UNK'` 센티넬이라 비-null 이 구조적.
- D1 export(Publisher 배선)는 여전히 미구현 — 이 선언은 그 export PR 이 소비할 **계약 선언 절반**이다.

## 0. 먼저 — 지금 강제되는가? (결론)

- **지금 수정할 "D1 서빙 dags"는 없다.** commerce D1 export 는 **미구현**(serving-design.md §5-⑤ —
  gold 는 Iceberg 카탈로그에만 존재, D1 스냅샷 export 파이프라인 미구축). `commerce_load_gold` DAG 에
  `export_d1` 태스크가 아직 없다. 즉 이 계약을 어길 "현재 서빙 코드"가 없다.
- **CI 게이트는 지금 commerce 를 막지 않는다.** ASAC-DBT `serving-contract-gate` 는 `domains/**/*.yml`
  변경 PR 에서 돌지만, **`config.meta.serving` 을 선언한 모델만 검증**하고 나머지는 건너뛴다 →
  commerce 는 선언 0개라 **0 models = PASS**. (게이트 워크플로 주석 + `validator._check_structural`
  이 `meta.serving` 있는 모델에만 적용됨으로 확인.)
- **그래서 이 문서는 "지금 당장 고쳐라"가 아니라 "commerce 가 D1 export 를 짓기 전에 이렇게 선언하라"**
  는 준비 계약이다. 지금 자체 tier 스킴대로 export 를 만들면 #478 이 없앤 파편화 + #477(등록 누락
  조용한 실패) 계열 문제를 commerce 가 재발명하게 된다 — 그래서 **export 구현과 같은 PR**에서 아래
  매핑대로 `meta.serving` 을 선언하고 공통 `common/serving` Publisher 를 소비하는 것이 목표다.

## 1. 커버리지 판정 — 22 gold 중 지금 "직접 D1 제품"은 15개뿐

| commerce tier | 개수 | 계약상 처리 | 이유 |
|---|---|---|---|
| **d1_direct** | 15 | **지금 `meta.serving` 선언 대상** (`enabled: true`) | 현재 gold 모델 자체가 소형 스냅샷 D1 제품 |
| **d1_rollup** | 6 | **보류** — D1 제품은 "사전 롤업 파생 모델"(미빌드, §5-⑤). 파생 빌드 후 그 모델에 선언 | 원장 모델은 대용량 → D1 금지. 계약은 실제 D1 대상(롤업 파생)에 건다 |
| **iceberg_api** | 1 (flow_daily) | **계약 대상 아님** (`enabled` 선언 안 함) | Trino 직조회 제품 — D1 게시가 아님. Worker API(#476) 영역 |
| d1_current (22 외) | 2 (agg_daily/monthly) | 보류 — 모델 미빌드(§1.1) | 빌드 후 d1_direct 규약 준용 선언 |

> **핵심**: `iceberg_api`(D1 아님)와 `d1_rollup`(D1 대상이 원장이 아니라 미빌드 롤업 파생)에 지금
> `meta.serving` 을 달면 계약 의미가 틀린다. **지금 선언 가능한 정확한 대상은 d1_direct 15개.**

## 2. 도메인 공통값 — 15 d1_direct 에 동일 세팅 (그리고 그 근거)

| 필드 | 값 | 어떻게/왜 이렇게 세팅되는가 |
|---|---|---|
| `enabled` | `true` | d1_direct = D1 전량 스냅샷 export 대상 |
| `external` | `true` | 공개 API·화면 6종 소비(serving-design 전제). 내부 전용 지표 없음 |
| `contract_version` | `v1` | 최초 채택 |
| `publication_mode` | `snapshot` | serving-design §0 전역원칙 ① "모든 D1 export = 전량 교체 스냅샷". staging→pointer 원자 전환 |
| `zero_policy` | `retain_last_good` | serving-design §5-⑤ 부분 실패 시맨틱("실패 테이블만 직전 스냅샷 유지=stale")과 동일. 0행이면 직전본 유지 |
| `partial_policy.min_publish_ratio` | `0.8` (선택·권장) | serving-design §9-⑨ "`_meta.row_count` 기대 밴드 벗어나면 스왑 중단·경보"를 계약 필드로 표현 |
| `publication_trigger.schedule_cron` | `"0 6 * * *"` | serving-design §7 갱신체인 — gold 06:00 직후 export(같은 DAG run). KST 06:00 |
| `event_time` | **미선언** | d1_direct 는 현재-스냅샷 집계(시간 필터축 없음) → 미선언. 따라서 `freshness_slo_minutes` **조건부 필수 면제**(v1.1 §3.1). 게시 지연·stale 는 `publication_trigger`(§7.4)가 감시 |
| `shape` | 표별(§3) | 그룹 집계 = `rollup`, 엔티티 1행 = `wide` |
| `product_question` | 표별(§3) | serving-design §1~6 "답하는 핵심 질문"에서 채택(지어낸 질문 아님) |
| `product_id` | 표별(§3) | `commerce_` 접두 + 표명. `^[a-z0-9_]+$`·전역 유일 |

> **staleness 26h(serving-design §7)** 는 계약의 `event_time` 기반 `freshness_slo_minutes` 가 아니라
> **게시 주기 감시**(§7.4 `published_at ↔ publication_trigger`)에 해당. commerce `commerce_serve_state`
> 마커가 그 로컬 구현. 두 감시축을 혼동하지 않는다.

## 3. 테이블별 필드값 (d1_direct 15) — product_id · grain · primary_key · shape · question

`primary_key` **근거 컬럼**은 아래대로. 계약(validator)은 PK 각 컬럼에 `not_null`, 단일 PK 는 `unique`,
복합 PK 는 모델레벨 `unique_combination_of_columns` **테스트 근거**를 요구한다. "근거상태" = 현재 yml
기준 무엇을 더 추가해야 하는지.

| # | 모델 | product_id | grain (1행 의미) | primary_key | shape | 근거상태 |
|---|---|---|---|---|---|---|
| 1 | dong_summary | `commerce_license_dong_summary` | 행정동 1행 | `[admin_dong_code]` | wide | ✅ **완비**(not_null·unique 이미 있음) |
| 2 | dong_category_matrix | `commerce_license_dong_category_matrix` | 행정동×구×대×중 (SQL `GROUP BY` 실측) | `[admin_dong_code, gu_code, major, category]` | rollup | `gu_code`·`major` not_null + `unique_combination` ✅적용 |
| 3 | gu_specialization | `commerce_license_gu_specialization` | 구×대×중 | `[gu_code, major, category]` | rollup | `major` not_null + `unique_combination` |
| 4 | seasonality | `commerce_license_seasonality` | 유형×월(1~12)×대×중×dataset | `[event_type, month_of_year, major, category, dataset]` | rollup | `category`·`dataset` not_null + `unique_combination` |
| 5 | cohort_survival | `commerce_license_cohort_survival` | 대×중×코호트연×경과연차 | `[major, category, cohort_y, years_elapsed]` | rollup | `category` not_null + `unique_combination` |
| 6 | lifespan | `commerce_license_lifespan` | 대×중×dataset×구 | `[major, category, dataset, gu_code]` | rollup | `category`·`dataset`·`gu_code` not_null + `unique_combination` |
| 7 | status_duration | `commerce_license_status_duration` | dataset×상태×진행여부 (SQL `GROUP BY d.dataset, d.st, d.is_ongoing` 확정 — major/category 는 라벨) | `[dataset, status_code, is_ongoing]` | rollup | `dataset`·`is_ongoing` not_null + `unique_combination` ✅적용 |
| 8 | status_transition | `commerce_license_status_transition` | 대×중×dataset×from×to | `[major, category, dataset, from_status, to_status]` | rollup | `major`·`category`·`dataset` not_null + `unique_combination` |
| 9 | area_profile | `commerce_detail_area_profile` | 대×중×dataset×구 | `[major, category, dataset, gu_code]` | rollup | `major`·`category`·`gu_code` not_null + `unique_combination` |
| 10 | multi_site | `commerce_license_multi_site` | 대×중×dataset | `[major, category, dataset]` | rollup | `major`·`category` not_null + `unique_combination` |
| 11 | change_activity | `commerce_license_change_activity` | 대×중×dataset | `[major, category, dataset]` | rollup | `major`·`category` not_null + `unique_combination` |
| 12 | address_succession | `commerce_license_address_succession` | (폐업대·중→개업대·중) 전이 | `[closed_major, closed_category, opened_major, opened_category]` | rollup | `closed_category`·`opened_category` not_null + `unique_combination` |
| 13 | phone_succession | `commerce_license_phone_succession` | 동일 전이 grain | `[closed_major, closed_category, opened_major, opened_category]` | rollup | `closed_category`·`opened_category` not_null + `unique_combination` |
| 14 | data_quality | `commerce_license_data_quality` | 대×중×dataset (API 단위 152) | `[major, category, dataset]` | rollup | `major`·`category` not_null + `unique_combination` |
| 15 | env_facility_operation | `commerce_env_facility_operation` | dataset×구 (51) | `[dataset, gu_code]` | rollup | `gu_code` not_null + `unique_combination` |

**product_question (serving-design 채택, 각 1개):**

| 모델 | product_question |
|---|---|
| dong_summary | 이 행정동엔 업소가 몇 곳이고 영업/폐업 구성과 지도 커버리지는 어떤가? |
| dong_category_matrix | 이 동네엔 어떤 업종이 많고 최근 1년 새로 생긴 업종은 무엇인가? |
| gu_specialization | 이 자치구는 서울 평균 대비 어떤 업종에 특화(LQ>1)돼 있나? |
| seasonality | 개·폐업이 한 해 중 어느 달(계절)에 몰리나? |
| cohort_survival | 이 업종으로 창업하면 k년 후 생존확률은 얼마인가? |
| lifespan | 이 업종 폐업 업소는 보통 몇 년 버텼고 조기폐업률은 얼마인가? |
| status_duration | 휴업/영업/폐업 상태는 각각 얼마나 지속되나? |
| status_transition | 휴업 다음은 재개인가 폐업인가(상태 전이 방향)? |
| area_profile | 이 업종 가게는 보통 몇 ㎡이고 소형/대형 구성은? |
| multi_site | 이 업종은 얼마나 체인화(동일 전화 다지점)돼 있나? |
| change_activity | 어떤 업종이 상호·주소를 자주 바꾸나(개명·이전 활발도)? |
| address_succession | 폐업한 그 자리엔 다음에 어떤 업종이 들어오나? |
| phone_succession | 폐업 사장님은 다음에 같은 업종인가 다른 업종으로 재도전하나? |
| data_quality | 어느 API(dataset)가 좌표/전화/행정동 결측이 심한가? |
| env_facility_operation | 자치구별 환경 배출시설의 연간 가동일수·가동시간 분포는? |

## 4. 적용 내역·잔여 검증 (무엇을 했고 무엇이 남았나)

**한 것:**
1. 15 d1_direct 모델에 `config.meta.serving.*` 선언(§2 공통값 + §3 표별값).
2. 복합키 14개에 모델레벨 `unique_combination_of_columns` test + PK 컬럼 `not_null` 보강.
   단일키 dong_summary 는 기존 `[not_null, unique]` 로 충족.
3. 자체 generic test 매크로 `macros/unique_combination_of_columns.sql` 추가(dbt_utils 무의존 —
   commerce 프로젝트에 packages.yml 없음, 기존 custom test 패턴 승계).
4. grain 은 각 모델 SQL `GROUP BY` 로 확정(예: status_duration = `dataset, st, is_ongoing`;
   dong_category_matrix 는 `admin_dong_code, gu_code, major, category`).
5. validator 규칙 로컬 재현 검증 → **15 모델 0 findings(PASS)**, 전역 product_id 유일(`commerce_` 접두).

**잔여(로컬 불가 → CI·dbt test 가 최종 게이트):**
- ASAC-DBT `serving_contract/` 미체크아웃이라 **실 validator·dbt 실행 불가**. `serving-contract-gate`
  CI 와 팀 `dbt test` 가 최종 검증. not_null 보강 컬럼은 taxonomy 파생/`'UNK'` 센티넬이라 비-null 이
  구조적이고, `unique_combination` 은 GROUP BY 키라 유일이 구조적 — 실패 가능성 낮으나 CI 로 확정할 것.
- **rollup(6)·iceberg_api(1)·current(2) 는 미선언**(§1) — 지금 달면 계약 의미가 틀리므로 제외.
- product_id 는 타 도메인과 겹치면 안 됨 — `commerce_` 접두로 회피했으나 CI 전역 검사가 최종 확인.

## 5. 적용 형태 (실제 yml 예시)

단일키(dong_summary)와 복합키(env_facility_operation) 두 형태로 적용됐다.

```yaml
# 단일키 — 컬럼 unique 로 근거 충족
- name: gold_license_dong_summary
  config:
    contract: {enforced: true}
    meta:
      serving:
        enabled: true
        external: true
        contract_version: v1
        product_id: commerce_license_dong_summary
        product_question: 이 행정동엔 업소가 몇 곳이고 영업/폐업 구성과 지도 커버리지는 어떤가?
        grain: admin_dong_code 마다 한 행입니다.
        primary_key: [admin_dong_code]
        publication_mode: snapshot
        zero_policy: retain_last_good
        publication_trigger:
          schedule_cron: "0 6 * * *"
        shape: wide
        partial_policy:
          min_publish_ratio: 0.8
  columns:
    - name: admin_dong_code
      tests: [not_null, unique]          # 단일 PK 근거

# 복합키 — 모델레벨 unique_combination_of_columns 로 근거 충족
- name: gold_env_facility_operation
  config:
    contract: {enforced: true}
    meta:
      serving:
        # ... (enabled/external/... 동일 공통값)
        product_id: commerce_env_facility_operation
        primary_key: [dataset, gu_code]
        # ...
  tests:
    - unique_combination_of_columns:        # 복합 PK 근거 (자체 매크로)
        combination_of_columns: [dataset, gu_code]
  columns:
    - name: dataset
      tests: [not_null]
    - name: gu_code
      tests: [not_null]
```

## 6. 남은 절차 (선언은 완료 — 다음 단계)

1. ✅ **계약 선언(dbt `meta.serving.*`)** — 15 d1_direct 완료(§4). PR 올리면 `serving-contract-gate`
   CI 가 형식·전역 유일성·PK 근거를 최종 검증한다(통과해야 merge). 팀 `dbt test` 로 근거 테스트 실행 확인.
2. **D1 export DAG** — commerce D1 export 를 짓는 시점에 **짝 롤아웃 이슈**를 연다(culture #520 패턴).
   export 는 자체 스크립트가 아니라 ASAC-DAG `common/serving` `build_serving_export_dag` factory 를
   소비하고, `commerce_load_gold`(06:00) 파이프라인에 태스크로 편입한다(serving-design.md §5-⑤).
3. **d1_rollup 6종**은 사전 롤업 파생 모델을 빌드한 뒤 그 파생 모델에 `meta.serving` 선언,
   **d1_current 2종**(agg_daily/monthly)은 빌드 후 d1_direct 규약 준용.
4. **iceberg_api(flow_daily)**는 계약 밖 — Trino 직조회, Worker/#476 영역.

## 관련

- 계약 정본: ASAC-DAG [`docs/contracts/serving-contract-v1.md`](https://github.com/ASAC-DE-bigkk/ASAC-DAG/blob/dev/docs/contracts/serving-contract-v1.md)
- 공통 Publisher: ASAC-DAG [`common/serving/`](https://github.com/ASAC-DE-bigkk/ASAC-DAG/tree/dev/common/serving) · Validator: ASAC-DBT [`serving_contract/`](https://github.com/ASAC-DE-bigkk/ASAC-DBT/tree/dev/serving_contract)
- 추적: dags 번들 `docs/serving-contract-chain.md` · commerce 서빙 설계: [serving-design.md](serving-design.md) · gold 모델 계약: [../../../models/gold/_commerce_gold__models.yml](../../../models/gold/_commerce_gold__models.yml)

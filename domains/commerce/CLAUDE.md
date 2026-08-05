# CLAUDE.md — dbt/domains/commerce (에이전트 작업 규약)

이 파일은 **commerce dbt 번들**(`dbt/domains/commerce/`)에서 작업할 때의 규약이다.
레이어·모델·실행 등 **상세 규약의 정본은 [README.md](README.md)** 이며, 이 파일은 그 위에
전역 규칙만 얹는다. commerce 도메인 전체(수집·오케스트레이션 포함)의 상위 규약은
ASAC-DAG `dags/domains/commerce/CLAUDE.md` 를 따른다.

## 언어 규정 (Language convention)

- **사람이 읽는 산출물은 한글로 작성한다.** 사용자에게 출력하는 대화 응답, 이슈·PR 본문,
  `docs/` 문서, 리포트, 커밋 메시지 등 "읽는 사람"이 있는 결과물은 기본 **한글**.
- **백그라운드 작업은 영어로 진행해도 된다.** SQL/dbt 모델 코드, 매크로, 식별자·컬럼명,
  내부 로그, 임시 파일 등 사람이 직접 읽는 최종 산출물이 아닌 것은 **영어** 허용.
- 판단 기준: "사람이 읽으라고 만든 것인가?" → 예: **한글**. 기계·내부용인가? → **영어** 무방.

## 작업 경계

- commerce 도메인의 dbt 변경은 이 번들(`dbt/domains/commerce/`) 안에서만 수행한다.
- **타 도메인 dbt 폴더**(`traffic_weather`, `culture`, `transit`, `citydata`)는 **읽기만 하고
  수정하지 않는다.** 교차 도메인 참조는 gold 레이어의 published source 계약으로만 이뤄진다
  (예: weather 가 `commerce_gold.gold_license_dong_summary` 를 source 로 소비).

## D1 서빙 계약 — **org 공통 Serving Contract(#478) 를 따른다**

commerce gold → 공유 Cloudflare **D1(SQLite)** 서빙의 정본 규약은 **ASAC-DAG#478 Serving Contract
v1/v1.1** 이다. commerce 는 2026-07-22 그 스레드에서 채택에 동의했고, 22개 gold 모델이 확정 필드를
선언하고 있다. **자체 규약으로 이탈해 관리하지 않는다.**

### 선언 (dbt `config.meta.serving`)

gold 22종 전부가 아래를 선언한다(2026-08-05 실측, `_commerce_gold__models.yml`).

| 구분 | 필드 | 선언 |
|---|---|---|
| #478 v1 필수 | `enabled` · `product_id` · `contract_version` · `grain` · `primary_key` · `publication_mode` · `zero_policy` | 22/22 |
| #478 v1.1 | `publication_trigger` 22 · `event_time` 3 · `freshness_slo_minutes` 3 | 조건부 필수 충족 |
| #478 선택 | `product_question` 22 · `shape` 22 · `partial_policy` 21 | — |
| 외부 공개 | `external` | 22/22 |
| commerce 확장 | `serving_tier`(`d1_direct`/`d1_rollup`/`iceberg_api`) · `d1_table` · `usage_patterns` · `source_evidence` · `quality_coverage` · `public_projection` · `public_primary_key` | — |

**확장 필드는 같은 `meta.serving` 블록 안에 얹는다** — 별도 네임스페이스를 만들지 않는다. #478 이
금지한 것은 "다른 이름의 규약을 병행 선언하는 것"(이중 선언)이지 확장 자체가 아니다.

**외부 공개를 내릴 때는 `external: false`** 만 바꾼다(#434 가 요청하는 방식). gold 테이블·파이프라인은
그대로 두고, `*_serving_export` 를 한 번 돌리면 `_catalog.external` 이 0 이 되어 카탈로그에서 빠진다.

### 소비 (dags `commerce_serving_export`)

`include/gold/serving_export.py` 가 `meta.serving.*` 를 읽어 `_catalog` 15컬럼(`product_id` ·
`external` · `product_question` · `event_time` 등)을 채운다. 즉 **선언이 곧 게시 결과**다.
`serving_tier` 별 동작: `d1_direct` = 스냅샷, `d1_rollup` = export 시 GROUP BY 파생,
`iceberg_api` = D1 금지·Trino 직조회. 기존 serving Postgres 경로는 폐기(2026-07-14).

`SERVING_SPEC`(export 쪽 목록)과 dbt 선언은 export 실행 시 대조되어 어긋나면 경보한다.

### 이력 (같은 사고를 반복하지 않기 위해)

2026-07-27, 이미 적용돼 있던 `meta.serving`(07-23) 위에 **같은 내용을 한 번 더 적용**해 블록이
충돌했다. 중복을 되돌린 것까지는 맞았으나, 그 김에 이 문서를 **"commerce 는 #478 에 강제 종속되지
않는다"** 로 다시 써버렸다 — 실제 충돌 범위보다 훨씬 넓은 결론이었다. 하루 뒤 PR#335 머지와 22종
재작성으로 코드는 정반대(#478 확정 필드 정합)로 갔고, 문서만 9일간 반대로 남아 있었다.

**교훈: 로컬 충돌은 충돌만 되돌린다. 거버넌스 문서를 함께 고치지 않는다.**

### 참고

- 설계 정본: [docs/DB/gold/serving-design.md](docs/DB/gold/serving-design.md)(tier 분류·화면 매핑).
- 계약 이력: ASAC-DBT #334 → **PR #335(머지 2026-07-28)**, export ASAC-DAG #493 → PR #494.
- 추적: dags 번들 [`docs/serving-contract-chain.md`](../../../dags/domains/commerce/docs/serving-contract-chain.md).
- `serving-contract-gate` CI 는 `config.meta.serving` 이 있는 모든 모델을 #478 규격으로 검사한다 —
  commerce 는 확정 필드를 갖추고 있으므로 통과 대상이다. 타 도메인 무접촉.
